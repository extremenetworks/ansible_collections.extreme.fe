# -*- coding: utf-8 -*-
# Copyright (c) 2025 Extreme Networks
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from typing import Dict

# Canonical names for system VRFs — the VOSS REST API requires these
# exact forms in URL paths (case-sensitive).  User VRF names are stored
# lowercase by VOSS, but system VRFs keep their canonical casing.
SYSTEM_VRF_CANONICAL: Dict[str, str] = {
    "globalrouter": "GlobalRouter",
    "mgmtrouter": "MgmtRouter",
}


def normalize_vrf_name(name: str) -> str:
    """Normalize a VRF name for API path construction.

    User-created VRFs are lowercased (VOSS stores them in lowercase).
    System VRFs (GlobalRouter, MgmtRouter) are mapped to their canonical
    casing because the REST API requires the exact identifier.
    """
    lower = name.lower()
    return SYSTEM_VRF_CANONICAL.get(lower, lower)
