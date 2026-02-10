# -*- coding: utf-8 -*-
"""Ansible module to manage ExtremeNetworks Fabric Engine MLAG via HTTPAPI."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

from typing import Any, Dict, List, Optional, Union

DOCUMENTATION = r"""
module: extreme_fe_mlag
short_description: Manage MLAG on ExtremeNetworks Fabric Engine switches
version_added: 1.4.0
description:
- Manage Multi-switch Link Aggregation (MLAG) configuration on ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI transport.
- Configure MLAG peers, ports, and RSMLT (Routed Split Multi-Link Trunking) instances.
- Supports both configuration and state retrieval operations for comprehensive MLAG management.
- Handles error propagation from device REST API endpoints back to Ansible.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project.
- Fabric Engine (VOSS) specific functionality; Switch Engine (EXOS) features are limited.
- RSMLT operations are Fabric Engine specific.
requirements:
- ansible.netcommon
options:
  state:
    description:
    - Desired MLAG operation.
    type: str
    choices: [present, absent, gathered, merged, replaced, deleted]
    default: present
  config:
    description:
    - MLAG configuration parameters.
    type: dict
    suboptions:
      peers:
        description:
        - List of MLAG peers to configure.
        type: list
        elements: dict
        suboptions:
          peer_id:
            description:
            - MLAG peer identifier.
            type: str
            required: true
          peer_ip_address:
            description:
            - IP address of the MLAG peer.
            type: str
          local_ip_address:
            description:
            - Local IP address for MLAG communication.
            type: str
          local_vlan_id:
            description:
            - Local VLAN ID for MLAG communication.
            type: int
          authentication_key:
            description:
            - Authentication key for MLAG peer.
            type: str
          hello_interval:
            description:
            - Hello interval for MLAG peer communication in seconds.
            type: int
          hello_timeout:
            description:
            - Hello timeout for MLAG peer communication in seconds.
            type: int
          ports:
            description:
            - List of MLAG ports for this peer.
            type: list
            elements: dict
            suboptions:
              port_id:
                description:
                - Port identifier (LAG ID).
                type: str
                required: true
              mlag_id:
                description:
                - MLAG ID for the port.
                type: int
      rsmlt:
        description:
        - RSMLT configuration.
        type: dict
        suboptions:
          instances:
            description:
            - List of RSMLT instances to configure.
            type: list
            elements: dict
            suboptions:
              vlan_id:
                description:
                - VLAN ID for RSMLT instance.
                type: int
                required: true
              enabled:
                description:
                - Enable/disable RSMLT instance.
                type: bool
                default: true
              hold_up_timer:
                description:
                - Hold up timer value in seconds (0-3600, or 9999 for infinity).
                type: int
                default: 0
              hold_down_timer:
                description:
                - Hold down timer value in seconds (0-3600).
                type: int
                default: 0
  gather_filter:
    description:
    - Filter for gathered information.
    type: dict
    suboptions:
      peer_ids:
        description:
        - List of peer IDs to gather information for.
        type: list
        elements: str
      include_ports:
        description:
        - Include port information in gathered data.
        type: bool
        default: true
      include_rsmlt:
        description:
        - Include RSMLT information in gathered data.
        type: bool
        default: true
      include_state:
        description:
        - Include state information in gathered data.
        type: bool
        default: false
"""

EXAMPLES = r"""
- name: Configure MLAG peers and ports
  hosts: switches
  gather_facts: false
  tasks:
    - name: Configure MLAG peer with ports
      extreme_fe_mlag:
        state: present
        config:
          peers:
            - peer_id: "1"
              peer_ip_address: "192.168.5.104"
              local_ip_address: "192.168.5.101"
              local_vlan_id: 100
              hello_interval: 1000
              hello_timeout: 5000
              ports:
                - port_id: "10"
                  mlag_id: 10
                - port_id: "11"
                  mlag_id: 11

