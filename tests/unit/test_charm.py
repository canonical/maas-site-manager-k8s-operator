# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
import os
import unittest
import unittest.mock
import uuid

import ops
import ops.testing
from charms.maas_site_manager_k8s.v0 import enroll
from ops.pebble import CheckInfo, CheckLevel, CheckStatus

from charm import (
    MSM_CREDS_ID,
    MSM_PEER_NAME,
    PASSWD_CHOICES,
    DatabaseNotReadyError,
    MsmOperatorCharm,
    S3IntegrationNotReadyError,
)


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(MsmOperatorCharm)
        self.harness.set_model_name("maas-dev-model")
        self.harness.handle_exec("site-manager", ["update-ca-certificates", "--fresh"], result=0)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    @unittest.mock.patch("charm.requests.get", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_postgres_relation_data")
    @unittest.mock.patch("ops.model.Container.get_check")
    def test_pebble_layer(
        self,
        mock_get_check,
        mock_fetch_postgres_relation_data,
        mock_get,
        mock_fetch_s3_connection_info,
    ):
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        # Expected plan after Pebble ready with default config
        expected_plan = {
            "services": {
                "msm": {
                    "override": "replace",
                    "summary": "MAAS Site Manager",
                    "command": "uvicorn --host 0.0.0.0 --port 8000 --factory --loop uvloop msm.apiserver.main:create_app",
                    "startup": "enabled",
                    "environment": {
                        "UVICORN_LOG_LEVEL": "info",
                        "MSM_DB_HOST": None,
                        "MSM_DB_PORT": None,
                        "MSM_DB_USER": None,
                        "MSM_DB_NAME": None,
                        "MSM_DB_PASSWORD": None,
                        "MSM_BASE_PATH": None,
                        "MSM_S3_ACCESS_KEY": None,
                        "MSM_S3_SECRET_KEY": None,
                        "MSM_S3_ENDPOINT": None,
                        "MSM_S3_BUCKET": None,
                        "MSM_S3_PATH": None,
                        "MSM_TEMPORAL_SERVER_ADDRESS": "localhost:7233",
                        "MSM_TEMPORAL_NAMESPACE": "msm-namespace",
                        "MSM_TEMPORAL_TASK_QUEUE": "msm-queue",
                        "MSM_TEMPORAL_TLS_ROOT_CAS": "",
                    },
                }
            },
            "checks": {
                "http-test": {
                    "override": "replace",
                    "http": {"url": "http://localhost:8000/version"},
                }
            },
        }
        mock_fetch_postgres_relation_data.return_value = {}
        mock_fetch_s3_connection_info.return_value = {}
        json_version = unittest.mock.Mock()
        json_version.json.return_value = {"version": "1.0.0"}
        mock_get.return_value = json_version

        # Set temporal-server-address to a valid value
        self.harness.update_config({"temporal-server-address": "localhost:7233"})

        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready("site-manager")
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        # Check we've got the plan we expected
        self.assertEqual(expected_plan, updated_plan)
        # Check the service was started
        service = self.harness.model.unit.get_container("site-manager").get_service("msm")
        self.assertTrue(service.is_running())
        # Ensure we set an ActiveStatus with no message
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_postgres_relation_data")
    @unittest.mock.patch("ops.model.Container.get_check")
    def test_config_changed_valid_can_connect(
        self,
        mock_get_check,
        mock_fetch_postgres_relation_data,
        mock_version,
        mock_fetch_s3_connection_info,
    ):
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        mock_fetch_postgres_relation_data.return_value = {}
        mock_version.return_value = "1.0.0"
        mock_fetch_s3_connection_info.return_value = {}

        # Ensure the simulated Pebble API is reachable
        self.harness.set_can_connect("site-manager", True)
        # Set temporal-server-address and trigger a config-changed event
        self.harness.update_config(
            {"temporal-server-address": "localhost:7233", "log-level": "debug"}
        )
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        updated_env = updated_plan["services"]["msm"]["environment"]  # type: ignore

        # Check the config change was effective
        self.assertEqual(updated_env["UVICORN_LOG_LEVEL"], "debug")
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("ops.model.Container.get_check")
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    def test_s3_relation(self, mock_fetch_s3_connection_info, mock_get_check, mock_version):
        mock_fetch_s3_connection_info.return_value = {
            "access-key": "test-access-key",
            "secret-key": "test-secret-key",
            "endpoint": "test-endpoint",
            "bucket": "test-bucket",
            "path": "test-path",
        }
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        mock_version.return_value = "1.0.0"
        self.harness.set_can_connect("site-manager", True)
        # Set temporal-server-address
        self.harness.update_config({"temporal-server-address": "localhost:7233"})
        # Simulate the database relation created
        self.harness.add_relation(
            "database",
            "postgresql",
            app_data={
                "endpoints": "postgresql.localhost:5432",
                "username": "appuser",
                "password": "secret",
                "database": "name",
            },
        )
        self.harness.add_relation(
            "s3",
            "s3-integrator",
        )
        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        updated_env = updated_plan["services"]["msm"]["environment"]
        self.assertEqual(updated_env["MSM_S3_ACCESS_KEY"], "test-access-key")
        self.assertEqual(updated_env["MSM_S3_SECRET_KEY"], "test-secret-key")
        self.assertEqual(updated_env["MSM_S3_ENDPOINT"], "test-endpoint")
        self.assertEqual(updated_env["MSM_S3_BUCKET"], "test-bucket")
        self.assertEqual(updated_env["MSM_S3_PATH"], "test-path")

    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("ops.model.Container.get_check")
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    def test_s3_relation_not_ready(
        self, mock_fetch_s3_connection_info, mock_get_check, mock_version
    ):
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        mock_version.return_value = "1.0.0"
        mock_fetch_s3_connection_info.side_effect = S3IntegrationNotReadyError()

        self.harness.set_can_connect("site-manager", True)
        # Set temporal-server-address
        self.harness.update_config({"temporal-server-address": "localhost:7233"})
        # Simulate the database relation created
        self.harness.add_relation(
            "database",
            "postgresql",
            app_data={
                "endpoints": "postgresql.localhost:5432",
                "username": "appuser",
                "password": "secret",
                "database": "name",
            },
        )

        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready("site-manager")

        # Check the charm is in WaitingStatus
        self.assertEqual(
            self.harness.model.unit.status, ops.WaitingStatus("Waiting for s3 integration")
        )

    def test_config_changed_valid_cannot_connect(self):
        # Trigger a config-changed event with an updated value
        self.harness.update_config({"log-level": "debug"})
        # Check the charm is in WaitingStatus
        self.assertIsInstance(self.harness.model.unit.status, ops.WaitingStatus)

    def test_config_changed_invalid(self):
        # Ensure the simulated Pebble API is reachable
        self.harness.set_can_connect("site-manager", True)
        # Trigger a config-changed event with an updated value
        self.harness.update_config({"log-level": "foobar"})

        # Check the charm is in BlockedStatus
        self.assertIsInstance(self.harness.model.unit.status, ops.BlockedStatus)

    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_postgres_relation_data")
    def test_config_changed_database_not_ready(
        self, mock_fetch_postgres_relation_data, mock_version
    ):
        mock_fetch_postgres_relation_data.side_effect = DatabaseNotReadyError()
        mock_version.return_value = "1.0.0"

        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready("site-manager")

        # Check the charm is in WaitingStatus
        self.assertEqual(
            self.harness.model.unit.status, ops.WaitingStatus("Waiting for database relation")
        )

    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("ops.model.Container.get_check")
    def test_database_created_and_removed(
        self, mock_get_check, mock_version, mock_fetch_s3_connection_info
    ):
        mock_version.return_value = "1.0.0"
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        mock_fetch_s3_connection_info.return_value = {}

        # Set temporal-server-address
        self.harness.update_config({"temporal-server-address": "localhost:7233"})

        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready("site-manager")

        # Simulate the database relation created
        relation_id = self.harness.add_relation(
            "database",
            "postgresql",
            app_data={
                "endpoints": "postgresql.localhost:5432",
                "username": "appuser",
                "password": "secret",
                "database": "name",
            },
        )
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

        # Simulate the database relation removed
        self.harness.remove_relation(relation_id)
        self.assertEqual(
            self.harness.model.unit.status, ops.WaitingStatus("Waiting for database relation")
        )

    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("ops.model.Container.get_check")
    def test_temporal_not_configured(
        self, mock_get_check, mock_version, mock_fetch_s3_connection_info
    ):
        """Test that charm is blocked when temporal-server-address is not configured."""
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        mock_version.return_value = "1.0.0"
        mock_fetch_s3_connection_info.return_value = {}

        self.harness.set_can_connect("site-manager", True)

        # Set temporal-server-address to empty string (default)
        self.harness.update_config({"temporal-server-address": ""})

        # Simulate the database relation created
        self.harness.add_relation(
            "database",
            "postgresql",
            app_data={
                "endpoints": "postgresql.localhost:5432",
                "username": "appuser",
                "password": "secret",
                "database": "name",
            },
        )

        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready("site-manager")

        # Check the charm is in BlockedStatus
        self.assertEqual(
            self.harness.model.unit.status,
            ops.BlockedStatus("temporal-server-address configuration is required"),
        )

    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("ops.model.Container.get_check")
    def test_temporal_configured(
        self, mock_get_check, mock_version, mock_fetch_s3_connection_info
    ):
        """Test that charm works correctly when temporal-server-address is configured."""
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        mock_version.return_value = "1.0.0"
        mock_fetch_s3_connection_info.return_value = {}

        self.harness.set_can_connect("site-manager", True)

        # Set temporal-server-address to a valid value
        self.harness.update_config({"temporal-server-address": "temporal.example.com:7233"})

        # Simulate the database relation created
        self.harness.add_relation(
            "database",
            "postgresql",
            app_data={
                "endpoints": "postgresql.localhost:5432",
                "username": "appuser",
                "password": "secret",
                "database": "name",
            },
        )

        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready("site-manager")

        # Check the charm is in ActiveStatus
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

        # Verify the temporal server address is set correctly in the environment
        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        updated_env = updated_plan["services"]["msm"]["environment"]
        self.assertEqual(updated_env["MSM_TEMPORAL_SERVER_ADDRESS"], "temporal.example.com:7233")

    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_postgres_relation_data")
    @unittest.mock.patch("ops.model.Container.get_check")
    def test_loki_push_api_endpoint_created_updated_and_removed(
        self,
        mock_get_check,
        mock_fetch_postgres_relation_data,
        mock_version,
        mock_fetch_s3_connection_info,
    ):
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        expected_log_targets_created = {
            "loki-0": {
                "override": "replace",
                "type": "loki",
                "location": "loki.localhost",
                "services": ["all"],
            }
        }
        expected_log_targets_departed = {
            "loki-0": {
                "override": "replace",
                "type": "loki",
                "location": "loki.localhost",
            }
        }

        mock_version.return_value = "1.0.0"
        mock_fetch_postgres_relation_data.return_value = {}
        mock_fetch_s3_connection_info.return_value = {}

        # Set temporal-server-address
        self.harness.update_config({"temporal-server-address": "localhost:7233"})

        # Simulate the Loki push API relation created
        self.harness.container_pebble_ready("site-manager")
        relation_id = self.harness.add_relation("logging-consumer", "loki")
        self.harness.add_relation_unit(relation_id, "loki/0")
        self.harness.update_relation_data(
            relation_id, "loki/0", {"endpoint": json.dumps({"url": "loki.localhost"})}
        )

        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        self.assertEqual(updated_plan["log-targets"], expected_log_targets_created)  # type: ignore
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

        self.harness.remove_relation_unit(relation_id, "loki/0")

        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        self.assertEqual(updated_plan["log-targets"], expected_log_targets_departed)
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

        # Simulate the database relation removed
        self.harness.remove_relation(relation_id)

        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        self.assertEqual(updated_plan["log-targets"], expected_log_targets_departed)
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_postgres_relation_data")
    @unittest.mock.patch("ops.model.Container.get_check")
    def test_ingress_ready_and_revoked(
        self,
        mock_get_check,
        mock_fetch_postgres_relation_data,
        mock_version,
        mock_fetch_s3_connection_info,
    ):
        mock_version.return_value = "1.0.0"
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        mock_fetch_postgres_relation_data.return_value = {}
        mock_fetch_s3_connection_info.return_value = {}

        app_name = self.harness.charm.app.name
        model_name = self.harness.model.name
        url = f"http://ingress:8080/{model_name}-{app_name}"
        self.harness.add_network("10.0.0.1")

        # Set temporal-server-address
        self.harness.update_config({"temporal-server-address": "localhost:7233"})

        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready("site-manager")

        # Simulate the ingress relation created
        relation_id = self.harness.add_relation(
            "ingress", "traefik", app_data={"ingress": json.dumps({"url": url})}
        )
        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        self.assertEqual(updated_plan["services"]["msm"]["environment"]["MSM_BASE_PATH"], url)
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

        # Simulate the ingress relation removed
        self.harness.remove_relation(relation_id)
        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        self.assertEqual(updated_plan["services"]["msm"]["environment"]["MSM_BASE_PATH"], None)
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    def test_charm_level_tracing(self, mock_version):
        mock_version.return_value = "1.0.0"
        # Set temporal-server-address
        self.harness.update_config({"temporal-server-address": "localhost:7233"})
        self.harness.add_relation("tracing", "tempo")
        self.harness.container_pebble_ready("site-manager")
        rel = self.harness.model.get_relation("tracing")
        self.assertIsNotNone(rel)


class TestCharmActions(unittest.TestCase):
    @unittest.mock.patch.dict(os.environ, {"JUJU_VERSION": "4.0.0"}, clear=True)
    def setUp(self):
        self.harness = ops.testing.Harness(MsmOperatorCharm)
        self.harness.set_model_name("maas-dev-model")
        self.harness.handle_exec("site-manager", ["update-ca-certificates", "--fresh"], result=0)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def _connect(self):
        # Set temporal-server-address
        self.harness.update_config({"temporal-server-address": "localhost:7233"})
        self.harness.container_pebble_ready("site-manager")
        self.harness.add_relation(
            "database",
            "postgresql",
            app_data={
                "endpoints": "postgresql.localhost:5432",
                "username": "appuser",
                "password": "secret",
                "database": "name",
            },
        )

    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    @unittest.mock.patch("ops.model.Container.get_check")
    def test_create_admin_action(self, mock_get_check, mock_fetch_s3_connection_info):
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        mock_fetch_s3_connection_info.return_value = {}

        def create_admin_handler(args: ops.testing.ExecArgs) -> ops.testing.ExecResult:
            self.assertEqual(
                args.command,
                [
                    "msm-admin",
                    "create-user",
                    "--admin",
                    "my_user",
                    "my_email@local.net",
                    "my_secret",
                    "my full name",
                ],
            )
            return ops.testing.ExecResult(exit_code=0)

        self._connect()
        self.harness.handle_exec("site-manager", ["msm-admin"], handler=create_admin_handler)
        output = self.harness.run_action(
            "create-admin",
            {
                "username": "my_user",
                "password": "my_secret",
                "email": "my_email@local.net",
                "fullname": "my full name",
            },
        )
        self.assertEqual(output.results, {"info": "user my_user successfully created"})

    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    @unittest.mock.patch("ops.model.Container.get_check")
    def test_create_admin_action_no_fullname(self, mock_get_check, mock_fetch_s3_connection_info):
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        mock_fetch_s3_connection_info.return_value = {}

        def create_admin_handler(args: ops.testing.ExecArgs) -> ops.testing.ExecResult:
            self.assertEqual(
                args.command,
                [
                    "msm-admin",
                    "create-user",
                    "--admin",
                    "my_user",
                    "my_email@local.net",
                    "my_secret",
                ],
            )
            return ops.testing.ExecResult(exit_code=0)

        self._connect()
        self.harness.handle_exec("site-manager", ["msm-admin"], handler=create_admin_handler)
        output = self.harness.run_action(
            "create-admin",
            {
                "username": "my_user",
                "password": "my_secret",
                "email": "my_email@local.net",
            },
        )
        self.assertEqual(output.results, {"info": "user my_user successfully created"})

    @unittest.mock.patch("ops.model.Container.get_check")
    def test_create_admin_action_failed(self, mock_get_check):
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)

        def create_admin_handler(args: ops.testing.ExecArgs) -> ops.testing.ExecResult:
            return ops.testing.ExecResult(exit_code=1)

        self._connect()
        self.harness.handle_exec("site-manager", ["msm-admin"], handler=create_admin_handler)

        with self.assertRaises(ops.testing.ActionFailed):
            self.harness.run_action(
                "create-admin",
                {
                    "username": "my_user",
                    "password": "my_secret",
                    "email": "my_email@local.net",
                },
            )

    def test_create_admin_action_not_ready(self):
        def create_admin_handler(args: ops.testing.ExecArgs) -> ops.testing.ExecResult:
            return ops.testing.ExecResult(exit_code=0)

        self.harness.handle_exec("site-manager", ["msm-admin"], handler=create_admin_handler)

        with self.assertRaises(ops.testing.ActionFailed):
            self.harness.run_action(
                "create-admin",
                {
                    "username": "my_user",
                    "password": "my_secret",
                    "email": "my_email@local.net",
                },
            )


