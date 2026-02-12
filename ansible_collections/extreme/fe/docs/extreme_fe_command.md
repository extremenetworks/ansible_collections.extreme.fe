# extreme_fe_command

```yaml

module: extreme_fe_command
short_description: Execute CLI commands on ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
- Execute one or more CLI commands on ExtremeNetworks Fabric Engine (VOSS) switches using the
  custom ``extreme_fe`` HTTPAPI plugin.
- Ensures the commands run in the order provided and submits them as a single REST operation to
  ``/v0/operation/system/cli``.
- Returns the CLI output for every command and fails when any command reports an error.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped
  with this project.
- Designed for Fabric Engine (VOSS) targets; other platforms are not supported.
requirements:
- ansible.netcommon
options:
  commands:
    description:
    - Ordered list of CLI commands to execute on the device.
    - Commands are sent as a single REST payload so execution order is preserved.
    required: true
    type: list
    elements: str
  continue_on_failure:
    description:
    - Continue executing commands after a failure is reported for a previous entry.
    - The module still fails when any command returns a non-200 status code, but the switch
      may execute subsequent commands when this option is true.
    type: bool
    default: false

```