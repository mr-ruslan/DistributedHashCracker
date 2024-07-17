FROM python:3.10

WORKDIR /app

COPY worker.py ./worker.py
COPY mw_scheme.xsd ./mw_scheme.xsd

RUN pip install xmlschema pika retry

CMD ["python", "worker.py"]