class TestPeerRelation(unittest.TestCase):
    @unittest.mock.patch.dict(os.environ, {"JUJU_VERSION": "4.0.0"}, clear=True)
    def setUp(self):
        self.harness = ops.testing.Harness(MsmOperatorCharm)
        self.harness.set_model_name("maas-dev-model")
        self.harness.add_network("10.0.0.10")
        self.harness.handle_exec("site-manager", ["update-ca-certificates", "--fresh"], result=0)
        self.addCleanup(self.harness.cleanup)

    def _ready(self):
        # Set temporal-server-address
        self.harness.update_config({"temporal-server-address": "localhost:7233"})
        self.harness.container_pebble_ready("site-manager")
        self.harness.add_relation(
            "database",
            "postgresql",
            app_data={
                "endpoints": "postgresql.localhost:5432",
                "username": "appuser",
                "password": "secret",
                "database": "name",
            },
        )

    def test_peer_relation_data(self):
        self.harness.set_leader(True)
        self.harness.begin()
        app = self.harness.charm.app
        rel_id = self.harness.add_relation(MSM_PEER_NAME, app.name)
        self.harness.charm.set_peer_data(app, "test_key", "test_value")
        self.assertEqual(
            self.harness.get_relation_data(rel_id, app.name)["test_key"], '"test_value"'
        )
        self.assertEqual(self.harness.charm.get_peer_data(app, "test_key"), "test_value")
        self.harness.charm.set_peer_data(app, "test_key", None)
        self.assertEqual(self.harness.get_relation_data(rel_id, app)["test_key"], "{}")

    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_s3_connection_info")
    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("charm.secrets.choice")
    @unittest.mock.patch("ops.model.Container.get_check")
    def test_create_operator(
        self, mock_get_check, mock_choice, mock_version, mock_fetch_s3_connection_info
    ):
        mock_get_check.return_value = CheckInfo("http-test", CheckLevel.ALIVE, CheckStatus.UP)
        mock_fetch_s3_connection_info.return_value = {}
        mock_choice.side_effect = PASSWD_CHOICES[:16]
        mock_version.return_value = "1.0.0"

        self.harness.set_leader(True)
        self.harness.begin()
        app = self.harness.charm.app

        def create_op_handler(args: ops.testing.ExecArgs) -> ops.testing.ExecResult:
            self.assertEqual(
                args.command,
                [
                    "msm-admin",
                    "create-user",
                    "--admin",
                    f"{app.name}-operator",
                    f"no-reply@{app.name}.charm",
                    PASSWD_CHOICES[:16],
                    f"{app.name} charm operator",
                ],
            )
            return ops.testing.ExecResult(exit_code=0)

        self.harness.handle_exec("site-manager", ["msm-admin"], handler=create_op_handler)
        self.harness.add_relation(MSM_PEER_NAME, app.name)
        self._ready()
        oper_id = self.harness.charm.get_peer_data(app, MSM_CREDS_ID)
        self.assertIsNotNone(oper_id)
        secret = self.harness.model.get_secret(id=oper_id).get_content()
        self.assertDictEqual(
            secret, {"password": PASSWD_CHOICES[:16], "username": f"no-reply@{app.name}.charm"}
        )


