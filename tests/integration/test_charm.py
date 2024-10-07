#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import subprocess
from pathlib import Path

import pytest
import yaml
from minio import Minio
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    await ops_test.track_model("msm")
    # Build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {
        "site-manager-image": METADATA["resources"]["site-manager-image"]["upstream-source"]
    }

    # Deploy the charm and wait for waiting/idle status
    await asyncio.gather(
        ops_test.model.deploy(charm, resources=resources, application_name=APP_NAME),
        ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="waiting", raise_on_blocked=True, timeout=1000
        ),
    )


@pytest.mark.abort_on_fail
async def test_database_integration(ops_test: OpsTest):
    """Verify that the charm integrates with the database.

    Assert that the charm is active if the integration is established.
    """
    await ops_test.model.deploy(
        "postgresql-k8s",
        application_name="postgresql-k8s",
        channel="14/stable",
        trust=True,
    )
    await ops_test.model.integrate(f"{APP_NAME}", "postgresql-k8s")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", raise_on_blocked=True, timeout=1000
    )


# TODO: uncomment once we can use self-hosted GH runners
# @pytest.mark.abort_on_fail
# async def test_charm_tracing_config(ops_test: OpsTest):
#     await ops_test.track_model("cos-lite")
#     subprocess.check_call(
#         [
#             "curl",
#             "-L",
#             "https://raw.githubusercontent.com/canonical/cos-lite-bundle/main/overlays/offers-overlay.yaml",
#             "-O",
#         ]
#     )
#     subprocess.check_call(
#         [
#             "curl",
#             "-L",
#             "https://raw.githubusercontent.com/canonical/cos-lite-bundle/main/overlays/storage-small-overlay.yaml",
#             "-O",
#         ]
#     )
#     await ops_test.model.deploy(
#         "cos-lite",
#         overlays=["./offers-overlay.yaml", "storage-small-overlay.yaml"],
#         trust=True,
#         channel="latest/edge",
#     )
#     await ops_test.model.create_offer("prometheus:metrics-endpoint", "prometheus-scrape")
#     await ops_test.model.deploy(
#         "tempo-coordinator-k8s", application_name="tempo", channel="latest/edge", trust=True
#     )
#     await ops_test.model.deploy(
#         "tempo-worker-k8s", application_name="tempo-worker", channel="latest/edge", trust=True
#     )
#     await ops_test.model.wait_for_idle(
#         apps=["tempo", "tempo-worker"], status="blocked", raise_on_blocked=False, timeout=1000
#     )
#     await ops_test.model.integrate("tempo", "tempo-worker")
#     minio_config = {"access-key": "accesskey", "secret-key": "mysoverysecretkey"}
#     await ops_test.model.deploy(
#         "minio", channel="latest/edge", trust=True, config=minio_config
#     )
#     await ops_test.model.wait_for_idle(
#         apps=["minio"], status="active", raise_on_blocked=True, timeout=1000
#     )

#     await ops_test.model.deploy(
#         "s3-integrator",
#         application_name="s3",
#         channel="latest/edge",
#         trust=True,
#     )
#     await ops_test.model.wait_for_idle(
#         apps=["s3"], status="blocked", raise_on_blocked=False, timeout=1000
#     )
#     await ops_test.juju(
#         "run s3/leader sync-s3-credentials access-key=accesskey secret-key=mysoverysecretkey"
#     )

#     # get the minio unit IP
#     out = subprocess.check_output(
#         ["juju", "status", "minio", "--model", "cos-lite", "--format", "json"]
#     )
#     address = json.loads(out)["applications"]["minio"]["units"]["minio/0"]["address"]
#     # ["applications"]["minio"]["address"]
#     bucket_name = "tempo"

#     mc_client = Minio(
#         f"{address}:9000",
#         access_key="accesskey",
#         secret_key="mysoverysecretkey",
#         secure=False,
#     )
#     if not mc_client.bucket_exists(bucket_name):
#         mc_client.make_bucket(bucket_name)

#     await ops_test.juju(
#         f"config s3 endpoint=minio-0.minio-endpoints.{ops_test.model.name}.svc.cluster.local:9000 bucket=tempo"
#     )
#     await ops_test.model.integrate("tempo", "s3")
#     await ops_test.model.integrate("tempo:ingress", "traefik")
#     await ops_test.model.create_offer("traefik:ingress")
#     cos_lite_model_name = ops_test.model.name
#     await ops_test.track_model("msm")

#     await ops_test.model.integrate(f"{APP_NAME}", f"{cos_lite_model_name}.traefik")
