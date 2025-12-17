ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.23
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip

WORKDIR /app
COPY requirements.txt /app/requirements.txt

RUN python3 -m venv /venv \
 && /venv/bin/pip install --no-cache-dir -U pip \
 && /venv/bin/pip install --no-cache-dir -r /app/requirements.txt

COPY main.py /app/main.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

ENV PATH="/venv/bin:$PATH"

CMD ["/run.sh"]