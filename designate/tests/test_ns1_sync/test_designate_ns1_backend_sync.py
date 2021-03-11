# Copyright 2021 NS1 Inc. https://www.ns1.com
#
# Author: Dragan Blagojevic <dblagojevic@daitan.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

#
#Usage:
#
#test_designate_ns1_backend_sync.py -c <command> -a <designate dns api url> -u <username> -p <password> -z <zone base name> -i <number of iterations>'
#        -c: command : either 'create' or 'delete'
#Example 1:
#Create 10 zones with 10 records each on designate. Manually verify that all zones/records are propagated to NS1 backend
#test_designate_ns1_backend_sync.py -c create -a http://192.168.0.60 -u admin -p password -z ab -i 10
#
#Example 2:
#Delete all zones on designate. Manually verify that all zones/records are deleted from NS1 backend
#test_designate_ns1_backend_sync.py -c delete -a http://192.168.0.60 -u admin -p password -z ab -i 10


import requests
import sys, getopt

class Zone:
    def __init__(self, name, email):
        self.name=name
        self.email=email
        self.id=""

class Recordset:
    def __init__(self, zone, recname, recsequence):
        self.zoneid=zone.id
        self.data = {
            "name" : recname + str(recsequence) + "." + zone.name,
            "description" : "This is an example record set.",
            "type" : "A",
            "ttl" : 3600,
            "records" : [
                "10.1.0." + str(recsequence)
            ]
        }

class DesignateApiClient():

    def __init__(self, designate_url, username, password, zone_prefix, count):
        self.api_endpoint = designate_url + "/dns/v2/zones"
        self.token_endpoint = designate_url + "/identity/v3/auth/tokens"
        self.username = username
        self.password = password
        self.zone_prefix = zone_prefix
        self.count = count
        
        self.api_token = self.get_auth_token()            

        self.headers = {
            "X-Auth-Token": self.api_token
        }
      

    def _build_url(self, zone):
        return "%s/v1/zones/%s" % (self.api_endpoint, zone.name.rstrip('.'))

    def get_auth_token(self):
        data = {
            "auth": {
                "identity": {
                    "methods": [
                        "password"
                    ],
                    "password": {
                        "user": {
                            "domain": {
                                "name": "Default"
                            },
                            "name": self.username,
                            "password": self.password
                        }
                    }
                },
                "scope": {
                    "project": {
                        "domain": {
                            "name": "Default"
                        },
                        "name": "admin"
                    }
                }
            }
        }   
        try:
            response = requests.post(
                self.token_endpoint,
                json=data
            )

            if response.status_code==201:
                return response.headers["X-Subject-Token"]
            else:
                return ""
        except requests.HTTPError as e:
            print("Exception while trying to get token:")
            print(e)

    def create_zone(self, zone):
        """Create a DNS zone"""
        
        data = {
            "name": zone.name,
            "email": zone.email
        }

        try:
            response = requests.post(
                self.api_endpoint,
                json=data,
                headers=self.headers
            )
            if not response.ok:
                print("Create zone status code: %s" % response.status_code)
                print(response.json())
                return ""
            body=response.json()                   
            return body['id']
        except requests.HTTPError as e:
            print("Exception on create zone:")
            print(e)            

    def create_zones(self):
        zoneList=[]
        for i in range(self.count):
            zone = Zone(self.zone_prefix + str(i) + ".com.","e@e.com")
            zoneList.append(zone)
        
        print("Creating zones...")

        for i in range(self.count):
            z = zoneList[i]
            z.id = self.create_zone(z)
            if z.id == "":
                print("Error creating zone")
                return

            print("Zone created: %s" % z.name)
            for j in range(self.count):
                rec = Recordset(z, "www",j)                
                self.create_record(z,rec)
                print("Zone %s record reated: %s" % (z.name, rec.data['name']))

    def create_record(self, zone, record):        
        try:                        
            response = requests.post(
                self.api_endpoint + "/" + zone.id + "/recordsets",
                json=record.data,
                headers=self.headers
            )            
            print(response.status_code)
            
        except requests.HTTPError as e:
            print("Exception on create record:")
            print(e)

    def delete_zone(self, zone):
        """Delete a DNS zone"""
        
        try:                        
            response = requests.delete(
                self.api_endpoint + "/" + zone.id,
                headers=self.headers
            )            
            if response.status_code == 202:
                print("Zone %s deleted" % zone.name)
            else:
                print("Error deleting zone %s Error code: " % response.status_code)
        except requests.HTTPError as e:
            print(e)           

    
    def delete_zones(self):
        zone_list = self.get_zones()
        for z in zone_list:
            self.delete_zone(z)

    def get_zones(self):
        "Get zone list"
        try:
            response = requests.get(
                self.api_endpoint,
                headers=self.headers
            )
            zone_list = []
            body = response.json()
            
            for item in body['zones']:           
                zone = Zone(item['name'],"")                
                zone.id = item['id']
                zone_list.append(zone)
            
            return zone_list

        except requests.HTTPError as e:
            print(e)
    

def main(argv):
    
    try:
        opts, args = getopt.getopt(argv,"c:a:u:p:z:i:")
        if len(opts)<6:
            print('Usage:')
            print('test_designate_ns1_backend_sync.py -c <command> -a <designate dns api url> -u <username> -p <password> -z <zone base name> -i <number of iterations>')
            print('     -c: create or delete')
            sys.exit(2)

    except getopt.GetoptError:
        print('Usage:')
        print('test_designate_ns1_backend_sync.py -c <command> -a <designate dns api url> -u <username> -p <password> -z <zone base name> -i <number of iterations>')
        print('     -c: create or delete')
        sys.exit(2)
    
    for opt, arg in opts:
        if opt == '-c':
            command = arg            
        elif opt == '-a':
            designate_url = arg            
        elif opt == '-u':
            username = arg
        elif opt == '-p':
            password = arg
        elif opt == '-z':
            zone_prefix = arg
        elif opt == '-i':
            count = int(arg)
   
    client = DesignateApiClient(designate_url, username, password, zone_prefix, count)

    if client.api_token !="":
        print("Auth Token:")
        print(client.api_token)        
    else:
        print("Error getting auth token")
        sys.exit()

    if command == "create":
        client.create_zones()
    elif command == "delete":
        client.delete_zones()        
    else:
        print("Invalid copmmand")
        sys.exit()
    
    
    print("==================================")
    print("Done.")



if __name__ == "__main__":
   main(sys.argv[1:])