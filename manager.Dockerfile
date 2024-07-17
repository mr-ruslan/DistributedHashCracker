FROM python:3.10

WORKDIR /app

COPY manager.py ./manager.py
COPY mw_scheme.xsd ./mw_scheme.xsd
COPY templates ./templates

RUN pip install --no-cache-dir flask[async] xmlschema uwsgi pymongo flask-pymongo pika retry

CMD ["uwsgi", "--http", "0.0.0.0:5000", "--enable-threads", "--lazy-apps", "--master", "--processes", "1", "--threads", "4", "-w", "manager:app"]