# Monitoring

The MAAS Site Manager charm supports integration with the COS Lite bundle and tracing via the Tempo HA charm. Follow [this](https://discourse.charmhub.io/t/tutorial-deploy-tempo-ha-on-top-of-cos-lite/15489) guide to set up COS Lite and Tempo HA.

## Integrate with MAAS Site Manager K8s

Once you have the COS Lite bundle and Tempo HA deployed, create the following integrations for MAAS Site Manager (assuming the Juju model you used is called `cos-lite`):

```bash
juju switch msm
juju integrate maas-site-manager-k8s admin/cos-lite.loki-logging
juju integrate maas-site-manager-k8s admin/cos-lite.grafana-dashboards
juju integrate maas-site-manager-k8s admin/cos-lite.prometheus-scrape
juju integrate maas-site-manager-k8s admin/cos-lite.tempo
```
