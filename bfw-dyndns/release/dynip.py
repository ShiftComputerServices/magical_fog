#!/bin/python3
import requests
import json
import subprocess
import time
from dateutil import parser
import datetime

(status, result) = (subprocess.getstatusoutput
                    ('cat /opt/phion/config/active/boxcron.conf |grep -A3 "vars_cloudflare" | grep VARVALUE'))
TOKEN = result[11:]

(status2, result) = (subprocess.getstatusoutput
                    ('cat /opt/phion/config/active/boxcron.conf |grep -A3 "vars_comment" | grep VARVALUE'))
COMMENT = result[11:]

ZONE = '39a19891e7816bc386bd4dcd77fd7fbf'
TTL = 300

HEADERS = {
        'Authorization': f'Bearer {TOKEN}',
        'Content-Type': 'application/json'
    }

DATA = {'comment': COMMENT,
        'content': '',
        'name': '',
        'proxied': False,
        'ttl': TTL,
        'type': 'A',
        'id': ''
        }

def get_serial() -> str:
    """
        Use hwtool to retrieve the firewall serial number
        :return: serial
        """
    result = subprocess.check_output(['/opt/phion/bin/hwtool', '-s'])
    serial = result.decode('utf-8').rstrip()
    return serial


def get_ip():
    response = requests.get('https://api.ipify.org?format=json')
    if response.status_code == 200:
        print('ipify')
        ip = json.loads(response.text)['ip']
        return ip

    response = requests.get("http://api.db-ip.com/v2/free/self/ipAddress")
    if response.status_code == 200:
        print('db-ip')
        ip = response.text
        return ip

    response = requests.get("https://freeipapi.com/api/json")
    if response.status_code == 200:
        print('freeipapi')
        response = json.loads(response.text)
        ip = response['ipAddress']
        return ip



def cloudflare_update(data):
    if len(data['id']) > 5:  # Update Record
        url = f'https://api.cloudflare.com/client/v4/zones/{ZONE}/dns_records/{data["id"]}'
        method = 'PATCH'
    else:  # Create Record
        url = f'https://api.cloudflare.com/client/v4/zones/{ZONE}/dns_records/'
        method = 'POST'
    payload = json.dumps(data)
    response = requests.request(method, url, data=payload, headers=HEADERS)
    return response.status_code


def cloudflare_get_records(serial):
    url = f'https://api.cloudflare.com/client/v4/zones/{ZONE}/dns_records'
    return requests.request("GET", url, headers=HEADERS, params=f'name=contains:{serial}').json()


def main():
    exists = False
    ip = get_ip()
    serial = get_serial()
    response = cloudflare_get_records(serial)
    if response['success']:
        if response['result_info']['count'] == 1:
            print('Record exists: ')
            modified_time = round(parser.isoparse(response['result'][0]['modified_on']).timestamp())
            current_time = round(datetime.datetime.now(datetime.timezone.utc).timestamp())
            delta = current_time - modified_time
            if (ip != response['result'][0]['content']) or (delta > 3600):  # lets update
                print('Updating Record...')
                DATA['content'] = response['result'][0]['content']
                DATA['name'] = response['result'][0]['name']
                DATA['comment'] = response['result'][0]['comment']
                DATA['id'] = response['result'][0]['id']
                print(cloudflare_update(DATA))
            else:
                print('Record is up-to-date')

        else:  # No record Exists, create it.
            print('No Record, creating...')
            DATA['content'] = ip
            DATA['name'] = serial
            DATA['comment'] = COMMENT
            DATA['id'] = ''
            print(cloudflare_update(DATA))
    else:
        print(response['message'])

if __name__ == '__main__':
    main()

