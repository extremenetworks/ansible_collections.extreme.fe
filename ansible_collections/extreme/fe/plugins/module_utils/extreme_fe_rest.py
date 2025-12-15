# -*- coding: utf-8 -*-
# Copyright (c) 2025 Extreme Networks
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils._text import to_text

class ExtremeFeRest(object):
    def __init__(self, module):
        self.module = module
        self.connection = Connection(module._socket_path)

    def get(self, path):
        return self.send_request('GET', path)

    def post(self, path, data=None):
        return self.send_request('POST', path, data)

    def put(self, path, data=None):
        return self.send_request('PUT', path, data)

    def delete(self, path):
        return self.send_request('DELETE', path)

    def send_request(self, method, path, data=None):
        try:
            response = self.connection.send_request(data, path=path, method=method)
            return response
        except ConnectionError as e:
            self.module.fail_json(msg=to_text(e))