- name: Configure RSMLT instances
  extreme_fe_mlag:
    state: present
    config:
      rsmlt:
        instances:
          - vlan_id: 100
            enabled: true
            hold_up_timer: 60
            hold_down_timer: 30
          - vlan_id: 200
            enabled: true

- name: Gather all MLAG configuration
  extreme_fe_mlag:
    state: gathered
    gather_filter:
      include_ports: true
      include_rsmlt: true
      include_state: true

- name: Delete specific MLAG peer
  extreme_fe_mlag:
    state: absent
    config:
      peers:
        - peer_id: "1"

- name: Delete all MLAG configuration
  extreme_fe_mlag:
    state: deleted
"""

RETURN = r"""
before:
  description: The configuration prior to the module execution.
  returned: when changed
  type: dict
  sample:
    peers: []
    rsmlt: 
      instances: []
after:
  description: The resulting configuration after module execution.
  returned: when changed
  type: dict
  sample:
    peers:
      - peer_id: "1"
        peer_ip_address: "192.168.5.104"
        local_ip_address: "192.168.5.101"
        ports:
          - port_id: "10"
            mlag_id: 10
    rsmlt:
      instances:
        - vlan_id: 100
          enabled: true
commands:
  description: The set of commands that were executed on the device.
  returned: always
  type: list
  sample:
    - "PATCH /v0/configuration/mlag/peers/Default"
    - "PUT /v0/configuration/mlag/peers/Default/ports"
    - "PATCH /v0/configuration/mlag/rsmlt/vlan/100"
gathered:
  description: Network resource facts for the provided configuration after module execution.
  returned: when state is I(gathered)
  type: dict
  sample:
    peers:
      - peer_id: "1"
        peer_ip_address: "192.168.5.104"
        local_ip_address: "192.168.5.101"
        state: "UP"
        ports:
          - port_id: "10"
            mlag_id: 10
            state: "UP"
    rsmlt:
      instances:
        - vlan_id: 100
          enabled: true
          operational_state: "UP"
