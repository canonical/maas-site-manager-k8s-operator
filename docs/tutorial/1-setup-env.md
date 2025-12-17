# Set up environment

In this section, we'll set up a development environment for deploying Charmed MAAS Site Manager K8s. We use a Multipass VM with the [charm-dev](https://github.com/canonical/multipass-blueprints/blob/main/v1/charm-dev.yaml) cloud-init config to install and configure necessary components, like MicroK8s and Juju.

## Launch the charm-dev Multipass VM
If you haven't already installed Multipass, do so via snap:

```bash
sudo snap install multipass
```

Then, launch a new VM with the `charm-dev` cloud-init config:

```bash
multipass launch --cpus 4 --memory 8G --disk 50G --name charm-dev-vm charm-dev
```

[note]
**Note:** You can find documentation about the `multipass launch` command used above [here](https://multipass.run/docs/launch-command).
[/note]

Once the VM has finished launching, you can access it with:

```bash
multipass shell charm-dev-vm
```

## Set up Juju
First, set up Juju to use a local MicroK8s controller. If you do not already have a `microk8s` cloud (you can check with `juju clouds`), run the following in a shell inside the `charm-dev-vm`:

```bash
juju bootstrap microk8s microk8s
```

We will need two separate models for our deployment; one for COS Lite, and one for MAAS Site Manager. Create these models as shown below:

```bash
juju add-model msm
juju add-model cos-lite
```

**Next Step:** [Deploy PostgreSQL](/t/15822)
