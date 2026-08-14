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
version_added: "1.0.0"
description:
- Manage Multi-switch Link Aggregation (MLAG) configuration on ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe) HTTPAPI transport.
- Configure MLAG peers, ports, and RSMLT (Routed Split Multi-Link Trunking) instances.
- Supports both configuration and state retrieval operations for comprehensive MLAG management.
- Handles error propagation from device REST API endpoints back to Ansible.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
- Fabric Engine (VOSS) specific functionality; Switch Engine (EXOS) features are limited.
- RSMLT operations are Fabric Engine specific.
requirements:
- ansible.netcommon
options:
  state:
    description:
    - Desired MLAG operation.
    type: str
    choices: [present, absent, gathered, merged, replaced, overridden, deleted]
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
            - On VOSS, this is derived from the IST VLAN IP configuration.
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
  description:
    - The MLAG configuration on the device before the task ran.
    - Captured for every state except C(gathered).
  returned: when state is not gathered
  type: dict
  sample:
    peers: []
    rsmlt: 
      instances: []
after:
  description:
    - The MLAG configuration on the device after the task ran.
    - Re-read from the device, so it reflects what the device actually applied
      rather than what was requested. Not returned when nothing changed or in
      check mode, since it would repeat C(before).
  returned: when the task changed the device and not in check mode
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
        self._validate_parameters()

        try:
            current = self._gather_facts()
            self.result['before'] = current

            if state == 'gathered':
                self.result['gathered'] = current
                # gathered reads nothing and writes nothing, so a snapshot pair
                # would just repeat the facts already under 'gathered'.
                self.result.pop('before', None)
                self.result.pop('after', None)
                return self.result

            if state in ('present', 'merged'):
                self._write(current, ports_authoritative=False, rsmlt_authoritative=False)
            elif state == 'replaced':
                self._write(current, ports_authoritative=True, rsmlt_authoritative=False)
            elif state == 'overridden':
                self._write(current, ports_authoritative=True, rsmlt_authoritative=True)
            elif state in ('absent', 'deleted'):
                self._delete(current)
            else:
                self.module.fail_json(msg=f"Unsupported state: {state}")

            # after-snapshot: only re-read when a real change was applied.
            # When nothing changed, or in check mode, 'after' would just repeat
            # 'before', so it is omitted instead -- same convention as
            # extreme_fe_interfaces and extreme_fe_autosense.
            if self.result['changed'] and not self.module.check_mode:
                self.result['after'] = self._gather_facts()
            else:
                self.result.pop('after', None)
            return self.result
        except ConnectionError as e:
            self.module.fail_json(msg=f"Connection error: {to_text(e)}")
        except Exception as e:
            import traceback
            self.module.fail_json(msg=f"Unexpected error: {to_text(e)}\nTraceback: {traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Change application (central point for idempotency + check_mode)
    # ------------------------------------------------------------------
    def _apply(self, method: str, path: str, data: Any, desc: str, graceful: bool = False) -> Any:
        """Record and send a mutating request.

        Only called when a real difference exists. changed and the command
        entry are recorded only after a successful apply (or in check_mode),
        so a graceful failure (e.g. an unsupported peer-IP reset) does not
        falsely report changed and stays idempotent on re-runs.
        """
        if self.module.check_mode:
            self.result['changed'] = True
            self.result['commands'].append(desc)
            return None
        try:
            response = self._send_request(method, path, data)
        except ConnectionError as exc:
            if graceful:
                self.result.setdefault('warnings', []).append(f"{desc}: {to_text(exc)}")
                return None
            raise
        self.result['changed'] = True
        self.result['commands'].append(desc)
        return response

    # ------------------------------------------------------------------
    # Current-state extraction helpers (VOSS exposes a single "Default" peer)
    # ------------------------------------------------------------------
    @staticmethod
    def _norm_ip(value: Optional[str]) -> str:
        return (value or '').strip() or '0.0.0.0'

    @staticmethod
    def _port_sort_key(pid: str):
        return (0, int(pid)) if str(pid).isdigit() else (1, str(pid))

    def _current_peer(self, current: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        peers = current.get('peers') or []
        return peers[0] if peers else None

    def _current_ports_set(self, current: Dict[str, Any]) -> set:
        peer = self._current_peer(current)
        if not peer:
            return set()
        return {str(p['port_id']) for p in (peer.get('ports') or []) if p.get('port_id') is not None}

    def _current_rsmlt_map(self, current: Dict[str, Any]) -> Dict[Any, Dict[str, Any]]:
        result: Dict[Any, Dict[str, Any]] = {}
        for inst in (current.get('rsmlt') or {}).get('instances', []):
            vid = inst.get('vlan_id')
            if vid is not None:
                result[vid] = inst
        return result

    # ------------------------------------------------------------------
    # Write states: merged / replaced / overridden
    # ------------------------------------------------------------------
    def _write(self, current: Dict[str, Any], ports_authoritative: bool, rsmlt_authoritative: bool) -> None:
        config = self.module.params.get('config') or {}
        for peer_cfg in (config.get('peers') or []):
            self._apply_peer(peer_cfg, current)
            if peer_cfg.get('ports') is not None:
                self._apply_ports(peer_cfg, current, ports_authoritative)
        rsmlt = config.get('rsmlt') or {}
        instances = rsmlt.get('instances') or []
        if instances or rsmlt_authoritative:
            self._apply_rsmlt(instances, current, rsmlt_authoritative)

    def _apply_peer(self, peer_cfg: Dict[str, Any], current: Dict[str, Any]) -> None:
        """PATCH the peer scalar fields when they differ (idempotent).

        VOSS requires peerIpAddress and vistVlanId to be set together, so both
        are always sent when either changes; omitted fields fall back to the
        current value.
        """
        cur = self._current_peer(current) or {}
        cur_ip = self._norm_ip(cur.get('peer_ip_address'))
        cur_vlan = cur.get('local_vlan_id')
        desired_ip = peer_cfg.get('peer_ip_address')
        desired_vlan = peer_cfg.get('local_vlan_id')
        target_ip = self._norm_ip(desired_ip) if desired_ip is not None else cur_ip
        target_vlan = desired_vlan if desired_vlan is not None else cur_vlan

        if target_ip == cur_ip and target_vlan == cur_vlan:
            return  # already in desired state

        payload: Dict[str, Any] = {}
        if target_ip and target_ip != '0.0.0.0':
            payload['peerIpAddress'] = {'address': target_ip, 'ipAddressType': 'IPv4'}
        if target_vlan is not None:
            payload['vistVlanId'] = target_vlan
        if payload:
            self._apply('PATCH', '/v0/configuration/mlag/peers/Default', payload, "PATCH peer Default")

    def _apply_ports(self, peer_cfg: Dict[str, Any], current: Dict[str, Any], authoritative: bool) -> None:
        """Set MLAG ports. merged = additive (union); replaced/overridden = exact."""
        requested = {str(p['port_id']) for p in (peer_cfg.get('ports') or []) if p.get('port_id') is not None}
        cur_ports = self._current_ports_set(current)
        target = requested if authoritative else (cur_ports | requested)
        if target != cur_ports:
            ports_data = [{'portId': pid} for pid in sorted(target, key=self._port_sort_key)]
            self._apply('PUT', '/v0/configuration/mlag/peers/Default/ports', ports_data,
                        "PUT peer Default ports")

    def _apply_rsmlt(self, instances: List[Dict[str, Any]], current: Dict[str, Any], authoritative: bool) -> None:
        cur_map = self._current_rsmlt_map(current)
        desired_vids = set()
        for inst in instances:
            vid = inst.get('vlan_id')
            desired_vids.add(vid)
            desired = {
                'enabled': inst.get('enabled', True),
                'holdUpTimer': inst.get('hold_up_timer', 0),
                'holdDownTimer': inst.get('hold_down_timer', 0),
            }
            cur = cur_map.get(vid)
            if not cur or not self._rsmlt_matches(cur, desired):
                self._apply('PATCH', f'/v0/configuration/mlag/rsmlt/vlan/{vid}', desired,
                            f"PATCH rsmlt vlan {vid}")
        if authoritative:
            for vid, cur in cur_map.items():
                if vid in desired_vids:
                    continue
                if cur.get('enabled') or cur.get('hold_up_timer') or cur.get('hold_down_timer'):
                    self._apply('PATCH', f'/v0/configuration/mlag/rsmlt/vlan/{vid}',
                                {'enabled': False, 'holdUpTimer': 0, 'holdDownTimer': 0},
                                f"PATCH rsmlt vlan {vid} (reset)")

    @staticmethod
    def _rsmlt_matches(cur: Dict[str, Any], desired: Dict[str, Any]) -> bool:
        return (cur.get('enabled') == desired['enabled']
                and cur.get('hold_up_timer') == desired['holdUpTimer']
                and cur.get('hold_down_timer') == desired['holdDownTimer'])

    # ------------------------------------------------------------------
    # Delete state: remove only what is specified (or all when no config)
    # ------------------------------------------------------------------
    def _delete(self, current: Dict[str, Any]) -> None:
        config = self.module.params.get('config') or {}
        peers = config.get('peers') or []
        instances = (config.get('rsmlt') or {}).get('instances') or []

        if not peers and not instances:
            self._delete_all(current)
            return

        for peer_cfg in peers:
            ports = peer_cfg.get('ports')
            if ports is not None:
                # remove only the listed ports
                remove = {str(p['port_id']) for p in ports if p.get('port_id') is not None}
                cur_ports = self._current_ports_set(current)
                target = cur_ports - remove
                if target != cur_ports:
                    ports_data = [{'portId': pid} for pid in sorted(target, key=self._port_sort_key)]
                    self._apply('PUT', '/v0/configuration/mlag/peers/Default/ports', ports_data,
                                "PUT peer Default ports (remove)")
            else:
                # delete the whole peer: clear ports + reset scalars
                self._clear_peer(current)

        for inst in instances:
            self._reset_rsmlt(inst.get('vlan_id'), current)

    def _delete_all(self, current: Dict[str, Any]) -> None:
        self._clear_peer(current)
        for vid in self._current_rsmlt_map(current):
            self._reset_rsmlt(vid, current)

    def _clear_peer(self, current: Dict[str, Any]) -> None:
        if self._current_ports_set(current):
            self._apply('PUT', '/v0/configuration/mlag/peers/Default/ports', [],
                        "PUT peer Default ports (clear)")
        peer = self._current_peer(current)
        if peer and self._norm_ip(peer.get('peer_ip_address')) != '0.0.0.0':
            # Peer IP reset is not always permitted on VOSS; do it gracefully.
            self._apply('PATCH', '/v0/configuration/mlag/peers/Default',
                        {'peerIpAddress': {'address': '0.0.0.0', 'ipAddressType': 'IPv4'}},
                        "PATCH peer Default (reset ip)", graceful=True)

    def _reset_rsmlt(self, vid: Any, current: Dict[str, Any]) -> None:
        if vid is None:
            return
        cur = self._current_rsmlt_map(current).get(vid)
        if cur and (cur.get('enabled') or cur.get('hold_up_timer') or cur.get('hold_down_timer')):
            self._apply('PATCH', f'/v0/configuration/mlag/rsmlt/vlan/{vid}',
                        {'enabled': False, 'holdUpTimer': 0, 'holdDownTimer': 0},
                        f"PATCH rsmlt vlan {vid} (reset)")

    def _validate_parameters(self) -> None:
        """Validate module parameters."""
        state = self.module.params['state']
        config = self.module.params.get('config')
        
        # Validate state-specific requirements
        if state in ['present', 'merged', 'replaced', 'overridden'] and not config:
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

            # Fetch state payload once outside the loop and index by peerId
            # This avoids N+1 API calls when iterating peers
            peers_state_map: Dict[Any, Dict[str, Any]] = {}
            try:
                state_response = self._send_request('GET', '/v0/state/mlag/peers')
                if state_response:
                    for state_peer in state_response:
                        state_peer_id = state_peer.get('peerId')
                        if state_peer_id is not None:
                            peers_state_map[state_peer_id] = state_peer
            except Exception:
                # Treat connection errors as "no state available"
                pass

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
                            # Treat errors as empty ports list
                            peer_data['ports'] = []

                    # Use pre-fetched state to get local_ip_address (config endpoint doesn't return it on VOSS)
                    # Add full state object only when include_state is true
                    state_peer = peers_state_map.get(peer_id)
                    if state_peer:
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

                    facts['peers'].append(peer_data)

            # Gather RSMLT configuration if requested
            if include_rsmlt:
                try:
                    rsmlt_response = self._send_request('GET', '/v0/configuration/mlag/rsmlt')
                    if rsmlt_response:
                        rsmlt_list = rsmlt_response if isinstance(rsmlt_response, list) else [rsmlt_response]
                    else:
                        rsmlt_list = []

                    # Fetch RSMLT state once outside the loop and index by vlanId
                    # This avoids N+1 API calls when iterating VLAN configs
                    rsmlt_state_map: Dict[Any, Dict[str, Any]] = {}
                    if include_state:
                        try:
                            rsmlt_state_response = self._send_request('GET', '/v0/state/mlag/rsmlt')
                            if rsmlt_state_response:
                                for state_vlan in rsmlt_state_response:
                                    state_vlan_id = state_vlan.get('vlanId')
                                    if state_vlan_id is not None:
                                        rsmlt_state_map[state_vlan_id] = state_vlan
                        except Exception:
                            # Treat errors as "no RSMLT state available"
                            pass

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

                            # Add state information if requested (use pre-fetched state)
                            if include_state:
                                state_vlan = rsmlt_state_map.get(vlan_id)
                                if state_vlan:
                                    state_instances = state_vlan.get('rsmltInstances', [])
                                    for state_instance in state_instances:
                                        instance_data['operational_state'] = state_instance.get('operationalState')
                                        break

                            facts['rsmlt']['instances'].append(instance_data)
                except Exception:
                    # Treat errors as empty RSMLT config
                    pass

        except Exception as e:
            self.module.fail_json(msg=f"Failed to gather MLAG facts: {to_text(e)}")

        return facts

    def _send_request(self, method: str, path: str, data: Optional[Any] = None) -> Any:
        """Send an HTTP request. Returns None for 404 on GET; raises otherwise."""
        try:
            return self.connection.send_request(data, path=path, method=method)
        except ConnectionError as e:
            error_msg = to_text(e)
            if method == 'GET' and ("404" in error_msg or "Method not found" in error_msg):
                return None  # absent resource is acceptable for reads
            raise ConnectionError(f"{method} {path}: {error_msg}")


def main():
    """Main function."""
    argument_spec = {
        'state': {
            'type': 'str',
            'choices': ['present', 'absent', 'gathered', 'merged', 'replaced', 'overridden', 'deleted'],
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
            ('state', 'overridden', ['config']),
        ]
    )

    mlag_module = MlagModule(module)
    result = mlag_module.run()

    module.exit_json(**result)


if __name__ == '__main__':
    main()