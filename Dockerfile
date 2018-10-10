FROM python:3.6-slim

WORKDIR /usr/src/app

# gcc is needed for regex package
RUN apt-get update && apt-get install -y git gnupg gcc
COPY requirements.txt ./
ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
RUN pip install --user --no-cache-dir -r requirements.txt
COPY . ./