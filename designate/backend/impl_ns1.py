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
import requests
from oslo_config import cfg
from oslo_log import log as logging

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
        self.tsigkey_name = self.options.get('tsigkey_name', None)
        self.tsigkey_hash = self.options.get('tsigkey_hash', None)
        self.tsigkey_value = self.options.get('tsigkey_value', None)
        
        self.headers = {
            "X-NSONE-Key": self.api_token
        }

    def _build_url(self, zone):
        return "%s/v1/zones/%s" % (self.api_endpoint, zone.name.rstrip('.'))

    def _check_zone_exists(self, zone):

        try:
            getzone = requests.get(
                self._build_url(zone),
                headers=self.headers
            )
            
        except requests.HTTPError as e:            
            LOG.error('HTTP error while checking if zone exists. Zone %s', zone)
            raise exceptions.Backend(e)
        
        except requests.ConnectionError as e:
            LOG.error('Connection error while checking if zone exists. Zone %s', zone)
            raise exceptions.Backend(e)
        
        return getzone.status_code == 200

    def create_zone(self, context, zone):
        """Create a DNS zone"""

        # get only first master in case of multiple. NS1 dns supports only 1        
        # designate requires "." at end of zone name, NS1 requires omitting
        data = {
            "zone": zone.name.rstrip('.'),
            "secondary": {
                "enabled": True,
                "primary_ip": self.masters[0].host,
                "primary_port": self.masters[0].port
            }
        }
        if self.tsigkey_name:
            tsig = {
                "enabled": True,
                "hash": self.tsigkey_hash,
                "name": self.tsigkey_name,
                "key": self.tsigkey_value
            }
            data['secondary']['tsig'] = tsig

        if not self._check_zone_exists(zone):
            try:
                requests.put(
                    self._build_url(zone),
                    json=data,
                    headers=self.headers
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
        else:
            LOG.info("Can't create zone %s because it already exists", zone)

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
                    headers=self.headers
                ).raise_for_status()
            except requests.HTTPError as e:
                raise exceptions.Backend(e)
        else:
            LOG.warning("Trying to delete zone %s but that zone is not "
                        "present in the ns1 backend. Assuming success.",
                        zone)
