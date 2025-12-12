# Deploy PostgreSQL

In this section, we'll deploy PostgreSQL and create a Juju offer.

Before starting, make sure you are working in the correct Juju model:

```bash
juju switch msm
```

## Deploy PostgreSQL

To deploy PostgreSQL, run the following:

```bash
juju deploy postgresql-k8s --channel 14/stable --trust
```

Then, run `juju status --watch 5s` and wait for the `postgresql-k8s/0` unit to report as `waiting/idle`.

[note]
**Note**: While waiting, `postgresql-k8s` may enter a blocked state, but will return to `waiting/idle` after some time
[/note]


## Create a Juju offer

Next, create a Juju offer for Postgresql:

```bash
juju offer postgresql-k8s:database pgsql
```

**Next Step**: [Deploy Object Storage and S3 Integrator](/t/17909)
