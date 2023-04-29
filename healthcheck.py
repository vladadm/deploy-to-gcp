import requests
import sys
import logging
from logging import Logger
import json

logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S", stream=sys.stderr)
logger: Logger = logging.getLogger("py")
# logger.setLevel(f'{args.log_lvl}'.upper())
logger.setLevel('DEBUG')
logging.getLogger("chardet.charsetprober").disabled = True

# logger.info(
#     'Script running with fallowing parameters: \n%s', args
# )


def http_healthcheck(
        resources: dict, healthcheck_endpoint: str):
# {
#     "kind": "compute#forwardingRule",
#     "name": "mt4-management-api-1-2-3-4-556-live03",
#     "IPAddress": "10.131.53.186",
#     "IPProtocol": "TCP",
#     "backendService": "https://www.googleapis.com/compute/v1/projects/zfx-qa/regions/asia-southeast1/backendServices/mt4-management-api-1-2-3-4-556-live03",
#     "description": "",
#     "loadBalancingScheme": "INTERNAL",
#     "network": "projects/zfx-infrastructure/global/networks/zfx-infrastructure-vpc",
#     "networkTier": "PREMIUM",
#     "ports": [
#         [
#             30130,
#             30131
#         ]
#     ],
#     "subnetwork": "projects/zfx-infrastructure/regions/asia-southeast1/subnetworks/zfx-qa-scaling-services",
#     'healthcheck_endpoint': '/healthcheck'
# }
# def http_healthcheck():
    connection_timeout = 10
    results = []

    urls = [
        {'instance': 'mt4-management-api-1-2-3-4-555-live03', 'resource': 'load_balancer', 'url': '10.131.53.198', 'port': '30130',
         'healthcheck_endpoint': '/healthcheck'},
        {'instance': 'mt4-management-api-1-2-3-4-555-live02', 'resource': 'load_balancer', 'url': '10.131.53.175', 'port': '30120',
         'healthcheck_endpoint': '/healthcheck'}
    ]
    # print(resources)
    for resource in resources:
        url = f"http://{resource['IPAddress']}:{resource['ports'][0]}{healthcheck_endpoint}"
        try:
            response = requests.get(
                url=url, timeout=connection_timeout)
            # print(response)
            resource.update({'url': url, 'status_code': response.status_code, 'body': response.json()})
        except Exception as exc:
            logger.error('Can not connection to %s \n%s', url, exc)
            resource.update({'url': url, 'status_code': 'timeout', 'body': ''})
        results.append(resource)

        # print(results)

    print("===== Healthcheck results =====")
    for result in results:
        if result['status_code'] != 200:
            print(f"\x1b[31;1m{result['name']} || {result['url']} || {result['status_code']} \x1b[0m")
            print(f"Body: {json.dumps(result['body'], indent=4)}")
        else:
            print(f"\x1b[32;20m{result['name']} || {result['url']} || {result['status_code']} \x1b[0m")
            # print(f"Body: {json.dumps(result['body'], indent=4)}")

    if len([x for x in results if x['status_code'] != 200]):
        print("\x1b[31;1m===== Healthcheck failed! =====\x1b[0m")
        """Please check services on instances in instance group managed 
        ( Details about instances you can find in previous stage ) or contact with DevOps Teams"""
        exit(3)
    print("\x1b[32;1m===== Healthcheck passed! =====\x1b[0m")


if __name__ == "__main__":
    http_healthcheck()
