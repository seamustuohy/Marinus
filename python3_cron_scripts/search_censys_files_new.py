#!/usr/bin/python3

# Copyright 2018 Adobe. All rights reserved.
# This file is licensed to you under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License. You may obtain a copy
# of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR REPRESENTATIONS
# OF ANY KIND, either express or implied. See the License for the specific language
# governing permissions and limitations under the License.

"""
This script parses the file that was downloaded by get_files and identifies matches.
This script can be run daily because it checks for conflicting processes.
That said, the search_files script can take over a 2 days to run and take 99% of a core.

It should be run daily approximately 10.5 hours after get_files run its checks (8 hours to
download and then an additional 2+ hours to unpack).

Therefore, if get_file runs Monday at 1am and finishes Tuesday at 11:20am, then search
files can kick in at 11:30am.

Eventually, the two files can be joined as one so as not to play the crontab game.
"""

import json
import os.path
import re
import subprocess
import sys
from datetime import datetime

from netaddr import IPAddress, IPNetwork

from libs3 import RemoteMongoConnector
from libs3.ZoneManager import ZoneManager


# Constants for output files
FILENAME_FILE = "filename.txt"


def is_running(process):
    """
    Is the provided process name is currently running?
    """
    proc_list = subprocess.Popen(["ps", "axw"], stdout=subprocess.PIPE)
    for proc in proc_list.stdout:
        if re.search(process, str(proc)):
            return True
    return False


def get_aws_ips(RMC, aws_ips):
    """
    Get the list of AWS CIDRs.
    """
    aws_ips_collection = RMC.get_aws_ips_connection()

    results = aws_ips_collection.find({})
    for result in results[0]['prefixes']:
        aws_ips.append(IPNetwork(result['ip_prefix']))


def get_azure_ips(RMC, azure_ips):
    """
    Get the list of Azure CIDRs.
    """
    azure_ips_collection = RMC.get_azure_ips_connection()

    results = azure_ips_collection.find({})
    for result in results[0]['prefixes']:
        azure_ips.append(IPNetwork(result['ip_prefix']))


def check_in_cidr(ip_addr, cidrs):
    """
    Is the provided IP in one of the provided CIDRs?
    """
    try:
        local_ip = IPAddress(ip_addr)
        for network in cidrs:
            if local_ip in network:
                return True
    except:
        return False
    return False


def is_aws_ip(ip_addr, aws_ips):
    """
    Is the provided IP within one of the AWS CIDRs?
    """
    return check_in_cidr(ip_addr, aws_ips)


def is_azure_ip(ip_addr, azure_ips):
    """
    Is the provided IP within one of the Azure CIDRs?
    """
    return check_in_cidr(ip_addr, azure_ips)


def check_in_org(entry, orgs):
    """
    Obtain the organization from the entry's SSL certificate.
    Determine whether the org from the certificate is in the provided list of orgs.
    """
    if "p443" in entry:
        try:
            value = entry["p443"]["https"]["tls"]["certificate"]["parsed"]["subject"]["organization"]
        except KeyError:
            return False

        for org in orgs:
            if org in value:
                return True

    return False

def zone_compare(value, zones):
    utf_val = value
    for zone in zones:
        if utf_val.endswith("." + zone) or utf_val == zone:
            return zone
    return None


def check_in_zone(entry, zones):
    """
    Obtain the DNS names from the common_name and dns_zones from the entry's SSL certificate.
    Determine if the entry's DNS names is in the list of provided zones.
    Return the matched zone.
    """
    cert_zones = []

    if "p443" in entry:
        try:
            temp1 = entry["p443"]["https"]["tls"]["certificate"]["parsed"]["subject"]["common_name"]
        except KeyError:
            temp1 = []

        try:
            temp2 = entry["p443"]["https"]["tls"]["certificate"]["parsed"]["extensions"]["subject_alt_name"]["dns_names"]
        except KeyError:
            temp2 = []

        value_array = temp1 + temp2
        for value in value_array:
            zone = zone_compare(value, zones)
            if zone is not None and zone not in cert_zones:
                cert_zones.append(zone)

        return cert_zones

    return []


def lookup_domain(entry, zones, all_dns_collection):
    """
    This tries to determine if the IP is known in the all_dns_collection.
    """
    domain_result = all_dns_collection.find({'value': entry['ip']})
    domains = []
    domain_zones = []
    if domain_result is not None:
        for result in domain_result:
            domains.append(result['fqdn'])

    if len(domains) > 0:
        for domain in domains:
            zone = zone_compare(domain, zones)
            if zone is not None:
                domain_zones.append(zone)

    return (domains, domain_zones)


def insert_result(entry, results_collection):
    """
    Insert the matched IP into the collection of positive results.
    This was done as an update because it was clear whether Censys would de-duplicate.
    """
    entry["createdAt"] = datetime.utcnow()
    results_collection.update({"ip": entry['ip']}, entry, upsert=True)


