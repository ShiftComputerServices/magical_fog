#!/bin/python3
# 0.1
import os
from urllib.request import Request, urlopen
from tempfile import NamedTemporaryFile, TemporaryDirectory
import shutil

SCRIPT_VERSION_URL: str = ('https://raw.githubusercontent.com/ShiftComputerServices/magical_fog/main/badactors/version.txt')
SCRIPT_URL: str = 'https://raw.githubusercontent.com/ShiftComputerServices/magical_fog/main/badactors/badactors.py'
SCRIPT: str = '/phion0/home/badactors.py'
LOCAL_VERSION: float = 0.0

try:
    with open(SCRIPT, 'r') as script:
        local_version = (script.readlines()[1:2])
        local_version = local_version[0].strip('#').strip()
        LOCAL_VERSION = float(local_version)
        script.close()
except FileNotFoundError:
    pass  # Move on to downloading the latest version.

req = Request(SCRIPT_VERSION_URL)
try:
    resource = urlopen(req)
    return_data = resource.read().strip()
    hosted_version = float(return_data.decode('utf-8'))

    if hosted_version > LOCAL_VERSION:
        # get the new version and save as temp file
        with TemporaryDirectory() as temp_dir:
            with NamedTemporaryFile(dir=temp_dir) as temp_file:
                req = Request(SCRIPT_URL)
                try:
                    resource = urlopen(req)
                    temp_file.write(resource.read())
                    if os.path.isfile(SCRIPT):
                        os.rename(SCRIPT, f'{SCRIPT}.prev')
                    shutil.copy(temp_file.name, SCRIPT)
                    os.chmod(SCRIPT, 0o775)
                except Exception as e:
                    print(e)

    else:
        pass  # do nothing we already have the current version
except Exception as e:
    print(e)
