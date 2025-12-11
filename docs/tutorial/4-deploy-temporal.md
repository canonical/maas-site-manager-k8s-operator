# Deploy Temporal

MAAS Site Manager uses Temporal Workflows for long-running tasks. Follow the steps below to deploy charmed Temporal.


## Deploy Temporal Server

First, add another Juju model for Temporal, deploy the Temporal server k8s charm, and wait for it to enter a `blocked/idle` state:

```bash
juju add-model temporal
juju deploy temporal-k8s --config num-history-shards=4
juju status --watch 5s  # wait for blocked/idle
```

Next, switch back to the `msm` model and create an offer for `postgresql-k8s`:

```bash
juju switch msm
juju offer postgresql-k8s:database pgsql
```

Switch back to the `temporal` model and consume the offer:

```bash
juju consume admin/msm.pgsql
juju relate temporal-k8s:db admin/msm.pgsql
juju relate temporal-k8s:visibility admin/msm.pgsql
```

Next, deploy the Temporal Admin charm and relate it to temporal-k8s when it enters a blocked/idle state:

```bash
juju deploy temporal-admin-k8s
juju status --watch 5s  # wait for blocked/idle from temporal-admin-k8s
juju relate temporal-k8s:admin temporal-admin-k8s:admin
```

Next, create a Temporal namespace for MAAS Site Manager called `msm-namespace`:

```bash
juju run temporal-admin-k8s/0 tctl args="--ns msm-namespace namespace register -rd 3" --wait 1m
```

## Deploy Temporal UI

For debugging Temporal workflows, deploy the Temporal UI charm and relate it to `temporal-k8s` once it enters a blocked/idle state.

```bash
juju deploy temporal-ui-k8s --config external-hostname=temporal-ui
juju status --watch 2s  # wait for blocked/idle from temporal-ui-k8s
juju relate temporal-k8s:ui temporal-ui-k8s:ui
```

## Deploy Ingress Controller

To enable TLS connections, you must have a TLS certificate stored as a k8s secret. You can create a self-signed certificate and store it in a secret as follows:

```bash
# Generate private key
openssl genrsa -out server.key 2048
# Generate a certificate signing request
openssl req -new -key server.key -out server.csr -subj "/CN=temporal"
# Create self-signed certificate
openssl x509 -req -days 365 -in server.csr -signkey server.key -out server.crt -extfile <(printf "subjectAltName=DNS:temporal")
# Create a k8s secret
microk8s kubectl -n temporal create secret tls temporal-tls --cert=server.crt --key=server.key
```

Repeat this process for the Temporal UI:

```bash
# Generate private key
openssl genrsa -out server.key 2048
# Generate a certificate signing request
openssl req -new -key server.key -out server.csr -subj "/CN=temporal-ui"
# Create self-signed certificate
openssl x509 -req -days 365 -in server.csr -signkey server.key -out server.crt -extfile <(printf "subjectAltName=DNS:temporal-ui")
# Create a k8s secret
microk8s kubectl -n temporal create secret tls temporal-ui-tls --cert=server.crt --key=server.key
```

Next, enable ingress and deploy two instances of `nginx-ingress-integrator` under the names `ingress` and `ingress-ui` and wait for them to enter an `waiting/idle` state:

```bash
sudo microk8s enable ingress
juju deploy nginx-ingress-integrator ingress --channel edge --trust --config service-hostname=temporal --config tls-secret-name=temporal-tls
juju deploy nginx-ingress-integrator ingress-ui --channel edge --trust --config service-hostname=temporal-ui --config tls-secret-name=temporal-ui-tls
juju status --watch 5s
```

Next, relate `temporal-ui-k8s` and `temporal-k8s` to the respective `nginx-ingress-integrator` applications:

```bash
juju relate temporal-k8s ingress
juju relate temporal-ui-k8s ingress-ui
```

Finally, configure the `tls-secret-name` for `temporal-k8s` and `temporal-ui-k8s`:

```bash
juju config temporal-k8s tls-secret-name=temporal-tls
juju config temporal-ui-k8s tls-secret-name=temporal-ui-tls
```

To verify that ingress resources were created correctly, run the following command:

```bash
microk8s kubectl describe ingress -n temporal
```

You should see an output similar to below, with differing IP addresses:

```
Name:             temporal-k8s-ingress
Labels:           app.juju.is/created-by=nginx-ingress-integrator
                  nginx-ingress-integrator.charm.juju.is/managed-by=nginx-ingress-integrator
Namespace:        temporal-model
Address:          127.0.0.1
Ingress Class:    public
Default backend:  <default>
TLS:
  temporal-tls terminates temporal-k8s
Rules:
  Host          Path  Backends
  ----          ----  --------
  temporal-k8s
                /   temporal-k8s-service:7233 (10.1.232.64:7233)
Annotations:    nginx.ingress.kubernetes.io/backend-protocol: GRPC
                nginx.ingress.kubernetes.io/proxy-body-size: 20m
                nginx.ingress.kubernetes.io/proxy-read-timeout: 60
                nginx.ingress.kubernetes.io/rewrite-target: /
Events:         <none>


Name:             temporal-ui-k8s-ingress
Labels:           app.juju.is/created-by=nginx-ingress-integrator
                  nginx-ingress-integrator.charm.juju.is/managed-by=nginx-ingress-integrator
Namespace:        temporal-model
Address:          127.0.0.1
Ingress Class:    public
Default backend:  <default>
TLS:
  temporal-tls terminates temporal-ui-k8s
Rules:
  Host             Path  Backends
  ----             ----  --------
  temporal-ui-k8s
                   /   temporal-ui-k8s-service:8080 (10.1.232.72:8080)
Annotations:       nginx.ingress.kubernetes.io/backend-protocol: HTTP
                   nginx.ingress.kubernetes.io/proxy-body-size: 20m
                   nginx.ingress.kubernetes.io/proxy-read-timeout: 60
                   nginx.ingress.kubernetes.io/rewrite-target: /
Events:            <none>
```

## Deploy Temporal Worker

Next, add a new model for the temporal worker and deploy the charm:

```bash
juju add-model worker
juju deploy temporal-worker-k8s --resource temporal-worker-image=ghcr.io/canonical/msm-temporal-worker:1.0
```

From the output of the `microk8s kubectl describe ingress -n temporal` command above, note the IP address and port of the `temporal-k8s` service (in the output above, this is `10.1.232.64:7233`) and configure the `temporal-worker` charm:

```bash
juju config temporal-worker-k8s host=$TEMPORAL_IP:$TEMPORAL_PORT queue=msm-queue namespace=msm-namespace
```

Similarly, we need to update the `maas-site-manager-k8s` config:

```bash
juju switch msm
juju config maas-site-manager-k8s temporal-server-address=$TEMPORAL_IP:$TEMPORAL_PORT
```

**Next Step**: [Deploy COS Lite](/t/15821)
