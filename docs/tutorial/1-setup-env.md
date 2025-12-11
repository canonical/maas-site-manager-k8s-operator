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

## Deploy charms via Terraform

MAAS Site Manager has a Terraform plan that you may use to easily deploy all charms (except for the COS Lite stack). If you instead wish to deploy the charms manually, skip this section and continue below to the Manual Deployment Setup section. If you wish to use the Terraform plan, first download the files to a directory:

```bash
mkdir msm-deployment
cd msm-deployment
curl https://git.launchpad.net/maas-site-manager/plain/deployment/terraform/main.tf -O
curl https://git.launchpad.net/maas-site-manager/plain/deployment/terraform/provider.tf -O
curl https://git.launchpad.net/maas-site-manager/plain/deployment/terraform/temporal.tf -O
curl https://git.launchpad.net/maas-site-manager/plain/deployment/terraform/variables.tf -O
```

Next, set some environment variables so that Terraform can talk to the Juju controller:

```bash
export CONTROLLER=$(juju whoami | yq .Controller)
export JUJU_CONTROLLER_ADDRESSES=$(juju show-controller | yq .$CONTROLLER.details.api-endpoints | yq -r '. | join(",")')
export JUJU_USERNAME="$(cat ~/.local/share/juju/accounts.yaml | yq .controllers.$CONTROLLER.user|tr -d '"')"
export JUJU_PASSWORD="$(cat ~/.local/share/juju/accounts.yaml | yq .controllers.$CONTROLLER.password|tr -d '"')"
export JUJU_CA_CERT="$(juju show-controller $(echo $CONTROLLER|tr -d '"') | yq '.[$CONTROLLER]'.details.\"ca-cert\"|tr -d '"'|sed 's/\\n/\n/g')"
```

### Deploy Object Storage and S3 Integrator

MAAS Site Manager requires an object storage service, such as Ceph. For a development environment, [microceph](https://canonical-microceph.readthedocs-hosted.com/en/squid-stable/tutorial/get-started/) is sufficient. Note that microceph's `rgw` service uses port 80 by default. If you are installing microceph in the same VM as MAAS Site Manager, change the `rgw` port to something else (we use 8080 below). Throughout the microceph setup tutorial, take note of the access key and secret key created. Additionally, when creating a bucket, ensure it is called `msm-images`.

### Configure the deployment
The MAAS Site Manager Terraform plan can take various input variables. Make sure to create a file called `terraform.tfvars` inside the `msm-deployment` directory with the required entries below, or see the [sample](https://git.launchpad.net/maas-site-manager/plain/deployment/config/terraform.tfvars.sample) file.

```
# Use the IP address from `sudo microceph status` and the port specified with `sudo microceph enable rgw`
s3_endpoint = "http://10.207.11.185:8080"
s3_access_key = "my_access_key"
s3_secret_key = "my_secret_key"
s3_bucket = "my_s3_bucket"
```

The Terraform plan will deploy MAAS Site Manager, Postgresql, Traefik, S3 Integrator, and the Temporal charms. You may instruct the Terraform plan to skip deploying some of these charms by specifying a Juju offer URL in the `terraform.tfvars` file. See the `variables.tf` file you downloaded earlier for which offers you may specify. You may also specify specific channels and/or revisions to deploy these charms from.

As the Terraform plan does not deploy the COS Lite stack, you may do so yourself and specify offer URLs for the following endpoints in `terraform.tfvars`:

- `logging-consumer:loki_push_api`
- `metrics-endpoint:prometheus_scrape`
- `grafana-dashboard:grafana_dashboard`

### Deploy the charms

Once you've configured your deployment, run the Terraform plan:
```bash
terraform init
terraform apply -auto-approve
```

Finally, create a MAAS Site Manager admin account and login at `http://<MULTIPASS_VM_IP>/msm-maas-site-manager-k8s`

```bash
# Create admin account
juju run -m msm maas-site-manager-k8s/0 create-admin username=admin password=admin email=admin@example.com
```

If you've deployed your MAAS Site Manager instance via Terraform, you can skip the rest of this tutorial.

## Manual Deployment Setup

We will need two separate models for our deployment; one for COS Lite, and one for MAAS Site Manager. Create these models as shown below:

```bash
juju add-model msm
juju add-model cos-lite
```

**Next Step:** [Deploy MAAS Site Manager and PostgreSQL](/t/15822)
