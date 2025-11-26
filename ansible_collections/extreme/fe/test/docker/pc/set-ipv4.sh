#!/usr/bin/env bash
# set-ipv4.sh — Flush existing IPv4 addresses on an interface, add a new one,
# and optionally set a default gateway. Designed for Ubuntu in Docker.

set -Eeuo pipefail

usage() {
  echo "Usage: $0 <iface> <IPv4/CIDR> [gateway]"
  echo "  e.g.: $0 eth1 10.10.10.2/24 10.10.10.1"
  exit 1
}

# ----- Args & basic checks -----
IFACE="${1:-}"; ADDR_CIDR="${2:-}"; GW="${3:-}"

[[ -z "$IFACE" || -z "$ADDR_CIDR" ]] && usage
command -v ip >/dev/null 2>&1 || { echo "Error: 'ip' command not found. Install iproute2."; exit 2; }
ip link show "$IFACE" >/dev/null 2>&1 || { echo "Error: interface '$IFACE' not found."; exit 3; }

if [[ $EUID -ne 0 ]]; then
  echo "Error: must be run as root (or with sudo)." >&2
  exit 4
fi

# Simple IPv4/CIDR sanity check (not exhaustive)
if ! [[ "$ADDR_CIDR" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]]; then
  echo "Error: address must be IPv4/CIDR (e.g. 10.10.10.2/24)"; exit 5
fi
if [[ -n "${GW:-}" && ! "$GW" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "Error: gateway must be an IPv4 address (e.g. 10.10.10.1)"; exit 6
fi

# ----- Do the work -----
echo "Bringing '$IFACE' up…"
ip link set dev "$IFACE" up

echo "Flushing existing IPv4 addresses on '$IFACE'…"
ip -4 addr flush dev "$IFACE"

echo "Adding address $ADDR_CIDR to '$IFACE'…"
ip addr add "$ADDR_CIDR" dev "$IFACE"

# Clear ARP cache for a clean start (optional)
ip neigh flush dev "$IFACE" || true

if [[ -n "${GW:-}" ]]; then
  echo "Setting default route via $GW on '$IFACE'…"
  # Remove any default route(s) on this iface; ignore errors if none exist
  ip -4 route del default dev "$IFACE" 2>/dev/null || true
  # Replace (create or update) the default route
  ip -4 route replace default via "$GW" dev "$IFACE"
fi

# Show results
echo
ip -4 addr show dev "$IFACE"
echo
ip -4 route show default || true
echo "Done."