def main():
    """
    Begin main...
    """

    if is_running("get_censys_files.py"):
        """
        Check to see if a download is in process...
        """
        now = datetime.now()
        print(str(now) + ": Can't run due to get_files running. Goodbye!")
        exit(0)


    if is_running(os.path.basename(__file__)):
        """
        Check to see if a previous attempt to parse is still running...
        """
        now = datetime.now()
        print(str(now) + ": I am already running! Goodbye!")
        exit(0)

    # Make the relevant database connections
    RMC = RemoteMongoConnector.RemoteMongoConnector()

    # Verify that the get_files script has a recent file in need of parsing.
    jobs_collection = RMC.get_jobs_connection()

    status = jobs_collection.find_one({'job_name':'censys'})
    if status['status'] != "DOWNLOADED":
        now = datetime.now()
        print(str(now) + ": The status is not set to DOWNLOADED. Goodbye!")
        exit(0)


    now = datetime.now()
    print("Starting: " + str(now))

    # Collect the list of available zones
    zones = ZoneManager.get_distinct_zones(RMC)

    print("Zones: " + str(len(zones)))

    # Collect the list of AWS CIDRs
    aws_ips = []
    get_aws_ips(RMC, aws_ips)

    print("AWS IPs: " + str(len(aws_ips)))

    # Collect the list of Azure CIDRs
    azure_ips = []
    get_azure_ips(RMC, azure_ips)

    print("Azure IPs: " + str(len(azure_ips)))

    # Collect the list of known CIDRs
    ip_zones_collection = RMC.get_ipzone_connection()

    results = ip_zones_collection.find({'status': {"$ne": "false_positive"}})
    cidrs = []
    for entry in results:
        cidrs.append(IPNetwork(entry['zone']))

    print("CIDRs: " + str(len(cidrs)))

    # Get the current configuration information for Marinus.
    config_collection = RMC.get_config_connection()

    configs = config_collection.find({})
    orgs = []
    for org in configs[0]['SSL_Orgs']:
        orgs.append(org)

    print("Orgs: " + str(len(orgs)))

    # Obtain the name of the decompressed file.
    filename_f = open(FILENAME_FILE, "r")
    decompressed_file = filename_f.readline()
    filename_f.close()

    # For manual testing: decompressed_file = "ipv4.json"

    now = datetime.now()
    print(str(now) + ": Beginning file processing...")

    # Remove old results from the database
    results_collection = RMC.get_results_connection()
    results_collection.remove({})
    all_dns_collection = RMC.get_all_dns_connection()

    try:
        with open(decompressed_file, "r") as dec_f:
            for line in dec_f:
                try:
                    entry = json.loads(line)

                    """
                    Does the SSL certificate match a known organization?
                    Is the IP address in a known CIDR?
                    """
                    if check_in_org(entry, orgs) or \
                       check_in_cidr(entry['ip'], cidrs):
                            entry['zones'] = check_in_zone(entry, zones)
                            entry['aws'] = is_aws_ip(entry['ip'], aws_ips)
                            entry['azure'] = is_azure_ip(entry['ip'], azure_ips)
                            (domains, zones) = lookup_domain(entry, zones, all_dns_collection)
                            if len(domains) > 0:
                                entry['domains'] = domains
                                if len(zones) > 0:
                                    for zone in zones:
                                        if zone not in entry['zones']:
                                            entry['zones'].append(zone)
                            insert_result(entry, results_collection)
                    # else:
                    #     #This will add days to the amount of time necessary to scan the file.
                    #     matched_zones = check_in_zone(entry, zones)
                    #     if matched_zones != []:
                    #         entry['zones'] = matched_zones
                    #         entry['aws'] = is_aws_ip(entry['ip'], aws_ips)
                    #         entry['azure'] = is_azure_ip(entry['ip'], azure_ips)
                    #         insert_result(entry, results_collection)
                except ValueError as err:
                    print("Value Error!")
                    print(str(err))
                except:
                    print("Line unexpected error:", sys.exc_info()[0])
                    print("Line unexpected error:", sys.exc_info()[1])
    except IOError as err:
        print("I/O error({0}): {1}".format(err.errno, err.strerror))
        exit(0)
    except:
        print("Unexpected error:", sys.exc_info()[0])
        print("Unexpected error:", sys.exc_info()[1])
        exit(0)

    # Indicate that the processing of the job is complete and ready for download to Marinus
    jobs_collection.update_one({'job_name': 'censys'},
                               {'$currentDate': {"updated": True},
                                "$set": {'status': 'COMPLETE'}})


    now = datetime.now()
    print("Ending: " + str(now))


if __name__ == "__main__":
    main()

exit(0)
