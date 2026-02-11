# -*- coding: utf-8 -*-
"""Ansible module to manage ExtremeNetworks Fabric Engine MLAG via HTTPAPI."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils._text import to_text

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
            - Note: On VOSS, this is derived from the IST VLAN IP configuration.
            type: str
          local_vlan_id:
            description:
            - Local VLAN ID for MLAG/IST communication.
            type: int
          ports:
            description:
            - List of MLAG ports (MLT IDs) for this peer.
            type: list
            elements: dict
            suboptions:
              port_id:
                description:
                - Port identifier (MLT ID on VOSS).
                type: str
                required: true
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
# Task-level examples for ansible-doc:

# =========================================================================
# Full playbook examples with prerequisites:
# To create a complete playbook, uncomment the lines starting with:
#   '# - name:', '# hosts:', '# gather_facts:', and '# tasks:'
# After uncommenting, realign indentation to conform to YAML format
# (playbook level at col 0, tasks indented under 'tasks:')
# =========================================================================
#
# Prerequisites:
#
# !! IMPORTANT: IS-IS / SPBM Limitations !!
# # When IS-IS (SPBM) is enabled, runtime MLAG changes are often restricted.
# # MLAG peer configuration should be done BEFORE enabling IS-IS.
# # To check:
# show isis
# show isis spbm
# # To disable:
# no router isis enable
#
# ## Create VLANs:
# ## - VLAN 100: IST (Inter-Switch Trunk) VLAN for MLAG peer communication
# ## - VLANs 200, 300: For RSMLT (cannot use IST VLAN for RSMLT)
# # vlan create 100 name "IST-VLAN" type port-mstprstp 0
# # vlan i-sid 100 10010
# # vlan create 200 name "RSMLT-VLAN-200" type port-mstprstp 0
# # vlan i-sid 200 20020
# # vlan create 300 name "RSMLT-VLAN-300" type port-mstprstp 0
# # vlan i-sid 300 30030
#
# ## Create MLTs for MLAG ports
# # mlt 10
# # mlt 11
#
# ## Configure IST VLAN with IP address (for MLAG peer communication)
# # interface vlan 100
# #   ip address 192.168.5.101/24
# # exit
#
# ## Enable RSMLT on non-IST VLANs (must have IP addresses)
# ## NOTE: RSMLT cannot be on an IST VLAN
# # interface vlan 200
# #   ip address 10.20.0.1/24
# #   ip rsmlt
# # exit
# # interface vlan 300
# #   ip address 10.30.0.1/24
# #   ip rsmlt
# # exit
#
# ## Verify Configuration
# # show vlan i-sid
# # show mlt
# # show smlt mlt
# # show ip rsmlt

# -------------------------------------------------------------------------
# Task 1: Configure MLAG peer relationship with ports
# Description:
#   - Configure an MLAG peer relationship with ISC ports
#   - MLAG enables link aggregation across two physical switches
# Prerequisites:
#   - VLAN 100 must exist with i-sid for ISC
#   - VLAN 100 must have an IP address for peer communication
#   - IP connectivity between peer switches
# Note: VOSS uses "Default" as the only valid peer_id
# -------------------------------------------------------------------------
# - name: "Task 1: Configure MLAG peers and ports"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Configure MLAG peer with ports
  extreme.fe.extreme_fe_mlag:
    state: present
    config:
      peers:
        - peer_id: "Default"
          peer_ip_address: "192.168.5.104"
          local_vlan_id: 100
          ports:
            - port_id: "10"
            - port_id: "11"

# -------------------------------------------------------------------------
# Task 2: Configure RSMLT (Routed Split Multi-Link Trunking)
# Description:
#   - Configure RSMLT instances on VLANs for Layer 3 gateway redundancy
#   - Both switches can act as active gateways
# Prerequisites:
#   - VLANs 200, 300 must exist with i-sid and IP addresses
#   - RSMLT must be enabled on VLANs (ip rsmlt)
#   - MLAG peer relationship must be configured
#   - NOTE: RSMLT cannot be on IST VLAN (100)
# -------------------------------------------------------------------------
# - name: "Task 2: Configure RSMLT instances"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Set up RSMLT on VLANs
  extreme.fe.extreme_fe_mlag:
    state: present
    config:
      rsmlt:
        instances:
          - vlan_id: 200
            enabled: true
            hold_up_timer: 60
            hold_down_timer: 30
          - vlan_id: 300
            enabled: true

# -------------------------------------------------------------------------
# Task 3: Gather MLAG configuration
# Description:
#   - Retrieve current MLAG configuration including peers, ports,
#     RSMLT instances, and operational state
# -------------------------------------------------------------------------
# - name: "Task 3: Gather all MLAG configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect MLAG configuration
  extreme.fe.extreme_fe_mlag:
    state: gathered
    gather_filter:
      include_ports: true
      include_rsmlt: true
      include_state: true
  register: mlag_gathered

# -------------------------------------------------------------------------
# Task 4: Delete MLAG peer
# Description:
#   - Remove MLAG peer relationship (clears ports)
# !! WARNING !!
#   MLAG peer deletion via REST API may not be fully supported on VOSS.
#   Module will clear ports and provide warning with CLI alternative.
#   To complete deletion via CLI: "no virtual-ist peer-ip <ip_address>"
# -------------------------------------------------------------------------
# - name: "Task 4: Delete specific MLAG peer"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Remove MLAG peer (reset to defaults)
  extreme.fe.extreme_fe_mlag:
    state: absent
    config:
      peers:
        - peer_id: "Default"

# -------------------------------------------------------------------------
# Task 5: Delete all MLAG configuration
# Description:
#   - Remove all MLAG configuration including peers and RSMLT instances
# !! WARNING !!
#   This will clear all MLAG-related configuration.
#   Use CLI for complete removal: "no virtual-ist peer-ip <ip_address>"
# -------------------------------------------------------------------------
# - name: "Task 5: Delete all MLAG configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Remove all MLAG configuration
  extreme.fe.extreme_fe_mlag:
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
            peers = desired_config.get('peers') or []
            for peer_config in peers:
                self._configure_peer(peer_config)
            
            rsmlt = desired_config.get('rsmlt')
            if rsmlt:
                instances = rsmlt.get('instances') or []
                for rsmlt_config in instances:
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
            peers = desired_config.get('peers') or []
            for peer_config in peers:
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
            # Use 'or []' to handle both missing keys and explicit None values
            peers = config.get('peers') or []
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
            
            # Validate RSMLT configuration if present
            rsmlt = config.get('rsmlt')
            if rsmlt:
                instances = rsmlt.get('instances') or []
                for instance in instances:
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
                    
                    # Build peer_data - VOSS only returns subset of fields
                    # Note: hello_interval, hello_timeout, authentication_key are EXOS-only
                    peer_data = {
                        'peer_id': peer_id,
                        'peer_ip_address': peer_ip_address,
                        'local_vlan_id': peer.get('vistVlanId'),
                    }
                    
                    # Gather port information if requested
                    if include_ports:
                        try:
                            ports_response = self._send_request('GET', f'/v0/configuration/mlag/peers/{peer_id}/ports')
                            if ports_response:
                                # On VOSS, port_id (MLT ID) is the only identifier - mlag_id is EXOS-only
                                peer_data['ports'] = [
                                    {'port_id': port.get('portId')}
                                    for port in ports_response
                                ]
                            else:
                                peer_data['ports'] = []
                        except Exception:
                            peer_data['ports'] = []
                    
                    # Always fetch state for local_ip_address (config endpoint doesn't return it on VOSS)
                    # Add full state object only when include_state is true
                    try:
                        state_response = self._send_request('GET', '/v0/state/mlag/peers')
                        if state_response:
                            for state_peer in state_response:
                                if state_peer.get('peerId') == peer_id:
                                    # Extract local_ip_address from state (not available in config on VOSS)
                                    state_local_ip_obj = state_peer.get('localIpAddress', {})
                                    peer_data['local_ip_address'] = state_local_ip_obj.get('address') if state_local_ip_obj else None

                                    # Add detailed state info only if requested
                                    if include_state:
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
        
        # Map configuration to API structure (VOSS-only fields)
        if 'peer_ip_address' in peer_config:
            peer_data['peerIpAddress'] = {
                'address': peer_config['peer_ip_address'],
                'ipAddressType': 'IPv4'
            }
        if 'local_vlan_id' in peer_config:
            peer_data['vistVlanId'] = peer_config['local_vlan_id']

        # Always update the existing "Default" peer with PATCH
        response = self._send_request('PATCH', f'/v0/configuration/mlag/peers/{peer_id}', peer_data)
        self.result['commands'].append(f"PATCH /v0/configuration/mlag/peers/{peer_id}")

        # Configure ports if specified
        if 'ports' in peer_config and peer_config['ports']:
            self._configure_peer_ports(peer_id, peer_config['ports'])

    def _configure_peer_ports(self, peer_id: str, ports_config: List[Dict[str, Any]]) -> None:
        """Configure MLAG ports for a peer (MLT IDs on VOSS)."""
        ports_data = []
        for port_config in ports_config:
            # On VOSS, only portId (MLT ID) is used - mlagId is EXOS-only
            port_data = {
                'portId': port_config['port_id']
            }
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
        """Delete MLAG peer configuration.

        On VOSS, the "Default" peer cannot be truly deleted via REST API.
        Instead, we clear ports and mark as reset. Use CLI for full removal.
        Note: VOSS only supports "Default" as peer_id - any other value is mapped to "Default".
        """
        # On VOSS, always use "Default" peer - any other peer_id is not supported
        api_peer_id = "Default"
        deleted_ports = False

        # First, clear all ports by sending empty list
        try:
            self._send_request('PUT', f'/v0/configuration/mlag/peers/{api_peer_id}/ports', [])
            self.result['commands'].append(f"PUT /v0/configuration/mlag/peers/{api_peer_id}/ports (clear)")
            deleted_ports = True
        except Exception:
            pass  # Ports may not exist or endpoint not available

        # On VOSS, DELETE and PATCH to /mlag/peers/{peer_id} may not be available
        # The DELETE and PATCH endpoints are often not supported on VOSS firmware
        # Just note that we cleared ports and provide CLI alternative
        if deleted_ports:
            self.result['warnings'] = self.result.get('warnings', [])
            self.result['warnings'].append(
                "MLAG ports cleared. To fully remove MLAG config on VOSS, use CLI: 'no virtual-ist peer-ip <ip>'"
            )
        else:
            self.result['warnings'] = self.result.get('warnings', [])
            self.result['warnings'].append(
                "Could not delete MLAG configuration via REST API. On VOSS, use CLI: 'no virtual-ist peer-ip <ip>'"
            )

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
                        'ports': {
                            'type': 'list',
                            'elements': 'dict',
                            'options': {
                                'port_id': {'type': 'str', 'required': True}
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