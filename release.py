import json
from typing import Dict, Optional, List
from datetime import datetime
from healthcheck import http_healthcheck


class Release:
    """
    Release class definition deployed to GCP resources
    and have methods delete/deploy
    if you want adding new resource create new method and place
    resource body
    """
    def __init__(
            self, service, version: str, metadata, logger, gcp, previous_version: Optional[str] = None):
        """
        Class constructor
        """
        # Release version number
        self.version = version.replace('.', '-').lower()
        # Release service name
        self.service_name = service
        # Deploy metadata object from file
        self.metadata = metadata
        # Logger object
        self.logger = logger
        # GCP object - program interface for manipulating of resources
        self.gcp = gcp
        # Service name + Service version - of GCP resource naming
        self.service_name_with_version = f"{self.service_name}-{self.version}"

        self.service_instances = self.metadata.service_instances

        # Image names
        self.boot_disk_img = f"{self.service_name_with_version}-boot-img"
        self.data_disk_img = f"{self.service_name_with_version}-data-img"

        # Base instance name for instances in instance group
        self.baseInstanceName = f"{self.metadata.instance_name}-{self.version}-vm"
        # Instance template name
        self.instance_template_name = self.service_name_with_version
        # Instance Group name
        self.instance_group_name = self.service_name_with_version
        # Autascaler resource name
        self.autoscaler_name = self.service_name_with_version
        # Backend services names
        self.backend_services = [f"{self.service_name_with_version}-{x['name']}" for x in self.service_instances]
        # Forwarding rules names of backend services
        self.forwarding_rules = [f"{self.service_name_with_version}-{x['name']}" for x in self.service_instances]
        # Service healthcheck endpoint. default: /healthcheck
        self.service_healthcheck_endpoint = self.metadata.metadata['healthcheck_endpoint']
        # Release definitions
        self.definitions = {
            'metadata': {
                'service_name': self.service_name,
                'version': self.version,
                'start_deploy': datetime.now().strftime('%Y-%m-%d-%H-%M'),
                'end_deploy': '',
                'previous_version': previous_version
            },
            'instances': self.service_instances,
        }
        # Steps collection of deleting release
        self.delete_steps = [
            "Delete forwarding rule",
            "Delete addresses",
            "Delete backend services",
            "Delete autoscaler",
            'Delete instance group',
            "Delete instance template",
            "Delete images",
        ]
        # Steps collection of deploy releases
        self.deploy_steps = [
            "Create image",
            "Create Instance Template",
            "Create Instance Group",
            "Create autoscaler",
            "Create Backend services",
            "Create IPAddresses",
            "Creating forwarding rule",
        ]

    def disk_images(self) -> List:
        """
        Generating body of creating images compute resources to GCP
        """
        body = [
                {
                    "name": self.boot_disk_img,
                    "source_disk": self.metadata.source_boot_disk,
                    "source-disk-zone": self.metadata.gcp_region,
                    "type": "boot",
                },
                {
                    "name": self.data_disk_img,
                    "source_disk": self.metadata.source_data_disk,
                    "source-disk-zone": self.metadata.gcp_region,
                    "type": "data",
                },
        ]
        # Save images body to Release definitions
        self.definitions.update({'disk_images': body})
        return body

    # def disk_image(self, **kwargs) -> Dict:
    #     body = {
    #                 "name": self.boot_disk_img,
    #                 "source_disk": kwargs['source_disk'],
    #                 "source-disk-zone": self.metadata.gcp_region,
    #             }
    #
    #     return body

    def instance_template(self) -> Dict:
        # https://cloud.google.com/compute/docs/reference/rest/v1/instanceTemplates/insert
        body = {
            "description": f"Instance Template of service {self.service_name} version {self.version}",
            "kind": "compute#instanceTemplate",
            "name": self.instance_template_name,
            "properties": {
                "canIpForward": False,
                "disks": [
                    {
                        "autoDelete": True,
                        "boot": True,
                        "deviceName": f"{self.boot_disk_img}",
                        "index": 0,
                        "initializeParams": {
                            "diskSizeGb": "80",
                            "diskType": "pd-balanced",
                            "sourceImage": f"projects/{self.metadata.gcp_project}/global/images/{self.boot_disk_img}"
                        },
                        "kind": "compute#attachedDisk",
                        "mode": "READ_WRITE",
                        "type": "PERSISTENT"
                    },
                    {
                        "autoDelete": True,
                        "boot": False,
                        "deviceName": f"{self.data_disk_img}",
                        "index": 1,
                        "initializeParams": {
                            "diskSizeGb": "50",
                            "diskType": "pd-balanced",
                            "sourceImage": f"projects/{self.metadata.gcp_project}/global/images/{self.data_disk_img}"
                        },
                        "kind": "compute#attachedDisk",
                        "mode": "READ_WRITE",
                        "type": "PERSISTENT"
                    }
                ],
                "machineType": self.metadata.machine_type,
                "metadata": {
                    "items": [
                        {
                            "key": "windows-startup-script-ps1",
                            "value": f"C:\\instance-startup.ps1 {self.service_name}"
                        }
                    ],
                    "kind": "compute#metadata"
                },
                "networkInterfaces": [
                    {
                        "kind": "compute#networkInterface",
                        "name": "nic0",
                        "network": self.metadata.network,
                        "subnetwork": self.metadata.subnetwork
                    }
                ],
                "reservationAffinity": {
                    "consumeReservationType": "ANY_RESERVATION"
                },
                "scheduling": {
                    "automaticRestart": True,
                    "onHostMaintenance": "MIGRATE",
                    "preemptible": False,
                    "provisioningModel": "STANDARD"
                },
                "serviceAccounts": [
                    {
                        "email": self.metadata.service_account,
                        "scopes": [
                            "https://www.googleapis.com/auth/cloud-platform"
                        ]
                    }
                ],
                "shieldedInstanceConfig": {
                    "enableIntegrityMonitoring": True,
                    "enableSecureBoot": False,
                    "enableVtpm": True
                },
                "tags": {
                    "items": self.metadata.instance_tags
                }
            },
        }
        # self.definitions.update({'instance_template': body})
        return body

    # def instance_group(self):
    #     body = {
    #         "description": "This instance group is controlled by Regional Instance Group Manager 'gase-mt4mngapi00q-0-1-0-trf-2461-26-mig'. To modify instances in this group, use the Regional Instance Group Manager API: https://cloud.google.com/compute/docs/reference/latest/regionInstanceGroupManagers",
    #         "kind": "compute#instanceGroup",
    #         "name": f"{self.service_name}-{self.version}",
    #         "network": self.metadata.network,
    #         "region": self.metadata.gcp_region,
    #         "size": self.metadata.instance_group_size,
    #         "subnetwork": self.metadata.subnetwork
    #     }
    #     return body

    def region_health_check(self)-> Dict:
        body = {

        }

    def region_instance_group_manager(self) -> Dict:
        body = {
          "kind": "compute#instanceGroupManager",
          "name": self.instance_group_name,
          "autoHealingPolicies": [
            {
              "healthCheck": self.metadata.instance_group_helthcheck,
              "initialDelaySec": self.metadata.initialDelaySec
            }
          ],
          "baseInstanceName": self.baseInstanceName,
          "distributionPolicy": {
            "targetShape": self.metadata.metadata['gce_instance_group']['distributionPolicy']['targetShape'],
            "zones": self.metadata.metadata['gce_instance_group']['distributionPolicy']['zones'],
          },
          "instanceGroup": f"https://www.googleapis.com/compute/v1/projects/{self.metadata.gcp_project}/regions/{self.metadata.gcp_region}/instanceGroups/{self.instance_group_name}",
          "instanceTemplate": f"https://www.googleapis.com/compute/v1/projects/{self.metadata.gcp_project}/global/instanceTemplates/{self.instance_template_name}",

          "listManagedInstancesResults": "PAGELESS",
          "targetSize": self.metadata.metadata['gce_instance_group']['targetSize'],
          "updatePolicy": {
            "instanceRedistributionType": "PROACTIVE",
            "maxSurge": {
              "calculated": 3,
              "fixed": 3
            },
            "maxUnavailable": {
              "calculated": 3,
              "fixed": 3
            },
            "minimalAction": "REPLACE",
            "replacementMethod": "SUBSTITUTE",
            "type": "OPPORTUNISTIC"
          }
        }
        self.definitions.update({'instance_group_managed': body})
        return body

    def region_autoscaler(self):
        body = {
            "name": self.autoscaler_name,
            "target": f"https://www.googleapis.com/compute/v1/projects/{self.metadata.gcp_project}/regions/{self.metadata.gcp_region}/instanceGroupManagers/{self.instance_group_name}",
            "autoscalingPolicy": {
                "coolDownPeriodSec": self.metadata.metadata['gce_instance_group']['scaling']['coolDownPeriodSec'],
                "cpuUtilization": {
                  "utilizationTarget": self.metadata.metadata['gce_instance_group']['scaling']['cpuUtilizationTarget']
                },
                "customMetricUtilizations": [x for x in self.metadata.metadata['gce_instance_group']['scaling']['customMetricUtilizations']],

                "maxNumReplicas": self.metadata.metadata['gce_instance_group']['scaling']['maxNumReplicas'],
                "minNumReplicas": self.metadata.metadata['gce_instance_group']['scaling']['minNumReplicas'],
                "mode": self.metadata.metadata['gce_instance_group']['scaling']['mode']
              }
        }

        self.definitions.update({'autoscaler': body})
        return body

    def ip_addresses(self) -> dict:
        body = {"name": "",
                "subnetwork": self.metadata.subnetwork,
                "addressType": self.metadata.metadata['load_balancer']['loadBalancingScheme']}
        addresses = []
        for instance in self.service_instances:
            address_body = body.copy()
            address_name = f"{self.service_name}-{instance['name']}-{self.version}"
            address_body.update({'name': address_name})
            addresses.append(address_body)
        self.definitions.update({'addresses': addresses})
        return addresses

    def region_backend_service(self):
        body = {
            "kind": "compute#backendService",
            "loadBalancingScheme": self.metadata.metadata['load_balancer']['loadBalancingScheme'],
            "name": f"{self.service_name_with_version}",
            "protocol": self.metadata.metadata['load_balancer']['protocol'],
            "sessionAffinity": self.metadata.metadata['load_balancer']['sessionAffinity'],
            "timeoutSec": self.metadata.metadata['load_balancer']['timeoutSec'],
              "backends": [
                {
                  "balancingMode": self.metadata.metadata['load_balancer']['balancingMode'],
                  "group": f"https://www.googleapis.com/compute/v1/projects/{self.metadata.gcp_project}/regions/{self.metadata.gcp_region}/instanceGroups/{self.instance_group_name}",
                    # "maxConnectionsPerInstance": self.metadata.metadata['load_balancer']['maxConnectionsPerInstance'],
                }
              ],
              "connectionDraining": {
                "drainingTimeoutSec": self.metadata.metadata['load_balancer']['drainingTimeoutSec']
              },
              "description": "",
              "healthChecks": [
                  # ToDo:  Details: "[{'message': "Value for field 'resource.healthChecks' is too large: maximum size 1 element(s); actual size 5."}]
              ]
        }

        backends = []
        for instance in self.service_instances:
            backend_body = body.copy()
            backend_name = f"{self.service_name}-{instance['name']}-{self.version}"
            backend_healthcheck = f"https://www.googleapis.com/compute/v1/projects/{self.metadata.gcp_project}/regions/{self.metadata.gcp_region}/healthChecks/{instance['healthcheck']}"

            backend_body.update({"name": backend_name})
            backend_body['healthChecks'] = [backend_healthcheck]

            backends.append(backend_body)
        self.logger.logger.debug("Backend Service's body collection: %s", json.dumps(backends, indent=4))
        self.definitions.update({'backends': body})
        # yield backends
        return backends

    def forwarding_rule(self):
        body = {
          "kind": "compute#forwardingRule",
          "name": "",
          "IPAddress": "",
          "IPProtocol": "TCP",
          "backendService": "",
          "description": f"",
          "loadBalancingScheme": self.metadata.metadata['load_balancer']['loadBalancingScheme'],
          "network": self.metadata.network,
          "networkTier": "PREMIUM",
          "ports": [
            # "30011"
          ],
          "subnetwork": self.metadata.subnetwork
        }

        forwarding_rules = []
        # self.logger.logger.debug("Instance grom GCP object: \n%s", self.gcp.reserved_ip)
        for instance in self.service_instances:
            forwarding_rule_body = body.copy()
            forwarding_rule_name = f"{self.service_name}-{instance['name']}-{self.version}"
            backend_url = f"https://www.googleapis.com/compute/v1/projects/{self.metadata.gcp_project}/regions/{self.metadata.gcp_region}/backendServices/{self.service_name}-{instance['name']}-{self.version}"

            forwarding_ip = self.gcp.getAddresses(forwarding_rule_name)['address']

            forwarding_rule_body.update({"name": forwarding_rule_name})
            forwarding_rule_body.update({"backendService": backend_url})
            forwarding_rule_body.update({"IPAddress": forwarding_ip})
            forwarding_rule_body['ports'] = [x for x in instance.get('port').values()]

            forwarding_rules.append(forwarding_rule_body)
            # self.logger.logger.debug("Forwarding rule body of instance: %s\n%s", instance, forwarding_rule_body)

        self.logger.logger.debug("Forwarding Rule's body collection: %s", json.dumps(forwarding_rules, indent=4))

        self.definitions.update({'forwarding_rules': forwarding_rules})
        return forwarding_rules

    def delete(self):
        self.logger.logger.info("======= Deleting %s version: %s =======", self.service_name, self.version)
        # Deleting forwarding-rules
        rules = [x['name'] for x in self.gcp.gcp_resources['forwardingRules'] if self.version in x['name']]
        if not rules:
            self.logger.logger.info("Delete forwarding rule of deployment version %s: [ SKIP ]", self.version)
        else:
            self.gcp.delete_forwarding_rules(rules)

        # Delete ip addresses
        addresses = [x['name'] for x in self.gcp.gcp_resources['addresses'] if self.version in x['name']]
        if not addresses:
            self.logger.logger.info("Delete addresses of deployment version %s: [ SKIP ]", self.version)
        else:
            self.gcp.delete_address(addresses)

        # Deleting backend-services
        backends = [x['name'] for x in self.gcp.gcp_resources['regionBackendServices'] if self.version in x['name']]
        if not backends:
            self.logger.logger.info("Delete backend services of deployment version %s: [ SKIP ]", self.version)
        else:
            self.gcp.delete_backend_services(backends)

        # Deleting regional autoscaler
        autoscalers = [x['name'] for x in self.gcp.gcp_resources['autoscalers'] if self.version in x['name']]
        if not autoscalers:
            self.logger.logger.info("Delete autoscaler of deployment version %s: [ SKIP ]", self.version)
        else:
            self.gcp.delete_region_autoscaler(''.join(autoscalers))

        # Deleting instance group
        instance_group = [x['name'] for x in self.gcp.gcp_resources['regionInstanceGroupManagers'] if self.version in x['name']]
        if not instance_group:
            self.logger.logger.info("Delete instance group of deployment version %s: [ SKIP ]", self.version)
        else:
            self.gcp.delete_region_instance_group(''.join(instance_group))

        # Deleting instance template
        templates = [x['name'] for x in self.gcp.gcp_resources['instanceTemplates'] if self.version in x['name']]
        if not templates:
            self.logger.logger.info("Delete instance template of deployment version %s: [ SKIP ]", self.version)
        else:
            self.gcp.delete_instance_template(''.join(templates))

        # Delete disk images
        images = [x['name'] for x in self.gcp.gcp_resources['images'] if self.version in x['name']]
        if not images:
            self.logger.logger.info("Delete disk images of deployment version %s: [ SKIP ]", self.version)
        else:
            self.gcp.delete_disk_images(images)

    def deploy(self):
        self.logger.logger.info("======= Deploy service: %s version: %s =======", self.service_name, self.version)
        # Creating disk images
        self.gcp.insert_disk_images(self.disk_images())
        #
        # Creating instance template
        # instance_template_target = self.gcp.insert_instance_template(self.instance_template())
        self.gcp.insert_instance_template(self.instance_template())
        # if instance_template_target:
        #     self.instance_template_body.update({'targetLink': instance_template_target})
        # self.logger.logger.debug("Final instance template body: \n%s", self.instance_group_body)

        # instance_group_target = self.gcp.insert_instance_group(self.instance_group())
        # if instance_group_target:
        #     self.instance_group_body.update({'targetLink': instance_group_target})
        # self.logger.logger.debug("Final instance group body: \n%s", self.instance_group_body)

        # Creating regional managed instance group
        # self.gcp.insert_region_instance_group_managed(
        #     self.region_instance_group_manager(
        #         self.instance_group_body.get('targetLink'), self.instance_template_body.get('targetLink'))
        # )
        self.gcp.insert_region_instance_group_managed(self.region_instance_group_manager())

        # Creating autoscaler of managed instance group
        # self.region_autoscaler()
        self.gcp.insert_region_autoscaler(self.region_autoscaler())

        # Creating backend services
        # self.region_backend_service()
        self.gcp.insert_region_backend_service(self.region_backend_service())

        # Create addresses of internal load balancer per service instance
        self.gcp.insert_address(self.ip_addresses())
        # Creating forwarding-rules of backend services with
        # creating addresses
        # self.forwarding_rule()
        self.gcp.insert_forwarding_rules(self.forwarding_rule())

        self.logger.logger.info("Health checking GCE load balancers")
        http_healthcheck(
            self.definitions.get('forwarding_rules'), self.service_healthcheck_endpoint)

        #  ============ Collecting deploy resources =========================
        end_deploy_time = datetime.now().strftime('%Y-%m-%d-%H-%M')
        deploy_result_file = f"{self.service_name}_{self.version}_{end_deploy_time}.json"
        self.logger.colored("Deploy service: {} version: {} finished at {}".format(
            self.service_name, self.version, end_deploy_time))
        self.definitions['metadata']['end_deploy'] = end_deploy_time
        self.logger.colored("Previous release version: {}".format(self.gcp.gcp_resources_version['regionInstanceGroupManagers'][-1]), 'Cyan')
        self.definitions['metadata']['previous_version'] = self.gcp.gcp_resources_version['regionInstanceGroupManagers'][-1]
        self.drop_to_file(filename=deploy_result_file)
        self.logger.colored("Saved deployment results to file: {}".format(
            deploy_result_file), 'Green')

    def drop_to_file(self, filename: str):
        with open(filename, 'w') as file:
            file.write(json.dumps(
                self.definitions, indent=4))