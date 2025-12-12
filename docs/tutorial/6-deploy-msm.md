# Deploy MAAS Site Manager

In this section, we'll deploy MAAS Site Manager and its Temporal worker.

## Deploy Temporal Worker

First, add a new model for the Temporal worker and deploy the charm:

```bash
juju add-model worker
juju deploy temporal-worker-k8s --resource temporal-worker-image=ghcr.io/canonical/maas-site-manager:0.1
```

From the output of the `microk8s kubectl describe ingress -n temporal` command we used in the previous section where we deployed the Temporal server, note the IP address and port of the `temporal-k8s` service and configure the `temporal-worker-k8s` charm. You may choose whichever `queue` and `namespace` you wish, but ensure that the namespace matches with the one created earlier in the Deploy Temporal section.

```bash
juju config temporal-worker-k8s host=$TEMPORAL_IP:$TEMPORAL_PORT queue=msm-queue namespace=msm-namespace
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
```

Next, we need to update the `maas-site-manager-k8s` config, using the same namespace and queue as configured for the worker above:

```bash
juju switch msm
juju config maas-site-manager-k8s temporal-server-address=$TEMPORAL_IP:$TEMPORAL_PORT temporal-namespace=msm-namespace temporal-task-queue=msm-queue
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
