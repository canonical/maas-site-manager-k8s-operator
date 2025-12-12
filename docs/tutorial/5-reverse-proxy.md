# Set up a Reverse-Proxy Service

MAAS Site Manager requires a reverse-proxy service. Follow these steps to set one up. Alternatively, you may use the `traefik-k8s` reverse-proxy setup by the COS Lite bundle, which we link to at the end of this tutorial.

## Deploy Traefik manually

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
