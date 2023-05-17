import asyncio
import logging
import re
from typing import Optional, Dict

import aiohttp as aiohttp
import sentry_sdk
import yaml
from aiohttp import ClientResponseError
from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger(__file__)

app = FastAPI()

TRUSTED_HOSTS = [
    "https://api1.aleph.im",
    "https://api2.aleph.im",
]
PATH = "/api/v0/aggregates/0xa1B3bb7d2332383D96b7796B908fB7f7F3c2Be10.json?keys=corechannel&limit=50"

global_data = {}
global_system_info_data = []
global_update_task: Optional[asyncio.Task] = None
global_update_sysinfo_task: Optional[asyncio.Task] = None

async def download_nodes() -> Dict:
    # Iterate over trusted hosts in case the first is unavailable
    last_error = None
    for trusted_host in TRUSTED_HOSTS:
        url = trusted_host + PATH
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(30)) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data
        except ClientResponseError as error:
            logger.warning(f"Error downloading nodes from {trusted_host}")
            last_error = error
            continue

    # Failed for all trusted hosts
    assert last_error is not None, "The last error should be defined"
    raise last_error


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
        await asyncio.sleep(30)

async def keep_nodes_system_info_updated():
    """Asyncio task that updates the aleph nodes regularly"""
    while True:
        logger.debug("Obtaining nodes system info data...")
        await update_system_info_nodes()
        logger.debug("Obtained node system info data.")
        await asyncio.sleep(30)

async def update_system_info_nodes():
    """Asyncio task that updates the aleph nodes system info regularly"""
    global global_system_info_data
    aggr = await asyncio.wait_for(get_global_nodes(), timeout=60)
    if not aggr:
        raise ValueError("Node data is missing")
    
    for node in aggr['data']['corechannel']['resource_nodes']:
        addr = node['address'].strip("/")
        if not addr:
            continue

        if addr:
            if not addr.startswith("https://"):
                addr = "https://" + addr

        url = addr + "/about/usage/system"

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(30)) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    if data is None or "cpu" not in data:
                        continue
                    global_system_info_data.append({
                        "url": addr + "/vm/",
                        "system_info": data
                    })
        except Exception as error:
            logger.warning(f"Error loading system info for node {url}")
            continue

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
    if not aggr:
        raise ValueError("Node data is missing")

    with open('config.yaml', 'r') as fd:
        config = yaml.safe_load(fd)

    api_urls = list(get_api_node_urls(aggr))
    vm_urls = list(get_compute_resource_node_urls(aggr))
    config['http']['services']['aleph-api']['loadBalancer']['servers'] = api_urls
    config['http']['services']['aleph-vm']['loadBalancer']['servers'] = vm_urls
    return config

@app.get("/api/by_instance_type/{instance_type}")
async def read_instance_type(instance_type):
    with open(f'config_{instance_type}.yaml', 'r') as fd:
        config = yaml.safe_load(fd)

    global global_system_info_data

    vm_s = []
    vm_m = []
    vm_l = []
    vm_xl = []

    for vm in global_system_info_data:
        vm_url = vm["url"]
        crn_info = vm["system_info"]
        cpu = crn_info["cpu"]["count"]
        ram = crn_info["mem"]["total_kB"]/1024/1024
        storage = crn_info["disk"]["total_kB"]/1024/1024/1024
        print(vm_url, "CPU: ", cpu, " RAM: ", ram, " DISK: ", storage)

        if instance_type == 'compute':
            if cpu <= 8 or (cpu < 24 and ram <= 16):
                vm_s.append(vm_url)
            elif 8 < cpu <= 16 or (cpu > 8 and 16 >= ram < 32):
                vm_m.append(vm_url)
            elif 16 <= cpu <= 32 or (cpu > 12 and 16 > ram <=32):
                vm_l.append(vm_url)
            elif cpu >= 32 or (cpu > 16 and ram > 32):
                vm_xl.append(vm_url)
            else:
                logger.warning(f"Config does not match any criteria ({vm_url})")
                print(vm)
        elif instance_type == 'storage':
            if storage <= 1:
                vm_s.append(vm_url)
            if storage > 1 and storage <= 2:
                vm_m.append(vm_url)
            if storage > 2 and storage <= 4:
                vm_l.append(vm_url)
            if storage > 4:
                vm_xl.append(vm_url)

        elif instance_type == 'memory':
            if storage <= 16:
                vm_s.append(vm_url)
            if storage > 16 and storage <= 32:
                vm_m.append(vm_url)
            if storage > 32 and storage <= 128:
                vm_l.append(vm_url)
            if storage > 128:
                vm_xl.append(vm_url)

    if len(vm_s) > 0:
        config['http']['services'][f'aleph-vm-{instance_type}-small']['loadBalancer']['servers'] = vm_s
    if len(vm_m) > 0:
        config['http']['services'][f'aleph-vm-{instance_type}-medium']['loadBalancer']['servers'] = vm_m
    if len(vm_l) > 0:
        config['http']['services'][f'aleph-vm-{instance_type}-large']['loadBalancer']['servers'] = vm_l
    if len(vm_xl) > 0:
        config['http']['services'][f'aleph-vm-{instance_type}-xlarge']['loadBalancer']['servers'] = vm_xl

    return config
    
@app.on_event("startup")
async def setup_sentry():
    sentry_sdk.init()
    # Environment variable SENTRY_DSN is read automatically by sentry_sdk


@app.on_event("startup")
async def start_polling():
    global global_update_task
    global global_update_sysinfo_task
    loop = asyncio.get_event_loop()
    global_update_task = loop.create_task(keep_nodes_updated())
    global_update_sysinfo_task = loop.create_task(keep_nodes_system_info_updated())

@app.on_event("shutdown")
async def stop_polling():
    global global_update_task
    global global_update_sysinfo_task
    global_update_task.cancel()
    global_update_sysinfo_task.cancel()


def download_node_data():
    "Download the node data outside of ASGI."
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(download_nodes())

if __name__ == '__main__':
    global_data = download_node_data()
    print(global_data)
