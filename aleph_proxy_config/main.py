import yaml
from fastapi import FastAPI

app = FastAPI()


@app.get("/api")
def read_root():
    with open('config.yaml', 'r') as fd:
        data = yaml.safe_load(fd)
    return data
