FROM python:3.10-slim

WORKDIR /app

RUN apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout="30" update \
    && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout="30" install -y --no-install-recommends \
    curl \
    sumo \
    sumo-tools \
    && rm -rf /var/lib/apt/lists/*

COPY edge_deploy/docker/requirements.runtime.txt /tmp/requirements.runtime.txt
RUN pip install --no-cache-dir -r /tmp/requirements.runtime.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SUMO_HOME=/usr/share/sumo

CMD ["uvicorn", "edge_deploy.inference_server:app", "--host", "0.0.0.0", "--port", "8001"]
