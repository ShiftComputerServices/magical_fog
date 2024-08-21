#!/bin/python3
# 4.00
import logging
import sys
import time
import os
import zipfile
from urllib.request import Request, urlopen
import requests
import hashlib
import shutil
from pathlib import Path
import socket
import pickle
import subprocess
from cryptography.fernet import Fernet

(status, result) = (subprocess.getstatusoutput
                    ('cat /opt/phion/config/active/boxcron.conf |grep -A3 "vars_enckey" | grep VARVALUE'))
enckey = result[11:]
enckey = bytes(enckey, 'utf-8')

with open('backup.pp', 'rb') as file:
    enc_data = file.read()

f = Fernet(enckey)
data = f.decrypt(enc_data)
bfw_backup = pickle.loads(data)

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


def check_md5(good_hash):
    """
    Check file against known good md5
    :param good_hash: known good hash
    :return: bool
    """
    file_name = BACKUP_TEMP_FILE

    # Open,close, read file and calculate MD5 on its contents
    with open(file_name, 'rb') as file_to_check:
        # read and MD5 the file
        data = file_to_check.read()
        file_to_check_md5 = hashlib.md5(data).hexdigest()
    # Finally compare original MD5 with freshly calculated
    if good_hash == file_to_check_md5:
        return True
    else:
        return False


def get_local_ver():
    """
    checks the local backup script version
    :return: the version of the script
    """
    if os.path.isfile(BACKUP_SCRIPT):
        with open(BACKUP_SCRIPT, 'r') as f:
            local_version = (f.readlines()[1:2])
            local_version = local_version[0].strip('#').strip()
            if 'port' in local_version:
                local_version = 0.0
            else:
                local_version = float(local_version)
    else:  # no file so 'touch' it set the version to 0.0
        Path(BACKUP_SCRIPT).touch()
        local_version = 0.0
    return local_version


def check_for_updates():
    """
    Check the server for updated backup script version, if exists, download, replace existing file, and relaunch
    the backup preserving the command line parameters
    :return: Nothing
    """
    req = Request('BACKUP_SCRIPT_VERSION_URL')
    try:
        resource = urlopen(req)
        return_data = resource.read().strip()
        hosted_version = float(return_data.decode('utf-8'))

        local_version = get_local_ver()

        if hosted_version > local_version:
            # get the new version and save as temp file
            req = Request(BACKUP_SCRIPT_URL)
            try:
                resource = urlopen(req)
                with open(BACKUP_TEMP_FILE, 'wb') as temp_file:
                    temp_file.write(resource.read())
                    temp_file.close()
                verified = True
            except:
                verified = False

            if not verified:
                # delete the file.
                if os.path.isfile(BACKUP_TEMP_FILE):
                    os.remove(BACKUP_TEMP_FILE)

            else:
                # delete the current on disk backup file, and replace with the new file from server.
                if os.path.isfile(BACKUP_SCRIPT):
                    os.remove(BACKUP_SCRIPT)
                    shutil.move(BACKUP_TEMP_FILE, BACKUP_SCRIPT)
                    os.chmod(BACKUP_SCRIPT, 0o775)

                # Relaunch updated backup script with preserved args
                args = sys.argv[1:]
                python_executable = sys.executable
                os.execl(python_executable, python_executable, *([sys.argv[0]] + args))

        else:
            return  # do nothing we already have the current version

    except Exception as ex_unknown:
        logging.debug(f'unknown error: {ex_unknown}')
        return


def upload_backup(file, serial):
    """
    Upload the backup file to the server
    :param file: backup file
    :param serial: serial number of the firewall
    :return: nothing
    """
    with open(f'/tmp/{file}', 'rb') as f:
        file_data = f.read()

    headers = {
        'Content-Type': 'application/zip',
        'Content-Length': os.stat(f'/tmp/{file}').st_size,
        'filename': file,
        'serial': serial,
        f'{BFW_HEADER[0]}': f'{BFW_HEADER[1]}'
    }
    req = Request(f'{BASE_URL}{BACKUP_PUT}', file_data, headers=headers)
    response = urlopen(req)
    print(response.read().decode('utf-8'))


def create_backup(file) -> bool:
    """
    Create the backup file using the 'phionar' tool
    :param file: backup file name
    :return: True if completed successfully
    """
    subprocess.call(f'/opt/phion/bin/phionar cdl {TEMPPATH}{file} *', cwd='/opt/phion/config/configroot', shell=True)
    time.sleep(5)
    if not os.path.exists(f'{TEMPPATH}{file}') or os.path.getsize(f'{TEMPPATH}{file}') < 10240:
        clean_up_files(file, '')
        raise BackupFailedTooSmall
    return True


def compress_backup(file):
    """
    Compress the file passed
    :param file: uncompressed backup file
    :return: compressed file name
    """
    zipf = zipfile.ZipFile(f'{TEMPPATH}{file}.zip', "w", zipfile.ZIP_DEFLATED)
    zipf.write(f'{TEMPPATH}{file}')
    zipf.close()
    return f'{file}.zip'


def clean_up_files(_backup_file='', _compressed_backup=''):
    """
    Clean up files left over after processing backups
    :param _backup_file: raw backup file
    :param _compressed_backup: compressed backup file
    :return:
    """
    if _backup_file is not '':
        if os.path.exists(f'{TEMPPATH}{_backup_file}'):
            os.remove(f'{TEMPPATH}{_backup_file}')
    if _compressed_backup is not '':
        if os.path.exists(f'{TEMPPATH}{_compressed_backup}'):
            os.remove(f'{TEMPPATH}{_compressed_backup}')


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
    serial = get_box_serial()
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

    check_for_updates()

    backup_file_name = f'bfw_sn_{serial}_{time.strftime("%Y%m%d-%H%M%S")}_box.par'

    create_backup(backup_file_name)

    compressed_backup_file_name = compress_backup(backup_file_name)

    upload_backup(compressed_backup_file_name, serial)

    clean_up_files(backup_file_name, compressed_backup_file_name)


if __name__ == "__main__":
    main()
