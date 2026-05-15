# Deploy MAAS Site Manager

In this section, we'll deploy MAAS Site Manager and its Temporal worker.

## Deploy Temporal Worker

First, add a new model for the Temporal worker and deploy the charm:

```bash
juju add-model worker
juju deploy temporal-worker-k8s --channel 1.0/stable --base ubuntu@24.04 --resource temporal-worker-image=ghcr.io/canonical/maas-site-manager:1.1.0
```

Next, configure the worker charm and relate the temporal server charm to the worker charm

```bash
juju config temporal-worker-k8s queue=msm-queue namespace=msm-namespace
juju relate temporal-worker-k8s admin/temporal.temporal-k8s
```

We will also need the `temporal-worker-info` relation in another model, so create an offer for it:

```bash
juju offer temporal-worker-k8s:temporal-worker-info
```

## Deploy MAAS Site Manager

Finally, we are ready to deploy MAAS Site Manager:

```bash
juju switch msm
juju deploy maas-site-manager-k8s --channel latest/edge
```

Next, we provide integrations for MAAS Site Manager:

```bash
juju integrate postgresql-k8s maas-site-manager-k8s
juju integrate traefik-k8s maas-site-manager-k8s
juju integrate maas-site-manager-k8s s3-integrator
juju relate maas-site-manager-k8s admin/worker.temporal-worker-k8s
```

## Log In

Now all of our applications are deployed and ready to use. The final step is to create an admin user in MAAS Site Manager so that we can log in:

```bash
juju run maas-site-manager-k8s/0 create-admin username=myusername password=mypassword fullname="Full Name" email=full.name@company.com
```

[note]
**Note:** username, password, and email are required parameters in the command above.
[/note]

Now, we can log in to the MAAS Site Manager webpage with the email and password created above by visiting the URL below in your web browser. Replace `$IPADDR` with the IP address of your `charm-dev-vm` virtual machine. You can see this IP address by running `multipass list` on your **host machine**.

`http://$IPADDR/msm-maas-site-manager-k8s`


**Optional Next Step**: [Setup Monitoring](/t/15821)
