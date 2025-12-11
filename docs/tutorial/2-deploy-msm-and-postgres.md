# Deploy MAAS Site Manager and PostgreSQL

In this section, we'll deploy MAAS Site Manager and PostgreSQL, and create an integration between the two.

Before starting, make sure you are working in the correct Juju model:

```bash
juju switch msm
```

## Deploy PostgreSQL

To deploy PostgreSQL, run the following:

```bash
juju deploy postgresql-k8s --channel 14/stable
```

Then, run `juju status --watch 5s` and wait for the `postgresql-k8s/0` unit to report as `waiting/idle`.

[note]
**Note**: While waiting, `postgresql-k8s` may enter a blocked state, but will return to `waiting/idle` after some time
[/note]

## Deploy MAAS Site Manager

To deploy MAAS Site Manager and integrate it with PostgreSQL, run the following:

```bash
juju deploy maas-site-manager-k8s --channel latest/edge
juju integrate postgresql-k8s maas-site-manager-k8s
```

Finally, wait for both units to report as `active/idle`:

```bash
juju status --watch 2s
```

**Next Step**: [Deploy Object Storage and S3 Integrator](/t/17909)
