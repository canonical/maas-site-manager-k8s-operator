# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
import os
import unittest
import unittest.mock

import ops
import ops.testing

from charm import DatabaseNotReadyError, MsmOperatorCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(MsmOperatorCharm)
        self.harness.set_model_name("maas-dev-model")
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @unittest.mock.patch("charm.requests.get", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_postgres_relation_data")
    def test_pebble_layer(self, mock_fetch_postgres_relation_data, mock_get):
        # Expected plan after Pebble ready with default config
        expected_plan = {
            "services": {
                "msm": {
                    "override": "replace",
                    "summary": "MAAS Site Manager",
                    "command": "uvicorn --host 0.0.0.0 --port 8000 --factory --loop uvloop msm.api:create_app",
                    "startup": "enabled",
                    "environment": {
                        "UVICORN_LOG_LEVEL": "info",
                        "MSM_DB_HOST": None,
                        "MSM_DB_PORT": None,
                        "MSM_DB_USER": None,
                        "MSM_DB_NAME": None,
                        "MSM_DB_PASSWORD": None,
                        "MSM_BASE_PATH": None,
                    },
                }
            },
        }
        mock_fetch_postgres_relation_data.return_value = {}
        json_version = unittest.mock.Mock()
        json_version.json.return_value = {"version": "1.0.0"}
        mock_get.return_value = json_version

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

    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_postgres_relation_data")
    def test_config_changed_valid_can_connect(
        self, mock_fetch_postgres_relation_data, mock_version
    ):
        mock_fetch_postgres_relation_data.return_value = {}
        mock_version.return_value = "1.0.0"

        # Ensure the simulated Pebble API is reachable
        self.harness.set_can_connect("site-manager", True)
        # Trigger a config-changed event with an updated value
        self.harness.update_config({"log-level": "debug"})
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        updated_env = updated_plan["services"]["msm"]["environment"]

        # Check the config change was effective
        self.assertEqual(updated_env["UVICORN_LOG_LEVEL"], "debug")
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

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

    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    def test_database_created_and_removed(self, mock_version):
        mock_version.return_value = "1.0.0"

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

    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_postgres_relation_data")
    def test_loki_push_api_endpoint_created_and_removed(
        self, mock_fetch_postgres_relation_data, mock_version
    ):
        expected_log_targets_created = {
            "loki-0": {
                "override": "replace",
                "type": "loki",
                "location": "loki.localhost",
                "services": ["all"],
            }
        }
        # expected_log_targets_departed = {
        #     "loki-0": {
        #         "override": "replace",
        #         "type": "loki",
        #         "location": "loki.localhost",
        #         "services": [],
        #     }
        # }

        mock_version.return_value = "1.0.0"
        mock_fetch_postgres_relation_data.return_value = {}

        # Simulate the Loki push API relation created
        relation_id = self.harness.add_relation(
            "logging-consumer",
            "loki",
            unit_data={"endpoint": json.dumps({"url": "loki.localhost"})},
        )
        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready("site-manager")

        updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        self.assertEqual(updated_plan["log-targets"], expected_log_targets_created)
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

        # Simulate the database relation removed
        self.harness.remove_relation(relation_id)

        # TODO (@skatsaounis): fix me
        # updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        # self.assertEqual(updated_plan["log-targets"], expected_log_targets_departed)
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    @unittest.mock.patch("charm.MsmOperatorCharm.version", new_callable=unittest.mock.PropertyMock)
    @unittest.mock.patch("charm.MsmOperatorCharm._fetch_postgres_relation_data")
    def test_ingress_ready_and_revoked(self, mock_fetch_postgres_relation_data, mock_version):
        mock_version.return_value = "1.0.0"
        mock_fetch_postgres_relation_data.return_value = {}

        # Simulate the Loki push API relation created
        # app_name = self.harness.charm.app.name
        # model_name = self.harness.model.name
        # url = f"http://ingress:80/{model_name}-{app_name}"
        self.harness.add_network("10.0.0.1")

        self.harness.container_pebble_ready("site-manager")
        # relation_id = self.harness.add_relation(
        #     "ingress", "traefik", unit_data={"ingress": json.dumps({"url": url})}
        # )
        # Simulate the container coming up and emission of pebble-ready event

        # updated_plan = self.harness.get_container_pebble_plan("site-manager").to_dict()
        # self.assertEqual(updated_plan["services"]["msm"]["environment"]["MSM_BASE_PATH"], url)
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())


class TestCharmActions(unittest.TestCase):

    @unittest.mock.patch.dict(os.environ, {"JUJU_VERSION": "4.0.0"}, clear=True)
    def setUp(self):
        self.harness = ops.testing.Harness(MsmOperatorCharm)
        self.harness.set_model_name("maas-dev-model")
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def _connect(self):
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

    def test_create_admin_action(self):
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

    def test_create_admin_action_no_fullname(self):
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

    def test_create_admin_action_failed(self):
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
