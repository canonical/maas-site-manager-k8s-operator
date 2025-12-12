# Set up a Reverse-Proxy Service

MAAS Site Manager requires a reverse-proxy service. The easiest way to get one is reusing the Traefik service that comes with COS. If you have set up charm-level tracing, you must use Traefik for the reverse-proxy service.

If you haven't deployed COS, you can skip to the "Deploy Traefik manually" section below.

Before starting, ensure you are working in the `cos-lite` model:

```bash
juju switch cos-lite
```

Next, provide the `ingress` offer for Traefik:

```bash
juju offer traefik:ingress
```

Finally, switch back to the `msm` model and integrate MAAS Site Manager K8s with the offer above:

```bash
juju switch msm
juju integrate maas-site-manager-k8s admin/cos-lite.traefik
```

## Deploy Traefik manually

If you have deployed COS and provided the integration as shown above, you can skip this section.

First, enable the `metallb` microk8s addon:

```bash
IPADDR=$(ip -4 -j route get 2.2.2.2 | jq -r '.[] | .prefsrc')
sudo microk8s enable metallb:$IPADDR-$IPADDR
```

Then, deploy `traefik-k8s` in the `msm` model:

```bash
juju switch msm
juju deploy traefik-k8s
```


**Next Step:** [Deploy MAAS Site Manager](/t/19564)
