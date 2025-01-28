#!/bin/python3
import requests
import json
import subprocess
import time

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


def cloudflare_get_records():
    url = f'https://api.cloudflare.com/client/v4/zones/{ZONE}/dns_records'
    return requests.get(url, headers=HEADERS).json()


def main():
    exists = False
    ip = get_ip()
    serial = get_serial()
    response = cloudflare_get_records()
    if response['success']:
        for record in response['result']:
            if serial in record['name']:  # record exists
                exists = True
                print('Record exists: ')
                (comment_text, comment_date) = record['comment'].split(':')
                if (ip != record['content']) or (time.time() - int(comment_date) > 3600):  # lets update
                    print('Updating Record...')
                    DATA['content'] = record['content']
                    DATA['name'] = record['name']
                    DATA['comment'] = f'{comment_text}:{str(round(time.time()))}'
                    DATA['id'] = record['id']
                    print(cloudflare_update(DATA))
                else:
                    print('Record is up-to-date')

        if not exists:  # No record Exists, create it.
            print('No Record, creating...')
            DATA['content'] = ip
            DATA['name'] = serial
            DATA['comment'] = f'{COMMENT}:{str(round(time.time()))}'
            DATA['id'] = ''
            print(cloudflare_update(DATA))
    else:
        print(response['message'])

if __name__ == '__main__':
    main()

