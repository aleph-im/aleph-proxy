import asyncio
import logging
import re
from typing import Optional

import aiohttp as aiohttp
import yaml
from fastapi import FastAPI

logging.basicConfig(
    level=logging.WARNING,
)
logger = logging.getLogger(__file__)

app = FastAPI()

TRUSTED_HOSTS = [
    "https://api1.aleph.im",
    "https://api2.aleph.im",
]
PATH = "/api/v0/aggregates/0xa1B3bb7d2332383D96b7796B908fB7f7F3c2Be10.json?keys=corechannel&limit=50"

global_data = {}
global_update_task: Optional[asyncio.Task] = None


async def download_nodes():
    # Iterate over trusted hosts in case the first is unavailable
    for trusted_host in TRUSTED_HOSTS:
        url = trusted_host + PATH
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(30)) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                return data


async def get_global_nodes():
    """Returns the Aleph nodes from the global variable"""
    # Wrap with asyncio.wait_for
    for retry in range(10):
        if global_data:
            return global_data
        else:
            logger.warning(f"Node data missing ({retry}/10)...")
            await asyncio.sleep(2)
            continue


async def keep_nodes_updated():
    """Asyncio task that updates the aleph nodes regularly"""
    global global_data
    while True:
        logger.debug("Obtaining node data...")
        global_data = await download_nodes()
        logger.debug("Obtained node data.")
        await asyncio.sleep(10)


def get_api_node_urls(aggr):
    for node in aggr['data']['corechannel']['nodes']:
        multiaddress = node['multiaddress']
        match = re.findall(r"/ip4/([\d\\.]+)/.*", multiaddress)
        if match:
            ip = match[0]
            yield {"url": f"http://{ip}:4024/api/"}


def get_compute_resource_node_urls(aggr):
    for node in aggr['data']['corechannel']['resource_nodes']:
        addr = node['address'].strip("/")
        if addr:
            if not addr.startswith("https://"):
                addr = "https://" + addr
            yield {"url": addr + "/vm/"}


@app.get("/api")
async def read_root():
    aggr = await asyncio.wait_for(get_global_nodes(), timeout=60)

    with open('config.yaml', 'r') as fd:
        config = yaml.safe_load(fd)

    api_urls = list(get_api_node_urls(aggr))
    vm_urls = list(get_compute_resource_node_urls(aggr))
    config['http']['services']['aleph-api']['loadBalancer']['servers'] = api_urls
    config['http']['services']['aleph-vm']['loadBalancer']['servers'] = vm_urls
    return config


@app.on_event("startup")
async def start_polling():
    global global_update_task
    loop = asyncio.get_event_loop()
    global_update_task = loop.create_task(keep_nodes_updated())


@app.on_event("shutdown")
async def stop_polling():
    global global_update_task
    global_update_task.cancel()
