# Set up a Reverse-Proxy Service

MAAS Site Manager requires a reverse-proxy service. The easiest way to get one is reusing the Traefik service that comes with COS. If you have set up charm-level tracing, you must use Traefik for the reverse-proxy service.

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
