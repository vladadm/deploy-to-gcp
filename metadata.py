import sys
import yaml
# from _logger import DeployLogger

# logger = DeployLogger(loglvl='INFO', name='metadata')


class DeploymentMetadata:
    def __init__(
            self,
            metadata_file: str,
            # app: str,
            # version: str,
            logger
            ):
        self.metadata_file = metadata_file
        # self.service_name = app
        # self.service_version = version
        self.logger = logger

        self.service_instances = []

        self.gcp_token = None
        self.gcp_project = None
        self.gcp_region = None
        self.network = None
        self.subnetwork = None
        self.service_account = None

        self.machine_type = None
        self.instance_name = None
        self.instance_tags = None
        self.source_boot_disk = None
        self.source_data_disk = None
        self.initialDelaySec = None
        self.instance_group_size = None

        self.gke_cluster = None
        self.gke_namespace = None
        self.instance_group_helthcheck = None
        self.metadata = None  # dict

        self.load_metadata()

    def load_metadata(self):
        try:
            with open(self.metadata_file, 'r') as f:
                self.logger.colored(f"Reading metadata file: {self.metadata_file}", 'Cyan', 'info')
                metadata = yaml.safe_load(f.read())
            self.logger.logger.debug('Metadata: \n%s', yaml.dump(metadata))
        except Exception as exc:
            self.logger.logger.error("Failed reading metadata file: %s", str(exc), stack_info=False)
            sys.exit(3)
        # ===== GCP Project
        # setattr(self, "gcp_token", metadata['gcp_project']['auth_json_file'])  # json file name
        # setattr(self, "gcp_project", metadata['gcp_project']['name'])
        # setattr(self, "gcp_region", metadata['gcp_project']['region'])
        #
        # setattr(self, "service_name", metadata['service_name'])
        # setattr(self, "service_tech_name", metadata['gce_instance']['base_name'])
        # setattr(self, "instances", metadata['gce_instance']['instances'])
        # self.service_name = metadata['service_name']
        # self.service_tech_name = metadata['gce_instance']['base_name']
        # self.gcp_token = metadata['gcp_project']['auth_json_file']
        self.gcp_project = metadata['gcp_project']['name']
        self.gcp_region = metadata['gcp_project']['region']
        self.network = metadata['gcp_project']['network']
        self.subnetwork = metadata['gcp_project']['subnetwork']
        self.service_account = metadata['gcp_project']['service_account']

        self.service_instances = metadata['service_instances']

        self.source_boot_disk = metadata['gce_instance']['source_boot_disk']
        self.source_data_disk = metadata['gce_instance']['source_data_disk']

        # setattr(self, "machine_type", metadata['gce_instance']['machine_type'])  # str
        # setattr(self, "instance_name", metadata['gce_instance']['name'])  # str
        # setattr(self, "instance_tags", metadata['gce_instance']['tags'])  # list
        self.machine_type = metadata['gce_instance']['machine_type']
        self.instance_name = metadata['gce_instance']['base_instance_name']
        self.instance_tags = metadata['gce_instance']['tags']

        self.instance_group_size = metadata['gce_instance_group']['size']
        self.initialDelaySec = metadata['gce_instance_group']['autoHealing']['initialDelaySec']
        self.instance_group_helthcheck = metadata['gce_instance_group']['autoHealing']['healthCheck']

        self.gke_namespace = metadata['gke_cluster']['namespace']
        self.gke_cluster = metadata['gke_cluster']['name']

        self.metadata = metadata