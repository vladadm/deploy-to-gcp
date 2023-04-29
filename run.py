#!python3
import json
import argparse
from _logger import DeployLogger
from metadata import DeploymentMetadata
from providers.gke import GKE
from providers.gcp import GCP
from release import Release


# Link on documentation in confluence
DOCUMENTATION = {
    'general': "https://zfxtech.atlassian.net/wiki/spaces/DVO/pages/2008088745/Blue-green+deployment+to+GCP"}

arg_parser = argparse.ArgumentParser(
    prog='gcp-deploy.py',
    description='Script the deployment of blue green schema for autoscale instance group in Google Cloud Platform.',
    usage='''\n- python3 %(prog)s --metadata {} --gcp-token {} --version {} --log-lvl {} --service {} --operation {} 
- python3 %(prog)s --help for more information''',
    epilog="For questions and suggestions, contact the DevOps team.",
    formatter_class=argparse.RawTextHelpFormatter,
)
arg_parser.add_argument('--metadata', action='store', required=True,
                        type=str, help='file with deploy metadata')
arg_parser.add_argument('--gcp-token', action='store', required=True,
                        type=str, help='GCP token json file')
arg_parser.add_argument('--service', action='store', type=str,
                        help='Deployable service name \nexample: trading-api\n')
arg_parser.add_argument('--version', action='store', type=str,
                        help='Release version \nexample: --version 1.2.3.00\n')
arg_parser.add_argument('--operation', action='store', required=True,
                        type=str, help='command invoke',
                        choices=['overview', 'current_version', 'deploy',
                                 'delete', 'delete_previous', 'scale_down', 'scale_up'])
arg_parser.add_argument('--log-lvl', default='INFO', type=str, choices=['INFO', 'WARN', 'DEBUG'])
args = arg_parser.parse_args()


if __name__ == "__main__":
    logger = DeployLogger(loglvl=args.log_lvl, name='run.py')
    metadata = DeploymentMetadata(metadata_file=args.metadata, logger=logger)

    logger.colored(
        f'Script running with the following arguments: \n{json.dumps(args.__dict__, indent=4)}',
        'Light_Purple', 'info')

    logger.logger.info(
        """\x1b[34;1mStart Blue - Green deployment services: %s, version: %s to GCP. 
        More information about process you can find in documentation:\n%s\x1b[0m""",
        args.service, args.version, DOCUMENTATION['general'])

    # Initialize GKE object
    gke = GKE(args.service, metadata, logger)

    logger.colored("==== Get current version from load balancer ====", 'Cyan', 'info')
    gke.get_ingresses()

    if args.operation == "current_version":
        logger.colored(
            f"The current deployed version of {args.service} in GCP project {metadata.gcp_project} is: {gke.current_version}",
            'Cyan', 'info')
        exit(0)

    # Initialize GCP object
    gcp = GCP(
        metadata=metadata,
        gcp_token=args.gcp_token,
        logger=logger,
        service=args.service)

    if args.operation == "overview":
        # Discovering of GCP project
        gcp.overview()
        exit(0)

    if args.operation == "deploy":
        logger.colored(
            f"Receiving command on deploy service {args.service} version {args.version}", 'Cyan', 'info')

        # Initialize Release object of release version
        release = Release(service=args.service, version=args.version, metadata=metadata, logger=logger, gcp=gcp)
        # Checking what release version not current
        if release.version == gke.current_version:
            logger.colored('Sorry, but this version: {} already deployed and is current ( in LoadBalancer )'.format(
                         release.version), 'Red', 'error')
            exit(3)
        logger.colored('Discovering GCP project: {} in region: {}'.format(
                    metadata.gcp_project, metadata.gcp_region), 'Cyan')

        # Discovering GCP project
        gcp.overview()
        version_for_delete = set()
        for versions in gcp.gcp_resources_version.values():
            for version in versions:
                if version != gke.current_version:
                    version_for_delete.add(version)

        if release.version in version_for_delete:
            logger.logger.info(
                'This deployment of %s version %s found in GCP project bun is not current',
                release.service_name, release.version)
            release.delete()

        logger.colored('Start deploy service: {}, version {}'.format(
            release.service_name, release.version), 'Cyan')
        release.deploy()
    #
    if args.operation == "delete":
        gcp.overview()
        release = Release(
            service=args.service,
            version=args.version,
            metadata=metadata,
            logger=logger,
            gcp=gcp)
        logger.logger.info(
            'Delete deployment service: %s, version %s',
            release.service_name, release.version)
        release.delete()

    #
    if args.operation == "delete_previous":
        gcp.overview()
        logger.colored(f"==== Find previous versions of {args.service} in GCP project {metadata.gcp_project} ====",
                       'Cyan')
        version_for_delete = set()
        for versions in gcp.gcp_resources_version.values():
            for version in versions:
                if version != gke.current_version:
                    version_for_delete.add(version)
        logger.colored(f"Current working {args.service} version: {gke.current_version}", 'Cyan')
        if version_for_delete:
            logger.colored("Well be delete following {} releases versions: \n {}".format(
                args.service, json.dumps(list(version_for_delete), indent=4)
            ), 'Cyan')

            releases_for_deleting = []
            for version in version_for_delete:
                releases_for_deleting.append(
                    Release(
                        service=args.service,
                        version=version,
                        metadata=metadata,
                        logger=logger,
                        gcp=gcp)
                )

            for release in releases_for_deleting:
                # logger.colored(f"Delete {args.service} version: {release.version}", 'Cyan')
                release.delete()
        else:
            logger.colored(f'In GCP project {metadata.gcp_project} for service {args.service} '
                           f'not found previous version for deleting', 'Cyan', 'info')

    if args.operation == "scale_down":
        gcp.overview()
        release = Release(
            service=args.service,
            version=args.version,
            metadata=metadata,
            logger=logger,
            gcp=gcp)
        logger.logger.info(
            '==== Scale down deployment service: %s, version %s',
            release.service_name, release.version)
        gcp.delete_region_autoscaler(release.autoscaler_name)
        gcp.resizeRegionInstanceGroupManagers(
            group_name=release.instance_group_name, group_size=0)

    if args.operation == "scale_up":
        gcp.overview()
        release = Release(
            service=args.service,
            version=args.version,
            metadata=metadata,
            logger=logger,
            gcp=gcp)
        logger.logger.info(
            '==== Scale up deployment service: %s, version %s',
            release.service_name, release.version)
        gcp.insert_region_autoscaler(release.region_autoscaler())

