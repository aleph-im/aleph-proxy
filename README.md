# aleph-proxy

## 1. Introduction

> Load balancer for the Aleph.im decentralized infrastructure.

This software provides an **HTTPS endpoint** to the capabilities of Core Channel (CCN) and Compute Resource (CRN) nodes of the network.

High availability is provided using **DNS Failover**: multiple servers are ready to handle client requests.

Requests are **dispatched across the nodes** of the network. Session cookies allow clients to request all their calls to be handled by the same [Compute Resource Node]((https://github.com/aleph-im/aleph-vm)) and VM.

Use `aleph.cloud` instead of `api1.aleph.im` or `api2.aleph.im` to use the official load balancer, or install your own with the procedure below.

Use `official.aleph.cloud` to only query official nodes managed by Aleph.im.

## 2. Architecture

The `aleph-proxy` load balancer is based on the [Traefik Proxy](https://traefik.io/).

The configuration of the proxy is provided to Traefik by the `aleph_proxy_config` Python ASGI web application. It is based on `./aleph_proxy_config/config.yaml`.  

The nodes behind the load balancer are fetched from the Aleph.im nodes aggregate, the same data used in account.aleph.im. A health check ensures that requests are only forwarded to online nodes. If a node fails to respond, the request will be automatically forwarded to another node instead.

## 3. Installation

```shell
apt update
apt upgrade
apt install git docker-compose
usermod -aG docker debian
git clone https://github.com/aleph-im/aleph-proxy.git
```

Edit the hostnames in `aleph-proxy/aleph_proxy_config/config.yaml`.

Logout and login again.

```shell
cd aleph-proxy
docker-compose up -d
```


### Copying keys

High availability setups will probably require you to copy
the _Let's Encrypt_ keys from a server to another.

If you do so, do not forget to update the file 
permissions on the second server: 
```shell
chmod 600 ./letsencrypt/acme.json
```