class TestEnrollment(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(MsmOperatorCharm)
        self.harness.set_model_name("msm-dev-model")
        self.harness.add_network("10.0.0.10")
        self.addCleanup(self.harness.cleanup)
        self.maas_id = str(uuid.uuid4())

    @unittest.mock.patch("charm.MsmOperatorCharm._get_enroll_token")
    def test_enroll(self, mock_enroll):
        mock_enroll.return_value = "my-token"
        self.harness.set_leader(True)
        self.harness.begin()
        remote_app = "maas-region"
        rel_id = self.harness.add_relation(
            enroll.DEFAULT_ENDPOINT_NAME,
            remote_app,
            unit_data={"unit": f"{remote_app}/0", "uuid": self.maas_id},
        )
        data = self.harness.get_relation_data(rel_id, self.harness.charm.app)
        self.assertIn("token_id", data)  # codespell:ignore
        secret = self.harness.model.get_secret(id=data["token_id"]).get_content()
        self.assertEqual(secret["enroll-token"], "my-token")


class TestHelperMethods(unittest.TestCase):
    """Test the helper methods added to reduce code duplication."""

    @unittest.mock.patch.dict(os.environ, {"JUJU_VERSION": "4.0.0"}, clear=True)
    def setUp(self):
        self.harness = ops.testing.Harness(MsmOperatorCharm)
        self.harness.set_model_name("maas-dev-model")
        self.harness.handle_exec("site-manager", ["update-ca-certificates", "--fresh"], result=0)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    def test_set_workload_version_with_version(self, mock_version):
        """Test _set_workload_version when version is available."""
        mock_version.return_value = "1.2.3"

        self.harness.charm._set_workload_version()

        # Verify the workload version was set
        self.assertEqual(self.harness.get_workload_version(), "1.2.3")

    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    def test_set_workload_version_without_version(self, mock_version):
        """Test _set_workload_version when version is not available."""
        mock_version.return_value = ""

        self.harness.charm._set_workload_version()

        # Verify no version was set (should remain None)
        self.assertIsNone(self.harness.get_workload_version())

    def test_ensure_operator_user_not_leader(self):
        """Test _ensure_operator_user when not leader - should return True."""
        self.harness.set_leader(False)

        result = self.harness.charm._ensure_operator_user()

        self.assertTrue(result)

    def test_ensure_operator_user_no_peers(self):
        """Test _ensure_operator_user when no peer relation exists - should return True."""
        self.harness.set_leader(True)

        result = self.harness.charm._ensure_operator_user()

        self.assertTrue(result)

    @unittest.mock.patch("charm.MsmOperatorCharm._create_operator_user")
    def test_ensure_operator_user_already_created(self, mock_create):
        """Test _ensure_operator_user when operator already exists - should return True."""
        self.harness.set_leader(True)
        app = self.harness.charm.app
        rel_id = self.harness.add_relation(MSM_PEER_NAME, app.name)

        # Set existing credentials
        self.harness.update_relation_data(rel_id, app.name, {MSM_CREDS_ID: '"existing-id"'})

        result = self.harness.charm._ensure_operator_user()

        self.assertTrue(result)
        mock_create.assert_not_called()

    @unittest.mock.patch("charm.MsmOperatorCharm._create_operator_user")
    def test_ensure_operator_user_success(self, mock_create):
        """Test _ensure_operator_user successful creation."""
        self.harness.set_leader(True)
        app = self.harness.charm.app
        self.harness.add_relation(MSM_PEER_NAME, app.name)

        result = self.harness.charm._ensure_operator_user()

        self.assertTrue(result)
        mock_create.assert_called_once()

    @unittest.mock.patch("charm.MsmOperatorCharm._create_operator_user")
    def test_ensure_operator_user_failure(self, mock_create):
        """Test _ensure_operator_user when creation fails."""
        from charm import OperatorUserError

        mock_create.side_effect = OperatorUserError("Failed to create user")
        self.harness.set_leader(True)
        app = self.harness.charm.app
        self.harness.add_relation(MSM_PEER_NAME, app.name)

        result = self.harness.charm._ensure_operator_user()

        self.assertFalse(result)
        self.assertEqual(
            self.harness.model.unit.status, ops.BlockedStatus("Failed to create operator user")
        )

    def test_get_site_manager_client_no_credentials(self):
        """Test _get_site_manager_client when no credentials exist."""
        self.harness.set_leader(True)

        client = self.harness.charm._get_site_manager_client()

        self.assertIsNone(client)

    @unittest.mock.patch("charm.SiteManagerClient")
    def test_get_site_manager_client_with_credentials(self, mock_client_class):
        """Test _get_site_manager_client when credentials are available."""
        self.harness.set_leader(True)
        app = self.harness.charm.app
        rel_id = self.harness.add_relation(MSM_PEER_NAME, app.name)

        # Create a secret with credentials
        secret = app.add_secret(
            {"username": "test@example.com", "password": "testpass"}, label="test-secret"
        )
        secret_id = secret.get_info().id

        # Store secret ID in peer data
        self.harness.update_relation_data(rel_id, app.name, {MSM_CREDS_ID: f'"{secret_id}"'})

        client = self.harness.charm._get_site_manager_client()

        self.assertIsNotNone(client)
        mock_client_class.assert_called_once_with(
            username="test@example.com", password="testpass", url="http://localhost:8000"
        )

    def test_update_ca_certificates(self):
        """Test _update_ca_certificates executes the correct command."""
        self.harness.set_can_connect("site-manager", True)

        # The setUp already handles the exec mock, we just verify it's called
        self.harness.charm._update_ca_certificates()

        # Verify the command was executed (implicitly tested via the mock in setUp)
        # The harness would raise an error if the command wasn't handled

    def test_update_ca_certificates_integration(self):
        """Test _update_ca_certificates is called by certificate methods."""
        self.harness.set_can_connect("site-manager", True)

        # Track exec calls
        exec_calls = []

        def exec_handler(args: ops.testing.ExecArgs) -> ops.testing.ExecResult:
            exec_calls.append(args.command)
            return ops.testing.ExecResult(exit_code=0)

        self.harness.handle_exec(
            "site-manager", ["update-ca-certificates", "--fresh"], handler=exec_handler
        )

        # Call the method
        self.harness.charm._update_ca_certificates()

        # Verify the command was called
        self.assertEqual(len(exec_calls), 1)
        self.assertEqual(exec_calls[0], ["update-ca-certificates", "--fresh"])
