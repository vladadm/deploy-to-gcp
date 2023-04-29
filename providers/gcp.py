from google.oauth2.service_account import Credentials
from googleapiclient import discovery, errors
import json
from typing import Any, Dict, Optional
import sys
import re
import time


#  ===================   GCP Provider =====================
class GceOperationStatus:
    """
    Class with GCE operations statuses.
    """
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"


class GCP:
    def __init__(
            self,
            metadata,
            gcp_token,
            logger,
            service: str = Optional,
            api_version: str = 'v1',
            gcp_resource: str = "compute",
            num_retries: int = 2,
            operation_pull_interval: int = 5,
            stabilisation_interval: int = 900,
            
    ):
        self.operation_pull_interval = operation_pull_interval  # seconds
        self.instance_group_stabilisation_interval = stabilisation_interval  # second
        self.gcp_resource = gcp_resource
        self.logger = logger
        self.metadata = metadata
        self.api_version = api_version  # GCP api version
        self.num_retries = num_retries  # Retries count of api request
        self.gcp_token = gcp_token      # json file name with GCP SA key

        self.gcp_project = metadata.gcp_project
        self.gcp_region = metadata.gcp_region
        self.service_name = service

        # GCP project resources
        self.gcp_resources = {
            "images": [],
            "instanceTemplates": [],
            "regionInstanceGroupManagers": [],
            "autoscalers": [],
            "regionBackendServices": [],
            "forwardingRules": [],
            "addresses": []
        }
        self.gcp_resources_version = {}

    def gcp_discovery(self) -> Any:  # pylint: disable=missing-docstring
        """
        Create connection to GCP
        :return: GCP connector object
        """
        try:
            auth = Credentials.from_service_account_file(self.gcp_token)
        except Exception as exc:
            self.logger.colored("Failed auth in GCP project {} with key file {}: \n{}".format(
                self.gcp_project, self.gcp_token, exc), 'Red', 'error')
            sys.exit(3)
        try:
            gcp_connect = discovery.build(
                serviceName=self.gcp_resource, version=self.api_version,
                credentials=auth, cache_discovery=False
            )
        except Exception as exc:
            self.logger.colored("Failed connect to GCP project {} api_version: {} \n{}".format(
                self.gcp_project, self.api_version, exc), 'Red')
            sys.exit(3)
        return gcp_connect

    def getResourcesVersions(self):
        for resource in self.gcp_resources:
            versions = set()
            resources = self.gcp_resources[resource]
            if resources:
                try:
                    for item in resources:
                        if resource == "images":
                            version = re.findall(
                                f"{self.service_name}-(.*)-(boot-img|data-img)",
                                item["name"],
                            )[0][0]
                        elif (
                            resource == "regionBackendServices"
                            or resource == "forwardingRules"
                            or resource == "addresses"
                        ):
                            version = re.findall(
                                f"{self.service_name}-\w+\d+-(.*)", item["name"]
                            )[0]
                        else:
                            version = re.findall(f"{self.service_name}-(.*)", item["name"])[
                                0
                            ]
                        # print(version)
                        if version:
                            # ToDo: Temporary need deleting
                            if "1-11-0-tcp-connection-scale-00" in version:
                                continue
                            versions.add(version)

                    self.gcp_resources_version.update({resource: sorted(list(versions))})
                    # logger_colored(f'Found version of {resource} resource: \n{versions}', 'Cyan')
                    # logger_colored('Found version of %s resource: %s' % (resource, '\n- '.join(map(str, versions))), 'Cyan')
                except Exception as exc:
                    self.logger.colored(
                        'Failed to retrieve version from resources: \n{}'.format('\n'.join(map(str, resources))),
                        'Red', 'error')
            else:
                self.logger.colored(f"Not found items for resource: {resource}", 'Cyan')

        self.logger.colored(
            f'Resources versions of service: {self.service_name} in GCP project: {self.gcp_project}', 'Cyan')

        print(json.dumps(self.gcp_resources_version, indent=4))

    def listAddresses(self):
        self.logger.colored("Сhecking usable addresses of service: {} in subnet: {} region: {}".format(
                       self.service_name, self.metadata.subnetwork, self.gcp_region), 'Cyan')

        addresses = self.gcp_discovery().addresses().list(
            project=self.gcp_project, region=self.gcp_region
        ).execute(num_retries=self.num_retries)

        if addresses.get('items'):

            self.gcp_resources['addresses'] = []
            for x in addresses.get('items'):
                if self.service_name in x['name'] and x['status'] == 'IN_USE':
                    self.gcp_resources['addresses'].append(
                        {"name": x['name'], "status": x['status'], 'address': x['address']})

            self.logger.logger.info(
                "Found in use addresses: \n- %s", '\n- '.join(map(str, self.gcp_resources['addresses'])))

            # reserved_ip = [x for x in addresses.get('items') if x['status'] != 'IN_USE']
            # self.logger.logger.info('Reserved addresses count: %s', len(reserved_ip))
            #
            # if len(reserved_ip) < 5:
            #     self.logger.logger.error(
            #         'Not enough free addresses for new deploy must be 5 reserved ip addresses but found only %s. ',
            #         len(reserved_ip))
            #     sys.exit(3)

    def listForwardingRules(self):
        self.logger.colored("Getting forwarding-rules of service: {} from GCP project: {} region: {}".format(
            self.service_name, self.gcp_project, self.gcp_region), 'Cyan')

        forwarding_rules = self.gcp_discovery().forwardingRules().list(
            project=self.gcp_project, region=self.gcp_region).execute()
        if forwarding_rules.get('items'):
            # self.logger.logger.debug("Items: \n%s", json.dumps(forwarding_rules.get('items'), indent=4))
            self.gcp_resources['forwardingRules'] = []
            for x in forwarding_rules.get('items'):
                if self.service_name in x['name']:
                    self.gcp_resources['forwardingRules'].append(
                        {"name": x.get('name'), "ip": x.get('IPAddress'), "ports": x.get('ports')})
        else:
            self.gcp_resources['forwardingRules'] = []

        self.logger.logger.info(
            "Found forwarding rules: \n- %s", '\n- '.join(map(str, self.gcp_resources['forwardingRules'])))

    def listBackendServices(self):
        self.logger.colored("Getting backend-services for service: {} from GCP project: {} region: {}".format(
                            self.service_name, self.gcp_project, self.gcp_region), 'Cyan')
        backends = self.gcp_discovery().regionBackendServices().list(
            project=self.gcp_project, region=self.gcp_region).execute()
        if backends.get('items'):
            self.gcp_resources['regionBackendServices'] = []
            for x in backends['items']:
                if self.service_name in x['name']:
                    self.gcp_resources['regionBackendServices'].append({'name': x['name']})
        else:
            self.gcp_resources['regionBackendServices'] = []

        self.logger.logger.info(
            "Found GCP Backend Services: \n- %s", '\n- '.join(map(str, self.gcp_resources['regionBackendServices'])))

    def listRegionInstanceGroupManagers(self):
        self.logger.colored("Getting instance groups managed for service: {} from GCP project: {} region: {}".format(
            self.service_name, self.gcp_project, self.gcp_region), 'Cyan')
        instance_groups = self.gcp_discovery().regionInstanceGroupManagers().list(
            project=self.gcp_project, region=self.gcp_region).execute()
        if instance_groups.get('items'):
            items = []
            for x in instance_groups['items']:
                if self.service_name in x['name']:
                    items.append({"name": x['name'], "deployed": x['creationTimestamp']})
            self.gcp_resources['regionInstanceGroupManagers'] = sorted(items,
                                                                       key=lambda d: d['deployed'], reverse=True)
        else:
            self.gcp_resources['regionInstanceGroupManagers'] = []

        self.logger.logger.info(
            "Found GCP Instance Groups: \n- %s", '\n- '.join(
                map(str, self.gcp_resources['regionInstanceGroupManagers'])))

    def listrRegionAutoscalers(self):
        self.logger.colored("Getting autoscalers for service: {} from GCP project: {} region: {}".format(
            self.service_name, self.gcp_project, self.gcp_region), 'Cyan')
        autoscalers = self.gcp_discovery().regionAutoscalers().list(
            project=self.gcp_project, region=self.gcp_region).execute()
        if autoscalers.get('items'):
            items = []
            for x in autoscalers['items']:
                if self.service_name in x['name']:
                    items.append({"name": x['name'], "deployed": x['creationTimestamp']})
            self.gcp_resources['autoscalers'] = sorted(items, key=lambda d: d['deployed'], reverse=True)
        self.logger.logger.info(
            "Found following autoscaler's: \n- %s", '\n- '.join(map(str, self.gcp_resources['autoscalers'])))

    def listImages(self):
        self.logger.colored("Getting disk images for {} from GCP project {}".format(
            self.service_name, self.gcp_project), 'Cyan')
        try:
            images = self.gcp_discovery().images().list(project=self.gcp_project).execute()
            if not images.get('items'):
                raise Exception("Disk images for %s in GCP project %s not found", self.service_name, self.gcp_project)

            self.gcp_resources['images'] = []
            if images.get('items'):
                for x in images.get('items'):
                    if self.service_name in x['name']:
                        self.gcp_resources['images'].append(
                            {"name": x['name'], "size": x['diskSizeGb'], "timeStamp": x['creationTimestamp']})
            self.logger.logger.info("Found disk images: \n- %s", '\n- '.join(map(str, self.gcp_resources['images'])))
        except errors.HttpError as gcp_api_err:
            self.logger.colored(gcp_api_err, "Red", 'error')
            exit(3)

    def listInstanceTemplates(self):
        self.logger.colored("Getting Instance Template for service: {} from GCP project: {} region: {}".format(
            self.service_name, self.gcp_project, self.gcp_region), 'Cyan')
        instanceTemplates = self.gcp_discovery().instanceTemplates().list(project=self.gcp_project).execute()
        if instanceTemplates.get('items'):
            self.gcp_resources['instanceTemplates'] = []
            for x in instanceTemplates['items']:
                if self.service_name in x['name']:
                    self.gcp_resources['instanceTemplates'].append({'name': x['name']})

        self.logger.logger.info(
            "Found Instance Templates: \n- %s", '\n- '.join(map(str, self.gcp_resources['instanceTemplates'])))

    def getAddresses(self, name: str):
        self.logger.logger.debug("Getting ip address of %s", name)
        ip_address = self.gcp_discovery().addresses().get(
            project=self.gcp_project, region=self.gcp_region, address=name).execute()
        self.logger.logger.debug('Response body: %s', ip_address)
        return ip_address

    def listHealthCheck(self):
        self.logger.colored("Getting healthchecks for service: {} from GCP project: {} region: {}".format(
            self.service_name, self.gcp_project, self.gcp_region), 'Cyan')

        healthchecks = self.gcp_discovery().healthChecks().list(project=self.gcp_project).execute()
        if healthchecks.get('items'):
            hl = [x['name'] for x in healthchecks['items'] if self.service_name in x['name']]
        else:
            hl = []
        self.logger.logger.info("Found Healthchecks: \n- %s", '\n- '.join(map(str, hl)))

    def overview(self):
        self.logger.colored(f"==== Starting overviewing resources in GCP {self.gcp_project} project ====",
                            'Cyan', 'info')
        self.listImages()
        self.listInstanceTemplates()
        self.listHealthCheck()
        self.listrRegionAutoscalers()
        self.listRegionInstanceGroupManagers()
        self.listBackendServices()
        self.listForwardingRules()
        self.listAddresses()
        self.getResourcesVersions()

    def delete_forwarding_rules(self, data: list):
        self.logger.logger.debug("Deleting following forwarding rules body: %s", data)
        operations = []
        for forwarding_rule_name in data:
            msg = "Deleting forwarding rules: {} START".format(forwarding_rule_name)
            self.logger.colored(msg, 'Cyan')
            try:
                response = self.gcp_discovery().forwardingRules().delete(
                    project=self.gcp_project, region=self.gcp_region, forwardingRule=forwarding_rule_name).execute()
            except errors.HttpError as gcp_api_err:
                self.logger.colored(gcp_api_err, "Red", 'error')
                exit(3)
            try:
                operation_name = response["name"]
            except KeyError:
                raise Exception(
                    "Wrong response '{}' returned - it should contain "
                    "'name' field".format(response))
            operations.append({'operation_msg': msg, 'operation_name': operation_name})
            self.logger.logger.debug("Operation response: %s", response)
        for operation in operations:
            self._wait_for_operation_to_complete(
                project_id=self.gcp_project, region=self.gcp_region, operation_name=operation['operation_name'],
                event=operation['operation_msg'])

    def delete_backend_services(self, data: list):
        self.logger.logger.debug("Deleting following backend services: %s", data)
        operations = []
        for backend_service_name in data:
            # self.logger.logger.info("Deleting backend service: \x1b[36;1m %s \x1b[0m", backend_service_name)
            msg = "Deleting backend service: {} START".format(backend_service_name)
            self.logger.colored(msg, 'Cyan')
            try:
                response = self.gcp_discovery().regionBackendServices().delete(
                    project=self.gcp_project, region=self.gcp_region, backendService=backend_service_name).execute()
            # except errors.HttpError as gcp_api_err:
            #     self.logger.colored(gcp_api_err, "Red", 'error')
            #     exit(3)
            # try:
                operation_name = response["name"]
            except errors.HttpError as gcp_api_err:
                if gcp_api_err.error_details:
                    self.logger.colored(json.dumps(gcp_api_err.error_details[0], indent=4), "Red", 'error')
                else:
                    self.logger.colored(gcp_api_err, "Red", 'error')
                exit(3)
            except KeyError:
                raise Exception(
                    "Wrong response '{}' returned - it should contain "
                    "'name' field".format(response))
            operations.append({'operation_msg': msg, 'operation_name': operation_name})
            self.logger.logger.debug("Operation response: %s", response)
        for operation in operations:
            self._wait_for_operation_to_complete(
                project_id=self.gcp_project, region=self.gcp_region, operation_name=operation['operation_name'],
                event=operation['operation_msg'])

    def delete_region_autoscaler(self, autoscaler_name: str):
        self.logger.logger.debug("Deleting regional autoscaler: %s", autoscaler_name)
        msg = "Deleting regional autoscaler: {} START".format(autoscaler_name)
        self.logger.colored(msg, 'Cyan')
        response = self.gcp_discovery().regionAutoscalers().delete(
            project=self.gcp_project, region=self.gcp_region, autoscaler=autoscaler_name).execute()
        try:
            operation_name = response["name"]
        except KeyError:
            raise Exception(
                "Wrong response '{}' returned - it should contain "
                "'name' field".format(response))
        self._wait_for_operation_to_complete(
            project_id=self.gcp_project, region=self.gcp_region,
            operation_name=operation_name, event=msg)
        self.logger.logger.debug("Operation response: %s", response)

    def delete_region_instance_group(self, instance_group_name: str):
        self.logger.logger.debug("Deleting regional managed instance group: %s", instance_group_name)
        # self.logger.logger.info("Deleting regional managed instance group: \n%s", instance_group_name)
        msg = "Deleting regional managed instance group: {}".format(instance_group_name)
        self.logger.colored(msg, 'Cyan')
        response = self.gcp_discovery().regionInstanceGroupManagers().delete(
            project=self.gcp_project, region=self.gcp_region, instanceGroupManager=instance_group_name).execute()
        try:
            operation_name = response["name"]
        except KeyError:
            raise Exception(
                "Wrong response '{}' returned - it should contain "
                "'name' field".format(response))
        self._wait_for_operation_to_complete(
            project_id=self.gcp_project, region=self.gcp_region,
            operation_name=operation_name, event=msg)
        self.logger.logger.debug("Operation response: %s", response)

    def delete_instance_template(self, instance_template_name: str):
        self.logger.logger.debug("Deleting instance template: %s", instance_template_name)
        msg = "Deleting instance template: {} START".format(instance_template_name)
        self.logger.colored(msg, 'Cyan')
        response = self.gcp_discovery().instanceTemplates().delete(
            project=self.gcp_project, instanceTemplate=instance_template_name).execute()
        try:
            operation_name = response["name"]
        except KeyError:
            raise Exception(
                "Wrong response '{}' returned - it should contain "
                "'name' field".format(response))
        self._wait_for_operation_to_complete(
            project_id=self.gcp_project, operation_name=operation_name, event=msg)
        self.logger.logger.debug("Operation response: %s", response)

    def delete_disk_images(self, data: list):
        self.logger.logger.debug("Deleting following disk images: %s", data)
        operations = []
        for disk_image_name in data:
            msg = "Deleting disk image: {}".format(disk_image_name)
            self.logger.colored(msg, 'Cyan')
            response = self.gcp_discovery().images().delete(
                project=self.gcp_project, image=disk_image_name).execute()
            try:
                operation_name = response["name"]
            except KeyError:
                raise Exception(
                    "Wrong response '{}' returned - it should contain "
                    "'name' field".format(response))
            operations.append({'operation_msg': msg, 'operation_name': operation_name})
            # self.logger.logger.debug('Operation id: %s', operation_name)
            self.logger.logger.debug("Operation response: %s", response)
        for operation in operations:
            # global operation type
            self._wait_for_operation_to_complete(
                project_id=self.gcp_project, operation_name=operation['operation_name'],
                event=operation['operation_msg'])

    def delete_address(self, addresses: list):
        self.logger.logger.debug("Deleting ip address body: %s", addresses)
        operations = []
        for address in addresses:
            msg = "Deleting ip address: {} START".format(address)
            self.logger.colored(msg, 'Cyan')
            response = self.gcp_discovery().addresses().delete(
                project=self.gcp_project, region=self.gcp_region, address=address).execute()
            try:
                operation_name = response["name"]
            except KeyError:
                raise Exception(
                    "Wrong response '{}' returned - it should contain "
                    "'name' field".format(response))
            operations.append({'operation_msg': msg, 'operation_name': operation_name})
            self.logger.logger.debug("Operation response: %s", response)
        for operation in operations:
            self._wait_for_operation_to_complete(
                project_id=self.gcp_project, region=self.gcp_region, operation_name=operation['operation_name'],
                event=operation['operation_msg'])

    def insert_address(self, addresses: list):
        self.logger.logger.debug("Create ip addresses body: %s", addresses)
        operations = []
        for body in addresses:
            msg = "Create ip address: {}".format(body['name'])
            self.logger.colored(msg, "Cyan")

            response = self.gcp_discovery().addresses().insert(
                project=self.gcp_project, region=self.gcp_region, body=body).execute()
            try:
                operation_name = response["name"]
            except KeyError:
                raise Exception(
                    "Wrong response '{}' returned - it should contain "
                    "'name' field".format(response))
            operations.append({'operation_msg': msg, 'operation_name': operation_name})
            self.logger.logger.debug("Operation response: %s", response)
            self.logger.logger.info('Operation id: %s', operation_name)
        for operation in operations:
            self._wait_for_operation_to_complete(
                project_id=self.gcp_project, region=self.gcp_region,
                operation_name=operation['operation_name'], event=operation['operation_msg'])

    def insert_disk_images(self, images: list):
        operations = []
        self.logger.logger.debug("Creating disk images body: %s", images)
        for body in images:
            msg = "Creating disk image: {}".format(body['name'])
            self.logger.colored(msg, "Cyan")
            response = self.gcp_discovery().images().insert(
                project=self.gcp_project, body=body, forceCreate=True).execute()
            try:
                operation_name = response["name"]
            except KeyError:
                raise Exception(
                    "Wrong response '{}' returned - it should contain "
                    "'name' field".format(response))
            self.logger.logger.debug("Operation response: %s", response)
            self.logger.logger.info('Operation id: %s', operation_name)
            operations.append({'operation_msg': msg, 'operation_name': operation_name})
        for operation in operations:
            self._wait_for_operation_to_complete(
                project_id=self.gcp_project, operation_name=operation['operation_name'],
                event=operation['operation_msg'])

    # def insert_disk_image(
    #         self,
    #         body: dict
    # ) -> str:
    #     msg = "Creating disk image: {}", body.get('name')
    #     self.logger.logger.info()
    #     self.logger.logger.debug("Creating disk image body: \n%s", json.dumps(body, indent=4))
    #     response = self.gcp_discovery().images().insert(
    #         project=self.gcp_project, body=body, forceCreate=True).execute()
    #     try:
    #         operation_name = response["name"]
    #     except KeyError:
    #         raise Exception(
    #             "Wrong response '{}' returned - it should contain "
    #             "'name' field".format(response))
    #     self._wait_for_operation_to_complete(project_id=self.gcp_project,
    #                                          operation_name=operation_name)
    #     return operation_name['targetLink']

    def insert_instance_template(self, body: dict):
        msg = "Creating instance template: {}".format(body['name'])
        self.logger.colored(msg, 'Cyan')
        self.logger.logger.debug("Body: \n%s", json.dumps(body, indent=4))
        try:
            response = self.gcp_discovery().instanceTemplates().insert(
                project=self.gcp_project, body=body).execute()
            operation_name = response["name"]
        except errors.HttpError as gcp_api_err:
            if gcp_api_err.error_details:
                self.logger.colored(json.dumps(gcp_api_err.error_details[0], indent=4), "Red", 'error')
            else:
                self.logger.colored(gcp_api_err, "Red", 'error')
            exit(3)
        except KeyError:
            raise Exception(
                "Wrong response '{}' returned - it should contain "
                "'name' field".format(response))
        self._wait_for_operation_to_complete(
            project_id=self.gcp_project, operation_name=operation_name, event=msg)
        self.logger.logger.debug("Operation response: %s", response)
        self.logger.logger.debug("TargetLink: %s", response.get('targetLink'))
        return response.get('targetLink')

    # def insert_instance_group(self, body: dict):
    #     self.logger.logger.info("Creating regional managed instance group: %s", body['name'])
    #     self.logger.logger.debug("Body: \n%s", json.dumps(body, indent=4))
    #     response = self.gcp_discovery().instanceGroups().insert(
    #         project=self.gcp_project, zone='asia-southeast1-a', body=body).execute()
    #     try:
    #         operation_name = response["name"]
    #     except KeyError:
    #         raise Exception(
    #             "Wrong response '{}' returned - it should contain "
    #             "'name' field".format(response))
    #     self._wait_for_operation_to_complete(
    #         project_id=self.gcp_project, zone='asia-southeast1-a', operation_name=operation_name)
    #     self.logger.logger.debug("Operation response: %s", response)
    #     return response.get('targetLink')

    def insert_region_instance_group_managed(self, body: dict):
        msg = "Creating regional instance group manager: {}".format(body['name'])
        self.logger.logger.debug("Body: \n%s", json.dumps(body, indent=4))
        self.logger.colored(msg, 'Cyan')
        response = self.gcp_discovery().regionInstanceGroupManagers().insert(
            project=self.gcp_project, region=self.gcp_region, body=body).execute()
        try:
            operation_name = response["name"]
        except KeyError:
            raise Exception(
                "Wrong response '{}' returned - it should contain "
                "'name' field".format(response))
        self.logger.logger.debug("Response: %s", response)
        start_time = time.time()
        self._wait_for_operation_to_complete(
            project_id=self.gcp_project, region=self.gcp_region,
            event=msg, operation_name=operation_name)
        self.logger.logger.debug("Operation response: %s", response)

        self._wait_for_instance_group_to_stable(project_id=self.gcp_project, region=self.gcp_region,
                                                instance_group_name=body['name'])
        deploy_interval = (time.time() - start_time)
        self.logger.colored(
            "Instance Group Managed: {} deploy interval: {}".format(
                body['name'], deploy_interval), 'Green')
        return response.get('targetLink')

    def insert_region_autoscaler(self, body):
        msg = "Creating autoscaler of managed instance group: {}".format(body['name'])
        self.logger.logger.debug("Body: \n%s", json.dumps(body, indent=4))
        response = self.gcp_discovery().regionAutoscalers().insert(
            project=self.gcp_project, region=self.gcp_region, body=body).execute()
        try:
            operation_name = response["name"]
        except KeyError:
            raise Exception(
                "Wrong response '{}' returned - it should contain "
                "'name' field".format(response))
        self.logger.logger.debug("Response: %s", response)
        self._wait_for_operation_to_complete(
            project_id=self.gcp_project, region=self.gcp_region,
            event=msg, operation_name=operation_name)
        self.logger.logger.debug("Operation response: %s", response)

    def insert_region_backend_service(self, body: list):
        operations = []
        for region_backend in body:
            msg = "Creating regional backend: {}".format(region_backend['name'])
            self.logger.colored(msg, "Cyan")
            self.logger.logger.debug("Regional backend body: \n%s", json.dumps(region_backend, indent=4))
            response = self.gcp_discovery().regionBackendServices().insert(
                project=self.gcp_project, region=self.gcp_region, body=region_backend).execute()
            try:
                operation_name = response["name"]
            except KeyError:
                raise Exception(
                    "Wrong response '{}' returned - it should contain "
                    "'name' field".format(response))
            self.logger.logger.debug("Operation response: %s", response)
            self.logger.logger.info('Operation id: %s', operation_name)
            operations.append({'operation_msg': msg, 'operation_name': operation_name})
        for operation in operations:
            self._wait_for_operation_to_complete(
                project_id=self.gcp_project, region=self.gcp_region,
                event=msg, operation_name=operation['operation_name'])

    def insert_forwarding_rules(self, body):
        operations = []
        for forwarding_rule in body:
            msg = "Creating forwarding rule: {}".format(forwarding_rule['name'])
            self.logger.colored(msg, "Cyan")
            self.logger.logger.debug("Forwarding rule body: \n%s", json.dumps(forwarding_rule, indent=4))
            response = self.gcp_discovery().forwardingRules().insert(
                project=self.gcp_project, region=self.gcp_region, body=forwarding_rule).execute()
            try:
                operation_name = response["name"]
            except KeyError:
                raise Exception(
                    "Wrong response '{}' returned - it should contain "
                    "'name' field".format(response))
            operations.append({'operation_msg': msg, 'operation_name': operation_name})
            self.logger.logger.debug("Operation response: %s", response)
        for operation in operations:
            self._wait_for_operation_to_complete(
                project_id=self.gcp_project, region=self.gcp_region,
                operation_name=operation['operation_name'], event=operation['operation_msg'])

    def resizeRegionInstanceGroupManagers(self, group_name: str, group_size: int):
        msg = "Scale down instance group: {}".format(group_name)
        self.logger.colored(msg, 'Cyan', 'info')
        response = self.gcp_discovery().regionInstanceGroupManagers().resize(
            project=self.gcp_project, region=self.gcp_region,
            instanceGroupManager=group_name, size=group_size).execute()
        try:
            operation_name = response["name"]
        except KeyError:
            raise Exception(
                "Wrong response '{}' returned - it should contain "
                "'name' field".format(response))
        self.logger.logger.debug("Response: %s", response)
        self._wait_for_operation_to_complete(
            project_id=self.gcp_project, region=self.gcp_region,
            event=msg, operation_name=operation_name)
        self.logger.logger.debug("Operation response: %s", response)

    def _wait_for_instance_group_to_stable(
            self, project_id: str,
            region: str, instance_group_name: str
    ) -> None:
        msg = "Wait instance group {} is stabilization START".format(instance_group_name)
        self.logger.colored(msg, 'Cyan')
        count = 0
        maximum_counts = int(self.instance_group_stabilisation_interval/self.operation_pull_interval)
        while True:
            instance_group_response = self._instance_group_status(
                service=self.gcp_discovery(),
                instance_group=instance_group_name, region=region,
                project_id=project_id, num_retries=self.num_retries
            )
            if instance_group_response.get("status").get('isStable') is True:
                self.logger.colored("Instance group: {} return status isStable: {}".format(
                    instance_group_name, instance_group_response.get("status").get('isStable')), 'Green')
                # self.logger.logger.info('Instance group: %s return status isStable: %s', instance_group_name, instance_group_response.get("status").get('isStable'))
                break
            else:
                self.logger.colored("Instance group: {} return status isStable: {}".format(
                    instance_group_name, instance_group_response.get("status").get('isStable')), 'Yellow')
                self.logger.logger.debug("Instance group response body: %s", instance_group_response)
            count += 1
            if count > maximum_counts:
                # self.logger.logger.error('Instance group did not return status isStable: True in time interval %s seconds',
                #              self.instance_group_stabilisation_interval)
                self.logger.colored(
                    "Instance group {} did not return status isStable: True in time interval {} seconds".format(
                        instance_group_name, self.instance_group_stabilisation_interval), "Red")
                exit(3)
            time.sleep(self.operation_pull_interval)

    def _wait_for_operation_to_complete(
        self,
        project_id: str,
        operation_name: str,
        event: Optional[str] = None,
        region: Optional[str] = None,
        zone: Optional[str] = None
    ) -> None:
        """
        Waits for the named operation to complete - checks status of the async call.

        :param operation_name: name of the operation
        :type operation_name: str
        :param zone: optional region of the request (might be None for global operations)
        :type zone: str
        :return: None
        """
        service = self.gcp_discovery()
        # self.logger.logger.info("Operation id: %s", operation_name)
        while True:
            if zone is None and region is None:
                # noinspection PyTypeChecker
                operation_response = self._check_global_operation_status(
                    service=service, operation_name=operation_name,
                    project_id=project_id, num_retries=self.num_retries
                )
            if region:
                # noinspection PyTypeChecker
                operation_response = self._check_region_operation_status(
                    service=service, operation_name=operation_name, region=region,
                    project_id=project_id, num_retries=self.num_retries
                )
            if zone:
                # noinspection PyTypeChecker
                operation_response = self._check_zone_operation_status(
                    service, operation_name, project_id, zone, self.num_retries)
            if operation_response.get("status") == GceOperationStatus.DONE:
                error = operation_response.get("error")
                if error:
                    code = operation_response.get("httpErrorStatusCode")
                    msg = operation_response.get("httpErrorMessage")
                    # Extracting the errors list as string and trimming square braces
                    error_msg = str(error.get("errors"))[1:-1]
                    raise Exception("{} {}: ".format(code, msg) + error_msg)
                self.logger.colored("{}: {}".format(event, operation_response.get("status")), 'Green')

                break
            else:
                # self.logger.logger.info("\x1b[93;0mOperation status: %s\x1b[0m", operation_response.get("status"))
                self.logger.colored("{}: {}".format(event, operation_response.get("status")), 'Yellow')
                self.logger.logger.debug("Operation response body: %s", operation_response)
            time.sleep(self.operation_pull_interval)

    @staticmethod
    def _check_zone_operation_status(
        service: Any,
        operation_name: str,
        project_id: str,
        zone: str,
        num_retries: int
    ) -> Dict:
        return service.zoneOperations().get(
            project=project_id, zone=zone, operation=operation_name).execute(
            num_retries=num_retries)

    @staticmethod
    def _check_global_operation_status(
        service: Any,
        operation_name: str,
        project_id: str,
        num_retries: int
    ) -> Dict:
        return service.globalOperations().get(
            project=project_id, operation=operation_name).execute(
            num_retries=num_retries)

    @staticmethod
    def _check_region_operation_status(
        service: Any,
        operation_name: str,
        project_id: str,
        region: str,
        num_retries: int
    ) -> Dict:
        return service.regionOperations().get(
            project=project_id, region=region, operation=operation_name).execute(
            num_retries=num_retries)

    @staticmethod
    def _instance_group_status(
        service: Any,
        instance_group: str,
        project_id: str,
        region: str,
        num_retries: int
    ) -> Dict:
        return service.regionInstanceGroupManagers().get(
            project=project_id, region=region, instanceGroupManager=instance_group).execute(
            num_retries=num_retries
        )
