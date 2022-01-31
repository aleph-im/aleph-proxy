FROM python:3.10-bullseye

RUN mkdir /opt/aleph_proxy_config
WORKDIR /opt/aleph_proxy_config

COPY ./requirements.txt ./requirements.txt
RUN pip install -r ./requirements.txt

COPY . .

RUN useradd -s /bin/bash user
USER user
CMD uvicorn main:app --reload --host 0.0.0.0 --port 9000
