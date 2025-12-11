# Deploy COS Lite Bundle

In this section, we'll deploy the COS Lite bundle and set it up for integration with MAAS Site Manager K8s. This step is optional, but highly recommended. If you plan to use charm-level tracing (next section), this step is required. Also, MAAS Site Manager K8s requires a reverse proxy service, which we will set up in a later section. If you wish to follow our tutorial for setting up a reverse proxy service, you will need to complete this section.

All commands below should be executed in a shell inside your `charm-dev-vm`.

## Enable Microk8s addons

First, enable `dns`, `hostpath-storage`, and `metallb` Microk8s addons:

```bash
sudo microk8s enable dns
sudo microk8s enable hostpath-storage
IPADDR=$(ip -4 -j route get 2.2.2.2 | jq -r '.[] | .prefsrc')
sudo microk8s enable metallb:$IPADDR-$IPADDR
```

Next, ensure that these have been successfully rolled out:

```bash
microk8s kubectl rollout status deployments/hostpath-provisioner -n kube-system -w
microk8s kubectl rollout status deployments/coredns -n kube-system -w
microk8s kubectl rollout status daemonset.apps/speaker -n metallb-system -w
```

## Deploy COS Lite bundle with overlays

Next, download the `storage-small` (for non-production environments) and `offers` overlays, and deploy COS Lite:

```bash
# get bundle default offer definitions
curl -L https://raw.githubusercontent.com/canonical/cos-lite-bundle/main/overlays/offers-overlay.yaml -O
# reduce COS storage requirements (non production env)
curl -L https://raw.githubusercontent.com/canonical/cos-lite-bundle/main/overlays/storage-small-overlay.yaml -O
# deploy COS Lite
juju switch cos-lite
juju deploy cos-lite --trust --overlay ./offers-overlay.yaml --overlay ./storage-small-overlay.yaml
juju offer prometheus:metrics-endpoint prometheus-scrape
```

Deployment will take some time to complete; run the following command and wait for each unit to report as `active/idle`:

```bash
juju status --watch 5s
```

## Integrate with MAAS Site Manager K8s

Next, create the following integrations for MAAS Site Manager:

```bash
juju switch msm
juju integrate maas-site-manager-k8s admin/cos-lite.loki-logging
juju integrate maas-site-manager-k8s admin/cos-lite.grafana-dashboards
juju integrate maas-site-manager-k8s admin/cos-lite.prometheus-scrape
```

**Next Step**: [Set up charm-level tracing](/t/15827)
