FROM python:3.6.6-alpine3.8

WORKDIR /usr/src/app

# gcc is needed for regex package
RUN apk add --no-cache gcc musl-dev
COPY requirements.txt ./
RUN pip install --user --no-cache-dir -r requirements.txt
COPY . ./
RUN python -m pytest -sv