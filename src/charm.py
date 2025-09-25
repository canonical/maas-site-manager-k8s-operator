#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk
"""MAAS Site Manager Charm."""

import json
import logging
import os
import secrets
import string
from typing import Any, cast
from urllib.parse import urlparse

import ops
import requests
from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificatesAvailableEvent,
    CertificatesRemovedEvent,
    CertificateTransferRequires,
)
from charms.data_platform_libs.v0.data_interfaces import DatabaseCreatedEvent, DatabaseRequires
from charms.data_platform_libs.v0.s3 import S3Requirer
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v0.loki_push_api import LokiPushApiConsumer
from charms.maas_site_manager_k8s.v0 import enroll
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_coordinator_k8s.v0.charm_tracing import trace_charm
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer, charm_tracing_config
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from ops.pebble import CheckStatus
from requests.exceptions import RequestException

from api import SiteManagerClient

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical", "trace"]
SERVICE_PORT = 8000
MSM_PEER_NAME = "site-manager-cluster"
MSM_CREDS_ID = "site-manager-operator-cred-id"
MSM_CREDS_SECRET = "site-manager-operator-cred"
SCOPE = "unit"
TLS_TRANSFER_RELATION = "receive-ca-cert"


PASSWD_CHOICES = string.ascii_letters + string.digits


class DatabaseNotReadyError(Exception):
    """Signals that the database cannot yet be used."""


class OperatorUserError(Exception):
    """Signals that the charm user is not available."""


class S3IntegrationNotReadyError(Exception):
    """Signals that the s3 integration is not ready."""


