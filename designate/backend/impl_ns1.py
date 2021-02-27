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
import netaddr
import requests
from oslo_config import cfg
from oslo_log import log as logging
from six.moves import urllib

from designate import exceptions
from designate.backend import base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class NS1Backend(base.Backend):
    __plugin_name__ = 'ns1'

    __backend_status__ = 'untested'

    def __init__(self, target):      
        super(NS1Backend, self).__init__(target)

        self.api_endpoint = "https://" + self.options.get('api_endpoint')
        self.api_token = self.options.get('api_token')

        self.headers = {
            "X-NSONE-Key": self.api_token
        }

    def _build_url(self, zone):                
                
        return "%s/v1/zones/%s" % (self.api_endpoint, zone.name.rstrip('.'))

    def _check_zone_exists(self, zone):
        
        getzone = requests.get(
            self._build_url(zone),
            headers=self.headers,
            verify=False
        )        
        return getzone.status_code == 200

    def create_zone(self, context, zone):
        """Create a DNS zone"""

        masters_host = ""
        master_port = 5354
        
        #get only first master in case there is multiple, NS1 dns supports only 1 
        for master in self.masters:
            master_host = master.host
            master_port = master.port
            break
        
        #designate requires "." at the end of the zone name, NS1 requires zone name without it         
        data = {
            "zone": zone.name.rstrip('.'),
            "secondary": {
                "enabled":True, 
                "primary_ip":master_host, 
                "primary_port":master_port
            }            
        }

        if self._check_zone_exists(zone):
            LOG.info(
                '%s exists on the server. Deleting zone before creation', zone
            )

            try:
                self.delete_zone(context, zone)
            except exceptions.Backend:
                LOG.error('Could not delete pre-existing zone %s', zone)
                raise

        try:       
            requests.put(
                self._build_url(zone),
                json=data,
                headers=self.headers,
                verify=False
            ).raise_for_status()
        except requests.HTTPError as e:
            # check if the zone was actually created 
            if self._check_zone_exists(zone):
                LOG.info("%s was created with an error. Deleting zone", zone)
                try:
                    self.delete_zone(context, zone)
                except exceptions.Backend:
                    LOG.error('Could not delete errored zone %s', zone)
            raise exceptions.Backend(e)

        self.mdns_api.notify_zone_changed(
            context, zone, self.host, self.port, self.timeout,
            self.retry_interval, self.max_retries, self.delay)

    def delete_zone(self, context, zone):
        """Delete a DNS zone"""

        # First verify that the zone exists 
        if self._check_zone_exists(zone):
            try:
                requests.delete(
                    self._build_url(zone),
                    headers=self.headers,
                    verify=False
                ).raise_for_status()
            except requests.HTTPError as e:
                raise exceptions.Backend(e)
        else:
            LOG.warning("Trying to delete zone %s but that zone is not "
                        "present in the ns1 backend. Assuming success.",
                        zone)