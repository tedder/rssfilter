FROM ubuntu:18.04
#FROM python:3.6-alpine

RUN apt update && apt install -y vim curl bash openssl libxml2-dev python3-dev python3-pip build-essential
COPY requirements.txt /opt/app/
RUN pip3 install --no-cache-dir -r /opt/app/requirements.txt
COPY aws-credentials /root/.aws/credentials

COPY main.py /opt/app/
CMD /opt/app/main.py