@trace_charm(
    tracing_endpoint="charm_tracing_endpoint",
    extra_types=[
        DatabaseRequires,
        GrafanaDashboardProvider,
        LokiPushApiConsumer,
        MetricsEndpointProvider,
        IngressPerAppRequirer,
    ],
)
class MsmOperatorCharm(ops.CharmBase):
    """MAAS Site Manager Charm."""

    def __init__(self, *args):
        super().__init__(*args)

        self.container = self.unit.get_container("site-manager")
        self.pebble_service_name = "msm"
        self.database_name = "msm"

        # Initialize relation objects
        self._database = DatabaseRequires(
            self, relation_name="database", database_name=self.database_name
        )
        self._prometheus_scraping = MetricsEndpointProvider(
            self,
            relation_name="metrics-endpoint",
            jobs=[{"static_configs": [{"targets": [f"*:{SERVICE_PORT}"]}]}],
        )
        self._loki_consumer = LokiPushApiConsumer(self, relation_name="logging-consumer")
        self._grafana_dashboards = GrafanaDashboardProvider(
            self, relation_name="grafana-dashboard", dashboards_path="src/grafana_dashboards"
        )
        self._ingress = IngressPerAppRequirer(self, port=SERVICE_PORT, strip_prefix=True)
        self.tracing = TracingEndpointRequirer(self, protocols=["otlp_http"])
        self.charm_tracing_endpoint, _ = charm_tracing_config(self.tracing, None)

        self.framework.observe(
            self.on["site-manager"].pebble_ready, self._update_layer_and_restart
        )
        self.framework.observe(self.on.config_changed, self._update_layer_and_restart)
        self.framework.observe(
            self.on["site-manager"].pebble_check_recovered, self._on_pebble_check_recovered
        )

        # Enrollment service
        self._enroll = enroll.EnrollProvider(self)
        enroll_events = self.on[enroll.DEFAULT_ENDPOINT_NAME]
        self.framework.observe(enroll_events.relation_joined, self._on_maas_enroll_joined)
        self.framework.observe(enroll_events.relation_broken, self._on_maas_enroll_broken)

        # Database connection
        self.framework.observe(self._database.on.database_created, self._on_database_created)
        self.framework.observe(self._database.on.endpoints_changed, self._on_database_created)
        self.framework.observe(
            self.on.database_relation_broken, self._on_database_relation_removed
        )

        # Loki push
        self.framework.observe(
            self._loki_consumer.on.loki_push_api_endpoint_joined,
            self._on_loki_push_api_endpoint_joined,
        )
        self.framework.observe(
            self._loki_consumer.on.loki_push_api_endpoint_departed,
            self._on_loki_push_api_endpoint_departed,
        )

        # Ingress
        self.framework.observe(self._ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self._ingress.on.revoked, self._on_ingress_revoked)

        # Certificate transfer
        self._ca_folder_path = "/usr/local/share/ca-certificates"
        self.certificate_transfer = CertificateTransferRequires(self, TLS_TRANSFER_RELATION)
        self.framework.observe(
            self.certificate_transfer.on.certificate_set_updated, self._on_cert_transfer_available
        )
        self.framework.observe(
            self.certificate_transfer.on.certificates_removed, self._on_cert_transfer_removed
        )

        # Charm actions
        self.framework.observe(self.on.create_admin_action, self._on_create_admin_action)

        self.bucket = "msm-images"
        self.s3_requirer = S3Requirer(self, "s3", self.bucket)
        self.framework.observe(
            self.s3_requirer.on.credentials_changed, self._update_layer_and_restart
        )

    def _update_layer_and_restart(self, event):
        """Handle changed configuration."""
        self.unit.status = ops.MaintenanceStatus("Assembling pod spec")

        # Fetch the new config value
        log_level = str(self.model.config["log-level"]).lower()

        # Do some validation of the configuration options
        if log_level not in VALID_LOG_LEVELS:
            self.unit.status = ops.BlockedStatus("invalid log level: '{log_level}'")
            return

        # Verify that we can connect to the Pebble API in the workload container
        if not self.container.can_connect():
            event.defer()
            self.unit.status = ops.WaitingStatus("waiting for Pebble API")
            return

        # push CA certificates
        self._dump_all_certificates()

        try:
            layer = self._pebble_layer
        except DatabaseNotReadyError:
            self.unit.status = ops.WaitingStatus("Waiting for database relation")
            return
        except S3IntegrationNotReadyError:
            self.unit.status = ops.WaitingStatus("Waiting for s3 integration")
            return

        # Handle Loki push API endpoints
        self._add_log_targets(layer)

        # Push an updated layer with the new config
        self.container.add_layer("site-manager", layer, combine=True)
        self.container.restart(self.pebble_service_name)

        if self.container.get_check("http-test").status == CheckStatus.UP:
            if version := self.version:
                # add workload version in juju status
                self.unit.set_workload_version(version)

            if (
                self.unit.is_leader()
                and self.peers
                and not self.get_peer_data(self.app, MSM_CREDS_ID)
            ):
                try:
                    self._create_operator_user()
                except OperatorUserError as ex:
                    logger.error(ex)
                    self.unit.status = ops.BlockedStatus("Failed to create operator user")
                    return
            self.unit.status = ops.ActiveStatus()
        else:
            self.unit.status = ops.WaitingStatus("Waiting for msm service to become available")

    def _on_pebble_check_recovered(self, event: ops.PebbleCheckRecoveredEvent) -> None:
        logger.info("msm service recovered")
        if version := self.version:
            # add workload version in juju status
            self.unit.set_workload_version(version)

        if self.unit.is_leader() and self.peers and not self.get_peer_data(self.app, MSM_CREDS_ID):
            try:
                self._create_operator_user()
            except OperatorUserError as ex:
                logger.error(ex)
                self.unit.status = ops.BlockedStatus("Failed to create operator user")
                return

        self.unit.status = ops.ActiveStatus()

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event is fired when Postgres database is created."""
        self._update_layer_and_restart(event)

    def _on_database_relation_removed(self, event) -> None:
        """Event is fired when relation with Postgres is broken."""
        self.unit.status = ops.WaitingStatus("Waiting for database relation")

    def _on_loki_push_api_endpoint_joined(self, event) -> None:
        """Event is fired when relation with Loki is established."""
        self._update_layer_and_restart(event)

    def _on_loki_push_api_endpoint_departed(self, event) -> None:
        """Event is fired when relation with Loki is removed."""
        self._update_layer_and_restart(event)

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent):
        logger.info("This app's ingress URL: %s", event.url)
        self._update_layer_and_restart(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent):
        logger.info("This app no longer has ingress")
        self._update_layer_and_restart(event)

    def _add_log_targets(self, layer: ops.pebble.LayerDict) -> None:
        """Set up logging with Loki."""
        existing_layer = self.container.get_plan().to_dict()
        if "log-targets" in existing_layer:
            layer["log-targets"] = existing_layer["log-targets"]
        loki_endpoints = [e["url"] for e in self._loki_consumer.loki_endpoints]

        # Check for new endpoints
        for endpoint in loki_endpoints:
            is_existing = False
            for target in layer.get("log-targets", {}).values():
                if target.get("location", "") == endpoint:
                    target["services"] = ["all"]
                    is_existing = True
                    break

            if not is_existing:
                if "log-targets" not in layer:
                    layer["log-targets"] = {}

                layer["log-targets"][f"loki-{len(layer['log-targets'])}"] = {
                    "override": "replace",
                    "type": "loki",
                    "location": endpoint,
                    "services": ["all"],
                }

        # Check for departed endpoints
        for target in layer.get("log-targets", {}).values():
            if target.get("location", "") not in loki_endpoints:
                target["services"] = []

    @property
    def _pebble_layer(self) -> ops.pebble.LayerDict:
        """Return a dictionary representing a Pebble layer."""
        cmd_line = [
            "uvicorn",
            "--host 0.0.0.0",
            f"--port {SERVICE_PORT}",
            "--factory",
            "--loop uvloop",
        ]
        if self.root_path:
            cmd_line.append(f"--root-path {self.root_path}")
        cmd_line.append("msm.apiserver.main:create_app")
        layer = {
            "summary": "site-manager layer",
            "description": "pebble config layer for site-manager",
            "services": {
                f"{self.pebble_service_name}": {
                    "override": "replace",
                    "summary": "MAAS Site Manager",
                    "command": " ".join(cmd_line),
                    "startup": "enabled",
                    "environment": self.app_environment,
                },
            },
            "checks": {
                "http-test": {
                    "override": "replace",
                    "http": {"url": "http://localhost:8000/version"},
                }
            },
        }

        return cast(ops.pebble.LayerDict, layer)

    @property
    def version(self) -> str:
        """Reports the current workload (FastAPI app) version."""
        if self.container.can_connect() and self.container.get_services(self.pebble_service_name):
            try:
                return self._request_version()
            except RequestException as e:
                logger.warning("unable to get version from API: %s", str(e))
            except Exception:
                logger.exception("unable to get version from API")
        return ""

    @property
    def root_path(self) -> str | None:
        """Get external path prefix handled by the proxy."""
        if u := self._ingress.url:
            path = urlparse(u).path
            return path if path != "/" else None
        else:
            return None

    @property
    def app_environment(self) -> dict[str, Any]:
        """This property method creates a dictionary containing environment variables for the application.

        It retrieves the database authentication data by calling
        the `_fetch_postgres_relation_data` method and uses it to populate the dictionary.
        If any of the values are not present, it will be set to None.
        The method returns this dictionary as output.
        """
        db_data = self._fetch_postgres_relation_data()
        s3_data = self._fetch_s3_connection_info()
        env = {
            "UVICORN_LOG_LEVEL": self.model.config["log-level"],
            "MSM_DB_HOST": db_data.get("db_host", None),
            "MSM_DB_PORT": db_data.get("db_port", None),
            "MSM_DB_USER": db_data.get("db_username", None),
            "MSM_DB_NAME": db_data.get("db_name", None),
            "MSM_DB_PASSWORD": db_data.get("db_password", None),
            "MSM_BASE_PATH": self._ingress.url,
            "MSM_S3_ACCESS_KEY": s3_data.get("access-key", None),
            "MSM_S3_SECRET_KEY": s3_data.get("secret-key", None),
            "MSM_S3_ENDPOINT": s3_data.get("endpoint", None),
            "MSM_S3_BUCKET": s3_data.get("bucket", None),
            "MSM_S3_PATH": s3_data.get("path", None),
            "MSM_TEMPORAL_SERVER_ADDRESS": self.model.config["temporal-server-address"],
            "MSM_TEMPORAL_NAMESPACE": self.model.config["temporal-namespace"],
            "MSM_TEMPORAL_TASK_QUEUE": self.model.config["temporal-task-queue"],
            "MSM_TEMPORAL_TLS_ROOT_CAS": self.model.config["temporal-tls-root-cas"],
        }
        return env

    def _request_version(self) -> str:  # pragma: nocover
        """Fetch the version from the running workload using the API."""
        resp = requests.get(f"http://localhost:{SERVICE_PORT}/version", timeout=10)
        return resp.json()["version"]

    def _fetch_postgres_relation_data(self) -> dict:
        """Fetch postgres relation data.

        This function retrieves relation data from a postgres database using
        the `fetch_relation_data` method of the `database` object. The retrieved data is
        then logged for debugging purposes, and any non-empty data is processed to extract
        endpoint information, username, and password. This processed data is then returned as
        a dictionary. If no data is retrieved, the unit is set to waiting status and
        the program exits with a zero status code.
        """
        relations = self._database.fetch_relation_data()
        logger.debug("Got following database data: %s", relations)
        for data in relations.values():
            if not data:
                continue
            try:
                host, port = data["endpoints"].split(":")
                db_data = {
                    "db_host": host,
                    "db_port": port,
                    "db_username": data["username"],
                    "db_password": data["password"],
                    "db_name": data["database"],
                }
            except KeyError:
                raise DatabaseNotReadyError()
            else:
                return db_data
        raise DatabaseNotReadyError()

    def _fetch_s3_connection_info(self) -> dict:
        """Fetch s3 connection info."""
        if connection_info := self.s3_requirer.get_s3_connection_info():
            try:
                return {
                    "access-key": connection_info["access-key"],
                    "secret-key": connection_info["secret-key"],
                    "endpoint": connection_info["endpoint"],
                    "bucket": connection_info["bucket"],
                    "path": connection_info["path"],
                }
            except KeyError:
                raise S3IntegrationNotReadyError()
        raise S3IntegrationNotReadyError()

    def _on_cert_transfer_available(self, event: CertificatesAvailableEvent):
        for i, cert in enumerate(event.certificates):
            cert_filename = f"{self._ca_folder_path}/receive-ca-cert-{self.model.uuid}-{event.relation_id}-{i}-ca.crt"
            self.container.push(cert_filename, cert, make_dirs=True)
            self.container.exec(["update-ca-certificates", "--fresh"]).wait()

    def _on_cert_transfer_removed(self, event: CertificatesRemovedEvent):
        certs_to_remove = [
            filename
            for filename in os.listdir(self._ca_folder_path)
            if filename.startswith(f"receive-ca-cert-{self.model.uuid}-{event.relation_id}")
        ]
        for cert in certs_to_remove:
            self.container.remove_path(cert)
        self.container.exec(["update-ca-certificates", "--fresh"]).wait()

    def _dump_all_certificates(self):
        relations = [
            relation for relation in self.model.relations[TLS_TRANSFER_RELATION] if relation.active
        ]
        for rel in relations:
            certs = self.certificate_transfer.get_all_certificates(rel.id)
            for i, cert in enumerate(certs):
                cert_filename = (
                    f"{self._ca_folder_path}/receive-ca-cert-{self.model.uuid}-{rel.id}-{i}-ca.crt"
                )
                self.container.push(cert_filename, cert, make_dirs=True)
        self.container.exec(["update-ca-certificates", "--fresh"]).wait()

    def _create_msm_user(
        self, username: str, password: str, email: str, fullname: str | None = None
    ) -> bool:
        """Create an admin user.

        Args:
            username (str): username
            password (str): password
            email (str): e-mail address
            fullname (Union[str, None]): Fullname (optional)

        Returns:
            bool: whether the user was created
        """
        logger.info(f"creating user {username}")
        cmd_line = ["msm-admin", "create-user", "--admin", username, email, password]
        if fullname:
            cmd_line.append(fullname)
        if self.container.can_connect() and self.container.get_services(self.pebble_service_name):
            try:
                proc = self.container.exec(
                    cmd_line,
                    service_context=self.pebble_service_name,
                )
                proc.wait()
                return True
            except ops.pebble.ExecError:
                return False
        else:
            return False

    def _on_create_admin_action(self, event: ops.ActionEvent):
        """Handle the create-admin action.

        Args:
            event (ops.ActionEvent): Event from the framework
        """
        username = event.params["username"]
        password = event.params["password"]
        email = event.params["email"]
        fullname = event.params.get("fullname", None)

        if self._create_msm_user(username, password, email, fullname):
            event.set_results({"info": f"user {username} successfully created"})
        else:
            event.fail(f"Failed to create user {username}")

    def _create_operator_user(self) -> None:
        """Create an internal admin operator user. Store the credentials in a Juju secret."""
        username = f"{self.app.name}-operator"
        fullname = f"{self.app.name} charm operator"
        password = "".join([secrets.choice(PASSWD_CHOICES) for i in range(16)])
        email = f"no-reply@{self.app.name}.charm"

        if self._create_msm_user(username, password, email, fullname):
            content = {"username": email, "password": password}
            try:
                secret = self.model.get_secret(label=MSM_CREDS_SECRET)
                secret.set_content(content)
            except ops.model.SecretNotFoundError:
                secret = self.app.add_secret(
                    content=content,
                    label=MSM_CREDS_SECRET,
                )
            self.set_peer_data(self.app, MSM_CREDS_ID, secret.get_info().id)
        else:
            raise OperatorUserError("Unable to create operator user")

    @property
    def peers(self) -> ops.Relation | None:
        """Fetch the peer relation."""
        return self.model.get_relation(MSM_PEER_NAME)

    def set_peer_data(self, app_or_unit: ops.Application | ops.Unit, key: str, data: Any) -> None:
        """Put information into the peer data bucket."""
        if not self.peers:
            return
        self.peers.data[app_or_unit][key] = json.dumps(data or {})

    def get_peer_data(self, app_or_unit: ops.Application | ops.Unit, key: str) -> Any:
        """Retrieve information from the peer data bucket."""
        if not self.peers:
            return {}
        data = self.peers.data[app_or_unit].get(key, "")
        return json.loads(data) if data else {}

    def _get_enroll_token(self) -> str | None:
        """Create an enrollment token for a MAAS Site."""
        if creds_id := self.get_peer_data(self.app, MSM_CREDS_ID):
            creds = self.model.get_secret(id=creds_id).get_content(refresh=True)
            client = SiteManagerClient(
                username=creds["username"],
                password=creds["password"],
                url=f"http://localhost:{SERVICE_PORT}",
            )
            return client.issue_enroll_token()
        else:
            return None

    def _on_maas_enroll_joined(self, event: ops.RelationEvent) -> None:
        """Set relation data for enrollment."""
        logger.info(event)
        if not self.unit.is_leader():
            return
        if enroll_token := self._get_enroll_token():
            self._enroll.publish_enroll_token(event.relation, enroll_token)
        else:
            event.defer()

    def _on_maas_enroll_broken(self, event: ops.RelationEvent) -> None:
        """Handle a broken enrollment relation."""
        logger.info(event)
        if not self.unit.is_leader():
            return
        if creds_id := self.get_peer_data(self.app, MSM_CREDS_ID):
            creds = self.model.get_secret(id=creds_id).get_content(refresh=True)
            client = SiteManagerClient(
                username=creds["username"],
                password=creds["password"],
                url=f"http://localhost:{SERVICE_PORT}",
            )
            return client.remove_site(event.relation.data[event.relation.app]["uuid"])
        else:
            event.defer()


if __name__ == "__main__":  # pragma: nocover
    ops.main(MsmOperatorCharm)  # type: ignore
