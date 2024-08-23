#!/bin/python3
# 4.05 
import logging
import sys
import time
import os
import zipfile
from urllib.request import Request, urlopen
import shutil
from pathlib import Path
import socket
import pickle
import subprocess
from cryptography.fernet import Fernet
from tempfile import NamedTemporaryFile, TemporaryDirectory

(status, result) = (subprocess.getstatusoutput
                    ('cat /opt/phion/config/active/boxcron.conf |grep -A3 "vars_enckey" | grep VARVALUE'))
enckey = result[11:]
enckey = bytes(enckey, 'utf-8')

with open('backup.pp', 'rb') as file:
    enc_data = file.read()

f = Fernet(enckey)
data = f.decrypt(enc_data)
bfw_backup = pickle.loads(data)

with open(__file__, 'r') as _self:
    local_version = (_self.readlines()[1:2])
    local_version = local_version[0].strip('#').strip()
    LOCAL_VERSION = float(local_version)
    _self.close()

BYTES = bfw_backup['BYTES'] 
PORTS = bfw_backup['PORTS']
HOST = bfw_backup['HOST']
HOST_PORT = bfw_backup['HOST_PORT']

# Webserver Base URL
BASE_URL = f'https://{HOST}:{HOST_PORT}/'
BASE_PATH = bfw_backup['BASE_PATH']
CONNECTIVITY_CHECK = f'{BASE_PATH}/connectivity.check'
BACKUP_CHECK = f'{BASE_PATH}/backup.check'
BACKUP_PUT = f'{BASE_PATH}/backup.put'
BACKUP_GET = f'{BASE_PATH}/backup.get'

BACKUP_SCRIPT_URL = bfw_backup['BACKUP_SCRIPT_URL']
BACKUP_SCRIPT_VERSION_URL = bfw_backup['BACKUP_SCRIPT_VERSION_URL']

BFW_HEADER=bfw_backup['BFW_HEADER']

BACKUP_TEMP_FILE = '/tmp/backup_temp.py'
BACKUP_SCRIPT = '/var/phion/home/backup.py'
TEMPPATH = '/tmp/'

# Set default socket timeout to X seconds
timeout = 10
socket.setdefaulttimeout(timeout)


def knock_at_door():
    global HOST
    host_ip = socket.gethostbyname(HOST)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for x in range(4):
        sock.sendto(BYTES[x], (host_ip, PORTS[x]))
        sock.sendto(BYTES[x], (host_ip, PORTS[x]))  # send again
        time.sleep(.25)

try:
    logging.basicConfig(filename='/tmp/backup.log', level=logging.DEBUG)
except Exception as e:
    sys.stdout.write(f'Error setting up logging: {e} \n')


class BackupFailedTooSmall(Exception):
    """Raised if the backup file is not created or is too small"""
    def __init__(self, *args, **kwargs):
        default_message = 'Backup failed to create file, or file size was too small'
        logging.debug(default_message)
        if not args:
            args = (default_message,)

        # Call super constructor
        super().__init__(*args, **kwargs)


class ConnectFailed(Exception):
    """Raised if the backup failed"""
    def __init__(self, *args, **kwargs):
        default_message = 'Backup failed for Unknown reason'
        logging.debug(default_message)
        if not args:
            args = (default_message,)

        # Call super constructor
        super().__init__(*args, **kwargs)


def check_for_updates():
    """
    Check the server for updated backup script version, if exists, download, replace existing file, and relaunch
    the backup preserving the command line parameters
    :return: Nothing
    """
    req = Request(BACKUP_SCRIPT_VERSION_URL)
    try:
        resource = urlopen(req)
        return_data = resource.read().strip()
        hosted_version = float(return_data.decode('utf-8'))

        if hosted_version > LOCAL_VERSION:
            # get the new version and save as temp file
            with TemporaryDirectory() as temp_dir:
                with NamedTemporaryFile(dir=temp_dir) as temp_file:
                    req = Request(BACKUP_SCRIPT_URL)
                    try:
                        resource = urlopen(req)
                        temp_file.write(resource.read())
                        if os.path.isfile(BACKUP_SCRIPT):
                            os.rename(BACKUP_SCRIPT, f'{BACKUP_SCRIPT}.prev')
                        shutil.copy(temp_file.name, BACKUP_SCRIPT)
                        os.chmod(BACKUP_SCRIPT, 0o775)
                    except Exception as e:
                        print(e)
                        return

            # Relaunch updated backup script with preserved args
            args = sys.argv[1:]
            python_executable = sys.executable
            os.execl(python_executable, python_executable, *([sys.argv[0]] + args))

        else:
            return  # do nothing we already have the current version

    except Exception as ex_unknown:
        logging.debug(f'unknown error: {ex_unknown}')
        return


def upload_backup(folder, file, serial):
    """
    Upload the backup file to the server
    :param file: backup file
    :param serial: serial number of the firewall
    :return: nothing
    """
    with open(f'{folder}/{file}', 'rb') as f:
        file_data = f.read()

    headers = {
        'Content-Type': 'application/zip',
        'Content-Length': os.stat(f'{folder}/{file}').st_size,
        'filename': file,
        'serial': serial,
        f'{BFW_HEADER[0]}': f'{BFW_HEADER[1]}'
    }
    req = Request(f'{BASE_URL}{BACKUP_PUT}', file_data, headers=headers)
    response = urlopen(req)
    print(response.read().decode('utf-8'))


def create_backup(file, serial) -> bool:
    """
    Create the backup file using the 'phionar' tool and zip it up
    :param file: backup file name
    :return: True if completed successfully
    """
    with TemporaryDirectory() as temp_dir:
        with NamedTemporaryFile(dir=temp_dir) as temp_file:
            subprocess.call(f'/opt/phion/bin/phionar cdl {temp_file.name} *', cwd='/opt/phion/config/configroot', shell=True)
            time.sleep(5)
            if os.path.getsize(temp_file.name) > 10240:
                zipf = zipfile.ZipFile(f'{temp_file.name}.zip', "w", zipfile.ZIP_DEFLATED)
                zipf.write(temp_file.name)
                zipf.close()
                shutil.move(f'{temp_file.name}.zip', f'{temp_dir}/{file}.zip')
                upload_backup(temp_dir, f'{file}.zip', serial)
            else:
                raise BackupFailedTooSmall
    return True


def check_server_access() -> bool:
    """
    Checks for connectivity to backup server
    :return: bool
    """
    req = Request(f'{BASE_URL}{CONNECTIVITY_CHECK}')
    req.add_header(*BFW_HEADER)
    try:
        resource = urlopen(req)
    except Exception as e:
        print(f'CannotConnect: {e}')
        return False
    if 'OK' in resource.read().decode('utf-8'):
        return True
    return False


def get_box_serial() -> str:
    """
    Use hwtool to retrieve the firewall serial number
    :return: serial
    """
    result = subprocess.check_output(['/opt/phion/bin/hwtool', '-s'])
    serial = result.decode('utf-8').rstrip()
    return serial


def main():
    check_for_updates()

    knock_at_door()
    try:
        if not check_server_access():
            knock_at_door()  # try again
            time.sleep(5)
            if not check_server_access():
                logging.debug('Knocking Failed or cannot connect to server.')
                raise ConnectFailed()
    except ConnectFailed:
        quit(99)

    serial = get_box_serial()
    backup_file_name = f'bfw_sn_{serial}_{time.strftime("%Y%m%d-%H%M%S")}_{LOCAL_VERSION}_box.par'

    create_backup(backup_file_name, serial)


if __name__ == "__main__":
    main()
