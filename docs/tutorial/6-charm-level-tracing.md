# Set up Charm-Level Tracing

While developing and debugging, it can be helpful to see traces of the MAAS Site Manager charm's workload. In this section, we will set up some necessary Juju components and relate them to MAAS Site Manager K8s in order to see these traces.

[note]
**Note**: You must have completed the last section if you would like to enable charm-level tracing.
[/note]

Before beginning, ensure you are working in the `cos-lite` model by running:

```bash
juju switch cos-lite
```

## Deploy Tempo K8s

First, deploy the Tempo Coordinator and Worker charms, and wait for them to report as `blocked/idle`:

```bash
juju deploy tempo-coordinator-k8s --channel edge --trust tempo
juju deploy tempo-worker-k8s --channel edge --trust tempo-worker
juju status --watch 5s
```

Next, integrate the coordinator and worker charms:

```bash
juju integrate tempo tempo-worker
```

## Deploy Minio and S3

Next, create an access and secret key and store them as environment variables. The secret key must be at least 8 characters.

```bash
export ACCESS_KEY=accesskey
export SECRET_KEY=mysoverysecretkey
```

Next, deploy Minio with the access and secret key created above. Wait for it to report as `active/idle`.
```bash
juju deploy minio --channel edge --trust --config access-key=$ACCESS_KEY --config secret-key=$SECRET_KEY
juju status --watch 5s
```

Next, deploy S3 and wait for it to report as `blocked/idle`:

```bash
juju deploy s3-integrator --channel edge --trust s3
juju status --watch 5s
```

Once S3 is in a `blocked/idle` state, run the `sync-s3-credentials` action:

```bash
juju run s3/leader sync-s3-credentials access-key=$ACCESS_KEY secret-key=$SECRET_KEY
```

## Create a Bucket in Minio

Next, we will create a bucket in Minio. First, store the IP address of the `minio/0` **unit** (NOT the Minio application) reported by `juju status` in an environment variable:

```
juju status # Note the IP of the minio/0 unit
export MINIO_IP="10.1.64.154"
```

Then, we will run a short Python script to create the bucket. Before doing so, ensure you have installed the `minio` pip package:

```bash
pip install minio
```

Now, we can finally create our bucket with this Python script. Be sure to run this in the same terminal session where we created our environment variables earlier (`ACCESS_KEY`, `SECRET_KEY`, and `MINIO_IP`).

```python
from minio import Minio
from os import getenv

address = getenv("MINIO_IP")
bucket_name = "tempo"

mc_client = Minio(
    f"{address}:9000",
    access_key=getenv("ACCESS_KEY"),
    secret_key=getenv("SECRET_KEY"),
    secure=False,
)

found = mc_client.bucket_exists(bucket_name)
if not found:
    mc_client.make_bucket(bucket_name)
```

Next, we provide a configuration to S3 and some relations for the charms we deployed above:

```bash
juju config s3 endpoint=minio-0.minio-endpoints.cos-lite.svc.cluster.local:9000 bucket=tempo
juju integrate tempo s3
juju integrate tempo:ingress traefik
juju relate tempo:grafana-source grafana:grafana-source
```
Finally, relate MAAS Site Manager K8s with Tempo:

```bash
juju offer tempo:tracing
juju switch msm
juju integrate maas-site-manager-k8s admin/cos-lite.tempo
```

Charm-level tracing also requires a reverse-proxy service, which will be set up in the next section.

**Next Step:** [Set up a reverse-proxy](/t/15828)
