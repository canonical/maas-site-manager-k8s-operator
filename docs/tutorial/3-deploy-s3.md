# Deploy Object Storage and S3 Integrator

MAAS Site Manager requires an object storage service, such as Ceph. For a development environment, [microceph](https://canonical-microceph.readthedocs-hosted.com/en/squid-stable/tutorial/get-started/) is sufficient. Note that microceph's `rgw` service uses port 80 by default. If you are installing microceph in the same VM as MAAS Site Manager, change the `rgw` port to something else (we use 8080 below). Throughout the microceph setup tutorial, take note of the access key and secret key created.

Once microceph is set up, install the `s3-integrator` charm and relate it to MAAS Site Manager:

```bash
# the IP address for the endpoint config parameter here is taken from the output of `sudo microceph status`. Use the port set when configuring the rgw service.
juju deploy s3-integrator --channel latest/stable --config endpoint=http://10.207.11.185:8080 --config bucket=my_s3_bucket --config path=/my_s3_path

# the access key and secret key used here come from the `sudo radosgw-admin key create` command in the microceph setup tutorial
juju run s3-integrator/leader sync-s3-credentials access-key=my_access_key secret-key=my_secret_key
```

**Next Step**: [Deploy Temporal](/t/17910)
