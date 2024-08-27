#!/bin/python3
# 2.0
import subprocess

IMPORT_LIST_FILE = '/var/phion/home/import.list'

# Enable or disable lists here.
SPAMHAUS = True
SPAMHOUS_DROP_URL ='https://www.spamhaus.org/drop/drop.txt'

DSHIELD = True
DSHIELD_URL = 'https://feeds.dshield.org/block.txt'

TOR = True
TOR_URL = 'https://check.torproject.org/torbulkexitlist'

ET_KNOWN = True
ET_KNOWN_URL = 'https://cpdbl.net/lists/etknown.list'

clean_list = []

def dshield():
    (status, ds_list) = subprocess.getstatusoutput(f'curl -s {DSHIELD_URL}')
    ds_list = ds_list.split('\n')
    for item in range(len(ds_list)):
        try:
            clean_list.append(ds_list[item].split("\t")[0] + '/' + ds_list[item].split("\t")[2])
        except IndexError:
            pass
        except Exception as DS_ex:
            return DS_ex
    return True

def spamhaus():
    try:
        (status, sh_list) = subprocess.getstatusoutput(f'curl -s {SPAMHOUS_DROP_URL}')
        sh_list = sh_list.split('\n')
        for item in range(len(sh_list)):
            host = sh_list[item].split(' ')[0]
            if len(host) > 7:
                clean_list.append(host)
            else:
                pass
    except Exception as SH_ex:
        return SH_ex
    return True


# Get the TOR bulk exit list of hosts
def tor():
    try:
        (status, tor_list) = subprocess.getstatusoutput(f'curl -s {TOR_URL}')
        tor_list = tor_list.split('\n')
        for item in range(len(tor_list)):
            if len(tor_list[item]) > 15:
                pass
            else:
                clean_list.append(tor_list[item])
    except Exception as TOR_ex:
        return TOR_ex
    return True


def et_known():
    # Get the Emerging Threat List
    try:
        (status, et_list) = subprocess.getstatusoutput(f'curl -s {ET_KNOWN_URL}')
        et_list = et_list.split('\n')
        for item in range(len(et_list)):
            if len(et_list[item]) > 15:
                pass
            else:
                clean_list.append(et_list[item])
    except Exception as dshield_ex:
        return False

    return True


def main():
    spamhaus_complete = False
    dshield_complete = False
    tor_complete = False
    et_known_complete = False

    if DSHIELD:
        dshield_complete = dshield()

    if SPAMHAUS:
        spamhaus_complete = spamhaus()

    if TOR:
        tor_complete = tor()

    if ET_KNOWN:
        et_known_complete = et_known()

    # status output
    print(f'Total IP addresses or Subnets: {len(clean_list)}')
    print(f'Dshield: {dshield_complete} | Spamhaus: {spamhaus_complete}'
          f' | Tor: {tor_complete} | Emerging Threats: {et_known_complete}')

    try:
        with open(IMPORT_LIST_FILE, 'w') as f:
            for line in clean_list:
                if len(line) > 1:
                    f.write(f'{line}\n')

    except Exception as file_ex:
        print(file_ex)


    # import the list to Custom Address List 1
    # /opt/phion/bin/CustomExternalAddrImport -i $FILE -o 1
    subprocess.run(['/opt/phion/bin/CustomExternalAddrImport', '-i', '/var/phion/home/import.list', '-o', '1'])


if __name__ == "__main__":
    main()
