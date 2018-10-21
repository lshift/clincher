FROM python:3.6.6-alpine3.8

WORKDIR /usr/src/app

# gcc is needed for regex package
RUN apk add --no-cache gcc musl-dev git
COPY test-requirements.txt ./
RUN pip install --user --no-cache-dir -r test-requirements.txt
RUN pip install flit
COPY . ./
ENV FLIT_ROOT_INSTALL=1
RUN flit install -s
ENV GIT_PYTHON_TRACE=1
RUN git config --global user.email foo@bar.com
RUN git config --global user.name Foo
RUN python -m pytest -v test_commits.py --cov=clincher --cov-report=term-missing -x