"""


class MlagModule:
    """Manage MLAG configuration on Fabric Engine devices."""

    def __init__(self, module: AnsibleModule):
        """Initialize the MLAG module."""
        self.module = module
        self.connection = Connection(module._socket_path)
        self.result = {
            'changed': False,
            'commands': [],
            'before': {},
            'after': {},
        }

    def run(self) -> Dict[str, Any]:
        """Execute the module."""
        state = self.module.params['state']
        
        # Validate input parameters
        self._validate_parameters()
        
        try:
            if state == 'gathered':
                return self._handle_gathered()
            elif state in ['present', 'merged']:
                return self._handle_present()
            elif state == 'replaced':
                return self._handle_replaced()
            elif state in ['absent', 'deleted']:
                return self._handle_absent()
            else:
                self.module.fail_json(msg=f"Unsupported state: {state}")
        except ConnectionError as e:
            self.module.fail_json(msg=f"Connection error: {to_text(e)}")
        except Exception as e:
            import traceback
            self.module.fail_json(msg=f"Unexpected error: {to_text(e)}\nTraceback: {traceback.format_exc()}")

    def _handle_gathered(self) -> Dict[str, Any]:
        """Handle gathered state."""
        gathered_data = self._gather_facts()
        self.result['gathered'] = gathered_data
        return self.result

    def _handle_present(self) -> Dict[str, Any]:
        """Handle present/merged state."""
        current_config = self._gather_facts()
        self.result['before'] = current_config
        
        desired_config = self.module.params.get('config', {})
        if not desired_config:
            self.result['after'] = current_config
            return self.result

        # Configure peers
        if 'peers' in desired_config and desired_config['peers']:
            for peer_config in desired_config['peers']:
                self._configure_peer(peer_config)

        # Configure RSMLT
        if 'rsmlt' in desired_config and desired_config['rsmlt'] and 'instances' in desired_config['rsmlt']:
            for rsmlt_config in desired_config['rsmlt']['instances']:
                self._configure_rsmlt_instance(rsmlt_config)

        if self.result['commands']:
            self.result['changed'] = True
            self.result['after'] = self._gather_facts()
        else:
            self.result['after'] = current_config

        return self.result

    def _handle_replaced(self) -> Dict[str, Any]:
        """Handle replaced state."""
        current_config = self._gather_facts()
        self.result['before'] = current_config
        
        desired_config = self.module.params.get('config', {})
        
        # First delete existing configuration
        self._delete_all_configuration()
        
        # Then apply new configuration
        if desired_config:
            if 'peers' in desired_config:
                for peer_config in desired_config['peers']:
                    self._configure_peer(peer_config)
            
            if 'rsmlt' in desired_config and 'instances' in desired_config['rsmlt']:
                for rsmlt_config in desired_config['rsmlt']['instances']:
                    self._configure_rsmlt_instance(rsmlt_config)

        self.result['changed'] = True
        self.result['after'] = self._gather_facts()
        return self.result

    def _handle_absent(self) -> Dict[str, Any]:
        """Handle absent/deleted state."""
        current_config = self._gather_facts()
        self.result['before'] = current_config
        
        desired_config = self.module.params.get('config', {})
        
        if self.module.params['state'] == 'deleted' or not desired_config:
            # Delete all MLAG configuration
            self._delete_all_configuration()
        else:
            # Delete specific configuration
            if 'peers' in desired_config:
                for peer_config in desired_config['peers']:
                    self._delete_peer(peer_config['peer_id'])

        if self.result['commands']:
            self.result['changed'] = True
            self.result['after'] = self._gather_facts()
        else:
            self.result['after'] = current_config

        return self.result

    def _validate_parameters(self) -> None:
        """Validate module parameters."""
        state = self.module.params['state']
        config = self.module.params.get('config')
        
        # Validate state-specific requirements
        if state in ['present', 'merged', 'replaced'] and not config:
            self.module.fail_json(msg="config is required for state: {}".format(state))
        
        if config:
            # Validate peers configuration if present
            peers = config.get('peers', [])
            for peer in peers:
                # Validate IP addresses if present
                peer_ip = peer.get('peer_ip_address')
                if peer_ip:
                    if not self._is_valid_ip(peer_ip):
                        self.module.fail_json(msg="peer_ip_address is not a valid IP address: {}".format(peer_ip))
                
                local_ip = peer.get('local_ip_address')
                if local_ip:
                    if not self._is_valid_ip(local_ip):
                        self.module.fail_json(msg="local_ip_address is not a valid IP address: {}".format(local_ip))
                
                # Validate timer values if present
                hello_interval = peer.get('hello_interval')
                if hello_interval is not None:
                    if not isinstance(hello_interval, int) or hello_interval < 100 or hello_interval > 30000:
                        self.module.fail_json(msg="hello_interval must be an integer between 100 and 30000 milliseconds")
                
                hello_timeout = peer.get('hello_timeout')
                if hello_timeout is not None:
                    if not isinstance(hello_timeout, int) or hello_timeout < 1000 or hello_timeout > 60000:
                        self.module.fail_json(msg="hello_timeout must be an integer between 1000 and 60000 milliseconds")
            
            # Validate RSMLT configuration if present
            rsmlt = config.get('rsmlt')
            if rsmlt and 'instances' in rsmlt:
                for instance in rsmlt['instances']:
                    vlan_id = instance.get('vlan_id')
                    if vlan_id is not None:
                        if not isinstance(vlan_id, int) or vlan_id < 1 or vlan_id > 4094:
                            self.module.fail_json(msg="vlan_id must be an integer between 1 and 4094")
                    
                    hold_up_timer = instance.get('hold_up_timer')
                    if hold_up_timer is not None:
                        if not isinstance(hold_up_timer, int) or (hold_up_timer < 0 or hold_up_timer > 3600) and hold_up_timer != 9999:
                            self.module.fail_json(msg="hold_up_timer must be an integer between 0 and 3600, or 9999 for infinity")
                    
                    hold_down_timer = instance.get('hold_down_timer')
                    if hold_down_timer is not None:
                        if not isinstance(hold_down_timer, int) or hold_down_timer < 0 or hold_down_timer > 3600:
                            self.module.fail_json(msg="hold_down_timer must be an integer between 0 and 3600")

    def _is_valid_ip(self, ip_str: str) -> bool:
        """Validate if string is a valid IP address."""
        import socket
        try:
            socket.inet_aton(ip_str)
            return True
        except socket.error:
            return False

    def _gather_facts(self) -> Dict[str, Any]:
        """Gather MLAG facts from the device."""
        facts = {
            'peers': [],
            'rsmlt': {'instances': []}
        }
        
        gather_filter = self.module.params.get('gather_filter') or {}
        include_ports = gather_filter.get('include_ports', True)
        include_rsmlt = gather_filter.get('include_rsmlt', True)
        include_state = gather_filter.get('include_state', False)
        peer_ids_filter = gather_filter.get('peer_ids', [])

        try:
            # Gather peer configuration
            peers_response = self._send_request('GET', '/v0/configuration/mlag/peers')
            if peers_response:
                for peer in peers_response:
                    peer_id = peer.get('peerId')
                    if peer_ids_filter and peer_id not in peer_ids_filter:
                        continue
                    
                    # Extract IP address from nested object structure
                    peer_ip_obj = peer.get('peerIpAddress', {})
                    peer_ip_address = peer_ip_obj.get('address') if peer_ip_obj else None
                    
                    peer_data = {
                        'peer_id': peer_id,
                        'peer_ip_address': peer_ip_address,
                        'local_ip_address': peer.get('localIpAddress'),  # May not exist in response
                        'local_vlan_id': peer.get('vistVlanId'),  # Use actual field name
                        'authentication_key': peer.get('authenticationKey'),
                        'hello_interval': peer.get('helloInterval'),
                        'hello_timeout': peer.get('helloTimeout')
                    }
                    
                    # Gather port information if requested
                    if include_ports:
                        try:
                            ports_response = self._send_request('GET', f'/v0/configuration/mlag/peers/{peer_id}/ports')
                            if ports_response:
                                peer_data['ports'] = [
                                    {
                                        'port_id': port.get('portId'),
                                        'mlag_id': port.get('mlagId')
                                    }
                                    for port in ports_response
                                ]
                            else:
                                peer_data['ports'] = []
                        except Exception:
                            peer_data['ports'] = []
                    
                    # Gather state information if requested
                    if include_state:
                        try:
                            state_response = self._send_request('GET', '/v0/state/mlag/peers')
                            if state_response:
                                for state_peer in state_response:
                                    if state_peer.get('peerId') == peer_id:
                                        peer_data['state'] = {
                                            'checkpointing_state': state_peer.get('checkpointingState'),
                                            'hello_state': state_peer.get('helloState'),
                                            'counters': state_peer.get('counters', {})
                                        }
                                        break
                        except Exception:
                            pass
                    
                    facts['peers'].append(peer_data)

            # Gather RSMLT configuration if requested
            if include_rsmlt:
                try:
                    rsmlt_response = self._send_request('GET', '/v0/configuration/mlag/rsmlt')
                    if rsmlt_response:
                        rsmlt_list = rsmlt_response if isinstance(rsmlt_response, list) else [rsmlt_response]
                    else:
                        rsmlt_list = []
                            
                    for vlan_config in rsmlt_list:
                                vlan_id = vlan_config.get('vlanId')
                                rsmlt_instances = vlan_config.get('rsmltInstances', [])
                                for instance in rsmlt_instances:
                                    instance_data = {
                                        'vlan_id': vlan_id,
                                        'enabled': instance.get('enabled'),
                                        'hold_up_timer': instance.get('holdUpTimer'),
                                        'hold_down_timer': instance.get('holdDownTimer')
                                    }
                                    
                                    # Add state information if requested
                                    if include_state:
                                        try:
                                            state_response = self._send_request('GET', '/v0/state/mlag/rsmlt')
                                            if state_response:
                                                for state_vlan in state_response:
                                                    if state_vlan.get('vlanId') == vlan_id:
                                                        state_instances = state_vlan.get('rsmltInstances', [])
                                                        for state_instance in state_instances:
                                                            instance_data['operational_state'] = state_instance.get('operationalState')
                                                            break
                                                        break
                                        except Exception:
                                            pass
                                    
                                    facts['rsmlt']['instances'].append(instance_data)
                except Exception:
                    pass

        except Exception as e:
            self.module.fail_json(msg=f"Failed to gather MLAG facts: {to_text(e)}")

        return facts

    def _configure_peer(self, peer_config: Dict[str, Any]) -> None:
        """Configure MLAG peer."""
        # MLAG API uses a single "Default" peer that we configure via PATCH
        peer_id = "Default"
        
        # Prepare peer configuration data
        peer_data = {}
        
        # Map configuration to API structure
        if 'peer_ip_address' in peer_config:
            peer_data['peerIpAddress'] = {
                'address': peer_config['peer_ip_address'],
                'ipAddressType': 'IPv4'
            }
        if 'local_vlan_id' in peer_config:
            peer_data['vistVlanId'] = peer_config['local_vlan_id']
        if 'authentication_key' in peer_config:
            peer_data['authenticationKey'] = peer_config['authentication_key']
        if 'hello_interval' in peer_config:
            peer_data['helloInterval'] = peer_config['hello_interval']
        if 'hello_timeout' in peer_config:
            peer_data['helloTimeout'] = peer_config['hello_timeout']

        # Always update the existing "Default" peer with PATCH
        response = self._send_request('PATCH', f'/v0/configuration/mlag/peers/{peer_id}', peer_data)
        self.result['commands'].append(f"PATCH /v0/configuration/mlag/peers/{peer_id}")

        # Configure ports if specified
        if 'ports' in peer_config and peer_config['ports']:
            self._configure_peer_ports(peer_id, peer_config['ports'])

    def _configure_peer_ports(self, peer_id: str, ports_config: List[Dict[str, Any]]) -> None:
        """Configure MLAG ports for a peer."""
        ports_data = []
        for port_config in ports_config:
            port_data = {
                'portId': port_config['port_id']
            }
            if 'mlag_id' in port_config:
                port_data['mlagId'] = port_config['mlag_id']
            ports_data.append(port_data)

        response = self._send_request('PUT', f'/v0/configuration/mlag/peers/{peer_id}/ports', ports_data)
        self.result['commands'].append(f"PUT /v0/configuration/mlag/peers/{peer_id}/ports")

    def _configure_rsmlt_instance(self, rsmlt_config: Dict[str, Any]) -> None:
        """Configure RSMLT instance."""
        vlan_id = rsmlt_config['vlan_id']
        
        instance_data = {
            'enabled': rsmlt_config.get('enabled', True),
            'holdUpTimer': rsmlt_config.get('hold_up_timer', 0),
            'holdDownTimer': rsmlt_config.get('hold_down_timer', 0)
        }

        response = self._send_request('PATCH', f'/v0/configuration/mlag/rsmlt/vlan/{vlan_id}', instance_data)
        self.result['commands'].append(f"PATCH /v0/configuration/mlag/rsmlt/vlan/{vlan_id}")

    def _delete_peer(self, peer_id: str) -> None:
        """Delete MLAG peer."""
        response = self._send_request('DELETE', f'/v0/configuration/mlag/peers/{peer_id}')
        self.result['commands'].append(f"DELETE /v0/configuration/mlag/peers/{peer_id}")

    def _delete_all_configuration(self) -> None:
        """Delete all MLAG configuration."""
        # Get current peers and delete them
        try:
            current_peers = self._send_request('GET', '/v0/configuration/mlag/peers')
            if current_peers:
                for peer in current_peers:
                    peer_id = peer.get('peerId')
                    if peer_id:
                        self._delete_peer(peer_id)
        except Exception:
            pass

    def _send_request(self, method: str, path: str, data: Optional[Dict[str, Any]] = None) -> Any:
        """Send HTTP request to the device."""
        try:
            response = self.connection.send_request(data, path=path, method=method)
            return response
        except ConnectionError as e:
            error_msg = to_text(e)
            # Check for specific API errors and provide meaningful messages
            if "Method not found" in error_msg:
                self.module.fail_json(msg=f"MLAG API endpoint {path} not supported on this device")
            elif "404" in error_msg:
                if method == 'GET':
                    return None  # Resource not found is acceptable for GET requests
                else:
                    self.module.fail_json(msg=f"Resource not found: {path}")
            elif "400" in error_msg:
                self.module.fail_json(msg=f"Bad request to {path}: {error_msg}")
            elif "401" in error_msg:
                self.module.fail_json(msg=f"Authentication failed for {path}")
            elif "403" in error_msg:
                self.module.fail_json(msg=f"Access forbidden for {path}")
            elif "500" in error_msg:
                self.module.fail_json(msg=f"Internal server error for {path}: {error_msg}")
            else:
                self.module.fail_json(msg=f"HTTP request failed for {path}: {error_msg}")




def main():
    """Main function."""
    argument_spec = {
        'state': {
            'type': 'str',
            'choices': ['present', 'absent', 'gathered', 'merged', 'replaced', 'deleted'],
            'default': 'present'
        },
        'config': {
            'type': 'dict',
            'options': {
                'peers': {
                    'type': 'list',
                    'elements': 'dict',
                    'options': {
                        'peer_id': {'type': 'str', 'required': True},
                        'peer_ip_address': {'type': 'str'},
                        'local_ip_address': {'type': 'str'},
                        'local_vlan_id': {'type': 'int'},
                        'authentication_key': {'type': 'str'},
                        'hello_interval': {'type': 'int'},
                        'hello_timeout': {'type': 'int'},
                        'ports': {
                            'type': 'list',
                            'elements': 'dict',
                            'options': {
                                'port_id': {'type': 'str', 'required': True},
                                'mlag_id': {'type': 'int'}
                            }
                        }
                    }
                },
                'rsmlt': {
                    'type': 'dict',
                    'options': {
                        'instances': {
                            'type': 'list',
                            'elements': 'dict',
                            'options': {
                                'vlan_id': {'type': 'int', 'required': True},
                                'enabled': {'type': 'bool', 'default': True},
                                'hold_up_timer': {'type': 'int', 'default': 0},
                                'hold_down_timer': {'type': 'int', 'default': 0}
                            }
                        }
                    }
                }
            }
        },
        'gather_filter': {
            'type': 'dict',
            'options': {
                'peer_ids': {'type': 'list', 'elements': 'str'},
                'include_ports': {'type': 'bool', 'default': True},
                'include_rsmlt': {'type': 'bool', 'default': True},
                'include_state': {'type': 'bool', 'default': False}
            }
        }
    }

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_if=[
            ('state', 'present', ['config']),
            ('state', 'merged', ['config']),
            ('state', 'replaced', ['config']),
        ]
    )

    if module.check_mode:
        module.exit_json(**{'changed': False, 'commands': []})

    mlag_module = MlagModule(module)
    result = mlag_module.run()
    
    module.exit_json(**result)


if __name__ == '__main__':
    main()