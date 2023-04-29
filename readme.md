## Delivery you GCE instance to instance group managed

This script is designed to automate the delivery and deployment of your GCE instance to a regional managed instances group.

The creation of resources in GCP:
- Image of disk ( global )
- Instance Template ( region )
- Managed Instance Group ( region )
- Autoscaler
- Internal TCP Load Balancer ( region )
  - backend service ( region )
  - address ( region )
  - forwarding rule ( region )

How script works:
- Loads parameters from the metadata file and performs the following actions through a GCP API call:
  - creating image from you GCE instance disks
  - creating Instance Template
  - creating Instance Group Manager
    - awaiting group stabilization
  - creating Autoscaler
  - creating Backend Service
  - creating Address in subnetwork
  - creating Forwarding Rule
- Performs accessibility of service through the load balancer

To work you will need:
- Create a service account in GCP with the following roles:
  ```"roles/compute.admin",         
    "roles/compute.instanceAdmin"
    "roles/iam.serviceAccountUser"
    "roles/container.clusterViewer"
    "roles/container.viewer"
    "roles/monitoring.metricWriter"
- Create json key of service account
- Create GCE instance and deploying you app
- Define which instance you want to deploy as a managed group
- On what subnet
- With what parameters
- Fill out the metadata file

Script run arguments:
- ```--metadata ```  
- ```--gcp-token```
- ```--service```
- ```--version```
- ```--operation```
- ```--help```


Metadata file example in ```metadata.example.yaml```


The script can be used in the CI/CD pipeline:
example:
