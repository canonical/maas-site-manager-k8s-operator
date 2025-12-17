# MAAS Site Manager Installation

The recommended way of deploying MAAS Site Manager K8s is via Terraform. Below we outline the steps to do so.

## Deploy charms via Terraform

MAAS Site Manager has a Terraform plan that you may use to easily deploy all charms (except for the COS Lite stack). If you instead wish to deploy the charms manually, skip this section and continue with the Manual Deployment Tutorial.

If you wish to use the Terraform plan, first download the files to a directory:

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

MAAS Site Manager requires an object storage service, such as Ceph. For a development environment, [microceph](https://canonical-microceph.readthedocs-hosted.com/en/squid-stable/tutorial/get-started/) is sufficient. Note that microceph's `rgw` service uses port 80 by default. If you are installing microceph in the same VM as MAAS Site Manager, change the `rgw` port to something else (we use 8080 below). Throughout the microceph setup tutorial, take note of the access key and secret key created.

### Configure the deployment

The MAAS Site Manager Terraform plan can take various input variables. Make sure to create a file called `terraform.tfvars` inside the `msm-deployment` directory with the required entries below, or see the [sample](https://git.launchpad.net/maas-site-manager/plain/deployment/config/terraform.tfvars.sample) file.

```
# Use the IP address from `sudo microceph status` and the port specified with `sudo microceph enable rgw`
s3_endpoint = "http://10.207.11.185:8080"
s3_access_key = "my_access_key"
s3_secret_key = "my_secret_key"
s3_bucket = "my_s3_bucket"
```

The Terraform plan will deploy MAAS Site Manager, Postgresql, Traefik, S3 Integrator, and the Temporal charms. You may instruct the Terraform plan to skip deploying some of these charms by specifying a Juju offer URL in the `terraform.tfvars` file. See the `variables.tf` file you downloaded earlier for which offers you may specify.

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

Finally, create a MAAS Site Manager admin account and login at `http://<INGRESS_IP>/msm-maas-site-manager-k8s`

```bash
# Create admin account
juju run -m msm maas-site-manager-k8s/0 create-admin username=admin password=admin email=admin@example.com
```
