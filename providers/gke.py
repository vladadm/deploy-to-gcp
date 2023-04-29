from kubernetes import client, config
from kubernetes.client.rest import ApiException

#  =================== Kubernetes Provider =====================


class GKE:
    # Google Kubernetes Engine
    def __init__(self, service_name: str, metadata, logger):
        self.namespace = metadata.gke_namespace
        self.service_name = service_name
        self.cluster_name = metadata.gke_cluster
        self.current_version = ''
        self.logger = logger

    def get_ingresses(self):
        self.logger.colored(
            f"Getting ingresses of service {self.service_name} in GKE cluster: {self.namespace} namespace: {self.cluster_name}", 'Cyan')
        ingresses = []

        try:
            config.load_kube_config()
            api_instance = client.NetworkingV1Api()
            api_response = api_instance.list_namespaced_ingress(
                self.namespace,  # Namespace
                timeout_seconds=15,  # TimeOut connection
                # watch=True,
            )
        except ApiException as e:
            self.logger.logger.error("Exception when calling NetworkingV1Api->list_namespaced_ingress: %s\n" % e)
            exit(2)

        for ingress in api_response.items:
            if self.service_name in ingress.metadata.name:
                ingresses.append(ingress)
        try:
            names = [{'name': x.metadata.name, 'version': x.metadata.labels.get("version")} for x in ingresses]
        except Exception as exc:
            self.logger.logger.error('Not found version label in ingress manifests. \n%s', exc)
        self.logger.logger.info("Found ingresses: \n- %s", '\n- '.join(map(str, names)))
        versions = set([x.get("version") for x in names])
        self.logger.colored(
            "Ingress in GKE cluster {} configured for version: \n- {}".format(
                self.cluster_name, '\n- '.join(map(str, versions))), 'Green', 'info')
        if versions:
            self.current_version = "".join(versions)
