# Deploy Object Storage and S3 Integrator

MAAS Site Manager requires an object storage service, such as Ceph. For a development environment, [microceph](https://canonical-microceph.readthedocs-hosted.com/en/squid-stable/tutorial/get-started/) is sufficient. Note that microceph's `rgw` service uses port 80 by default. If you are installing microceph in the same VM as MAAS Site Manager, change the `rgw` port to something else (we use 8080 below). Throughout the microceph setup tutorial, take note of the access key and secret key created. Additionally, when creating a bucket, ensure it is called `msm-images`.

Once microceph is set up, install the `s3-integrator` charm and relate it to MAAS Site Manager:

```bash
# the IP address for the endpoint config parameter here is taken from the output of `sudo microceph status`. Use the port set when configuring the rgw service.
juju deploy s3-integrator --channel latest/stable --config endpoint=http://10.207.11.156:8080 --config bucket=msm-images --config path=/

# the access key and secret key used here come from the `sudo radosgw-admin key create` command in the microceph setup tutorial
juju run s3-integrator/leader sync-s3-credentials access-key=accesskey secret-key=mysecretkey

# integrate s3-integrator with maas-site-manager-k8s
juju integrate maas-site-manager-k8s s3-integrator
```

**Next Step**: [Deploy Temporal](/t/17910)
