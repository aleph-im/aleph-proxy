import re

import aiohttp as aiohttp
import yaml
from fastapi import FastAPI

app = FastAPI()

url = "https://api1.aleph.im/api/v0/aggregates/0xa1B3bb7d2332383D96b7796B908fB7f7F3c2Be10.json?keys=corechannel&limit=50"


async def download_nodes():
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            print("Status:", response.status)
            print("Content-type:", response.headers['content-type'])

            data = await response.json()
            print("Body:", len(data))

            return data


def get_api_node_urls(aggr):
    for node in aggr['data']['corechannel']['nodes']:
        multiaddress = node['multiaddress']
        match = re.findall(r"/ip4/([\d\\.]+)/.*", multiaddress)
        if match:
            ip = match[0]
            yield f"http://{ip}:4024/api/"


def get_compute_resource_node_urls(aggr):
    for node in aggr['data']['corechannel']['resource_nodes']:
        addr = node['address'].strip("/")
        if addr:
            yield addr + "/vm/"


@app.get("/api")
async def read_root():
    with open('config.yaml', 'r') as fd:
        config = yaml.safe_load(fd)

    aggr = await download_nodes()
    api_urls = list(get_api_node_urls(aggr))
    vm_urls = list(get_compute_resource_node_urls(aggr))
    config['http']['services']['aleph-api']['loadBalancer']['servers'] = api_urls
    config['http']['services']['aleph-vm']['loadBalancer']['servers'] = vm_urls
    return config
