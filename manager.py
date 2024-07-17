from flask import Flask, request, jsonify, render_template
import threading
import xml.etree.ElementTree as ET
from flask_pymongo import PyMongo
import pymongo
import pika
from retry import retry
import socket

import uuid
from datetime import datetime, timedelta
from enum import Enum
import string
from queue import Queue


CRACK_TIMEOUT = 100 #seconds


class CrackRequest:

    class Status(Enum):
        QUEUE = "QUEUE"
        IN_PROGRESS = "IN_PROGRESS"
        READY = "READY"
        ERROR = "ERROR"

    def __init__(self, id, hash, max_length, alphabet):
        self.id = id
        self.hash = hash
        self.max_length = max_length
        self.alphabet = alphabet



app = Flask(__name__)

mongo = PyMongo()
mongo.init_app(app, "mongodb://mongodb_0:27017,mongodb_1:27017,mongodb_2:27017/?replicaSet=rs0", w='majority', wTimeoutMS=10000)

collection = mongo.cx.appdatabase.crack

requests_storage = Queue(maxsize=0)


xsd_schema = ET.parse('mw_scheme.xsd')

alphabet = string.ascii_lowercase + string.digits



# POST CRACK
@app.route('/api/hash/crack', methods=['POST'])
async def crack_hash():
    try:
        payload = request.json

        if 'hash' not in payload or 'maxLength' not in payload:
            return jsonify({'error': 'Missing fields in JSON data'}), 400
        if not isinstance(payload['maxLength'], int):
            return jsonify({'error': 'maxLength must be integer'}), 400

        crack_alphabet = payload['alphabet'] if 'alphabet' in payload else alphabet

        request_id = str(uuid.uuid4())
        entry = {'request_id': request_id,
                 'hash': payload['hash'],
                 'max_length': payload['maxLength'],
                 'alphabet': crack_alphabet,
                 'data': {},
                 'status': CrackRequest.Status.QUEUE.value}
        while True:
            try:
                collection.insert_one(entry)
                break
            except pymongo.errors.DuplicateKeyError as e:
                request_id = str(uuid.uuid4())
                entry['request_id'] = request_id

        print(f'requested {request_id}')
        requests_storage.put(CrackRequest(request_id, payload['hash'], payload['maxLength'], crack_alphabet))

        return jsonify({'requestId': request_id}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# GET STATUS
@app.route('/api/hash/status')
def get_status():


    request_id = request.args.get('requestId')
    if request_id is None:
        return jsonify({'error': 'Missing requestId parameter'}), 400

    record  = collection.find_one({'request_id': request_id})
    print(f'found record: {record}')
    if record == None:
        return jsonify({'error': 'Request not found'}), 404
    
    return jsonify({
        'status': record['status'],
        'data': sum(record['data'].values(), []) if record['status'] == CrackRequest.Status.READY.value else None
    }), 200



# GET TEST PAGE
@app.route('/test')
def index():
    return render_template('test.html')



# CONSUMER
def handle_worker_response(channel, method, properties, body):
    message = body.decode('utf-8')

    try:
        xml_response_data = ET.fromstring(message)
        request_id = xml_response_data.attrib['requestId']
        part_number = int(xml_response_data.attrib['partNumber'])
        source_result = [src.text for src in xml_response_data.findall('result')]
        
        print(f'got {request_id}[{part_number}] = {source_result} with rabbit')
        collection.update_one({'request_id':request_id}, {'$set': {'data.'+str(part_number): source_result}}, upsert=False)
        record = collection.find_one({'request_id':request_id})
        if record != None:
            if all(str(i) in record['data'] for i in range(record['parts_count'])):
                collection.update_one({'request_id':request_id}, {'$set': {'status':CrackRequest.Status.READY.value}}, upsert=False)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(e)

@retry((pika.exceptions.ChannelClosed, pika.exceptions.AMQPConnectionError, socket.gaierror), delay=2)
def consumer():
    credentials = pika.PlainCredentials('admin', 'admin')
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq', credentials=credentials, heartbeat=0))
    channel = connection.channel()
    channel.exchange_declare(exchange='d_exchange', exchange_type='direct', durable=True)
    channel.queue_declare(queue='worker_queue', durable=True)
    channel.queue_bind(exchange='d_exchange', queue='worker_queue', routing_key='to_worker')
    channel.queue_declare(queue='manager_queue', durable=True)
    channel.queue_bind(exchange='d_exchange', queue='manager_queue', routing_key='to_manager')
    channel.basic_consume(queue='manager_queue', on_message_callback=handle_worker_response)
    channel.start_consuming()

threading.Thread(target=consumer, daemon=True).start()



workers_count = 4

# PUBLISHER
def start_task(request: CrackRequest, channel):
    workers_count_t = workers_count
    base_xml_request = ET.Element('request')
    base_xml_request.set('requestId', request.id)
    base_xml_request.set('hash', request.hash)
    base_xml_request.set('alphabet', request.alphabet)
    base_xml_request.set('maxLength', str(request.max_length))
    base_xml_request.set('partCount', str(workers_count_t))
    for i in range(workers_count_t):
        xml_request = base_xml_request
        xml_request.set('partNumber', str(i))
        xml_request_data = ET.tostring(xml_request)
        channel.basic_publish(exchange='d_exchange', routing_key='to_worker', body=xml_request_data, properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent))
    started = datetime.utcnow()
    collection.update_one({'request_id':request.id}, {'$set': {'started':started, 'status':CrackRequest.Status.IN_PROGRESS.value, 'parts_count':workers_count_t}}, upsert=False)

@retry((pika.exceptions.ChannelClosed, pika.exceptions.AMQPConnectionError, socket.gaierror), delay=2)
def task_starter():
   
    credentials = pika.PlainCredentials('admin', 'admin')
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq', credentials=credentials, heartbeat=0))
    channel = connection.channel()
    while True:
        request = requests_storage.get()
        try:
            start_task(request, channel)
        except InterruptedError:
            break
        except Exception as e:
            print(e)
            requests_storage.put(request)
            raise e
    connection.close()

threading.Thread(target=task_starter, daemon=True).start()

queued_tasks = collection.find({'status': CrackRequest.Status.QUEUE.value})
for task in queued_tasks:
    requests_storage.put(CrackRequest(task['request_id'], task['hash'], task['max_length'], task['alphabet']))
