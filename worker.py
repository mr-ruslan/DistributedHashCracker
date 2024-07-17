import threading
import xml.etree.ElementTree as ET
import pika
from retry import retry
import socket

import itertools
import hashlib



xsd_schema = ET.parse('mw_scheme.xsd')



def crack(request_id, target_hash, alphabet, max_length = 10, part_number=0, part_count=1):
    source = []
    print(f'start cracking {target_hash}')
    for i in range(1, max_length + 1):
        all_sources = itertools.product(alphabet, repeat=i)
        for combination_array in itertools.islice(all_sources, part_number, None, part_count):
            combination = ''.join(combination_array)
            md5_hash = hashlib.md5(combination.encode('utf-8')).hexdigest()
            if md5_hash == target_hash:
                source.append(combination)
    print(f'result: {source}')
    
    xml_response = ET.Element('response')
    xml_response.set('requestId', request_id)
    xml_response.set('partNumber', str(part_number))
    for s in source:
        result_element = ET.SubElement(xml_response, 'result')
        result_element.text = s
    xml_response_data = ET.tostring(xml_response)

    credentials = pika.PlainCredentials('admin', 'admin')
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq', credentials=credentials, heartbeat=0))
    channel = connection.channel()
    channel.basic_publish(exchange='d_exchange', routing_key='to_manager', body=xml_response_data, properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent))
    channel.close()



def handle_manager_request(channel, method, properties, body):
        message = body.decode('utf-8')

        xml_request_data = ET.fromstring(message)
        request_id = xml_request_data.attrib['requestId']
        hash = xml_request_data.attrib['hash']
        alphabet = xml_request_data.attrib['alphabet']
        max_length = int(xml_request_data.attrib['maxLength'])
        part_number = int(xml_request_data.attrib['partNumber'])
        part_count = int(xml_request_data.attrib['partCount'])

        crack(request_id, hash, alphabet, max_length, part_number, part_count)
        
        channel.basic_ack(delivery_tag=method.delivery_tag)
    

@retry((pika.exceptions.ChannelClosed, pika.exceptions.AMQPConnectionError, socket.gaierror), delay=5)
def consumer():
    credentials = pika.PlainCredentials('admin', 'admin')
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq', credentials=credentials, heartbeat=0))
    channel = connection.channel()
    print('Connected to RabbitMQ')

    channel.exchange_declare(exchange='d_exchange', exchange_type='direct', durable=True)
    channel.queue_declare(queue='worker_queue', durable=True)
    channel.queue_bind(exchange='d_exchange', queue='worker_queue', routing_key='to_worker')

    channel.basic_consume(queue='worker_queue', on_message_callback=handle_manager_request)
    channel.basic_qos(prefetch_count=1)
    channel.start_consuming()


threads = []

for _ in range(2):
    thread = threading.Thread(target=consumer, daemon=False)
    threads.append(thread)
    thread.start()

print(f'started on {len(threads)} threads')

for thread in threads:
    thread.join()

