# extreme_fe_save_config

```yaml

module: extreme_fe_save_config
short_description: Save the running configuration on ExtremeNetworks Fabric Engine switches
version_added: 1.3.0
description:
- Save the current Fabric Engine (VOSS) running configuration to the active or specified
  configuration file via the custom ``extreme_fe`` HTTPAPI plugin.
- Supports optionally providing a filename and using Fabric Engine's verbose save option to
  persist both current and default configuration elements.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped
  with this project.
- Applicable only to Fabric Engine (VOSS) devices.
requirements:
- ansible.netcommon
options:
  name:
    description:
    - Destination configuration filename.
    - When omitted, the device saves to the currently selected or default configuration file.
    type: str
  verbose:
    description:
    - When true, request the device to save both the current and default configuration state.
    - Only applicable to Fabric Engine; ignored when unset.
    type: bool

```