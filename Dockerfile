FROM python:3.6-slim

WORKDIR /usr/src/app

# gcc is needed for regex package
RUN apt-get update && apt-get install -y gcc
COPY requirements.txt ./
RUN pip install --user --no-cache-dir -r requirements.txt
COPY . ./
RUN python -m pytest -sv