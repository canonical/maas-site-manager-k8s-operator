# Charmed MAAS Site Manager K8s Documentation

Charmed MAAS Site Manager K8s is an operator for deploying and operating MAAS Site Manager, a tool for managing multiple MAAS installations (called 'sites') at the same time. It centralizes image management for all enrolled sites and provides a statistical overview of all connected sites and their machines' statuses, with more features coming soon.

This charm integrates with [postgresql-k8s](https://charmhub.io/postgresql-k8s) for storing Site information, [traefik-k8s](https://charmhub.io/traefik-k8s) as a reverse-proxy service, [loki-k8s](https://charmhub.io/loki-k8s) for logging services, [prometheus-k8s](https://charmhub.io/prometheus-k8s) for metrics scraping, [tempo](https://charmhub.io/tempo-coordinator-k8s) for charm-level tracing, and [grafana-k8s](https://charmhub.io/grafana-k8s) for dashboards.

[note ]
This operator is built for **Kubernetes**.

**IAAS/VM** deployments are not supported.
[/note]

[note]
Juju version 3.6 is required for this charm. Versions 3.5 and earlier are not supported.
[/note]

# Navigation

[details=Navigation]

|Level | Path | Navlink|
|--- | --- | ---|
|1 | tutorial | [Tutorial]()|
|2 | t-overview | [Overview](/t/15819)|
|2 | t-set-up | [1. Set up environment](/t/15820)|
|2 | t-deploy-postgresql | [2. Deploy PostgreSQL](/t/15822)|
|2 | t-deploy-s3-integrator | [3. Deploy Object Storage and S3 Integrator](/t/17909)|
|2 | t-deploy-temporal | [4. Deploy Temporal](/t/17910)|
|2 | t-deploy-cos-lite | [5. Deploy COS Lite Bundle](/t/15821)|
|2 | t-set-up-tracing | [6. Set up Charm-Level Tracing](/t/15827)|
|2 | t-reverse-proxy | [7. Set up a Reverse-Proxy](/t/15828)|
|2 | t-deploy-msm | [8. Deploy MAAS Site Manager](/t/19564)|
