# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# HTTPAPI plugin for ExtremeNetworks Fabric Engine switches

from __future__ import annotations

DOCUMENTATION = """
author:
  - Bjorn Haas (@bhaas_extr)
name: extreme_fe
short_description: HTTPAPI plugin for ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
  - Provides authentication and request helpers for ExtremeNetworks Fabric Engine
    switches that expose the REST API under ``/rest/openapi``.  Authentication
    tokens are generated via the ``/v0/operation/auth-token/:generate`` endpoint
    and stored as the ``x-auth-token`` cookie for subsequent requests.
  - Inventories may identify switches by DNS hostname or FQDN. Fabric Engine
    9.3.2.0 and 9.4.0.0 abort the TLS handshake when the ClientHello carries
    the SNI (Server Name Indication) extension, and a client sends SNI only
    when it connects by name -- RFC 6066 forbids sending it for an IP literal.
    This plugin therefore resolves the configured host to an IP address and
    points the connection at that address before the first request, so the
    handshake carries no SNI extension. See I(resolve_hostname).
extends_documentation_fragment:
  - ansible.netcommon.connection_persistent
options:
  base_path:
    description:
      - Base REST API path prefix used for all requests.
    type: str
    default: /rest/openapi
  auth_endpoint:
    description:
      - Relative endpoint used to obtain an authentication token.
    type: str
    default: /v0/operation/auth-token/:generate
  resolve_hostname:
    description:
      - Whether to resolve a DNS hostname or FQDN to an IP address and connect
        to that address, so the TLS handshake carries no SNI extension.
      - Applies to TLS connections only. With C(ansible_httpapi_use_ssl=false)
        there is no ClientHello and so no SNI to avoid, and the name is what the
        C(Host) header is built from, so such a host is left exactly as the
        inventory spells it.
      - Has no effect when the configured host is already an IP literal.
        Such a host is still bracketed if it is an unbracketed IPv6 address,
        whatever this option is set to, because a bare IPv6 address cannot be
        placed in a request URL.
      - A name that resolves only to scoped (zone-bearing) IPv6 addresses
        fails with an explicit error. A zone identifier such as C(%eth0) cannot
        be carried in a request URL, so such an address would resolve but not
        connect. Set this option to C(false) to reach those hosts by name.
      - A host pinned to its own self-signed certificate is detected and left
        alone automatically. When certificate validation is enabled
        (C(ansible_httpapi_validate_certs=true)) and I(ca_path) points at a
        file holding B(exactly one) B(self-signed) certificate -- the setup
        C(examples/README.md) documents, where the switch's own certificate is
        its trust anchor -- that certificate is inspected. If it carries the
        host name as its CN or as a C(dNSName) SAN, the connection is made by
        name, because verifying it against a resolved address would fail.
      - Such a host is connected to by address only when the address it
        resolves to is itself one of the certificate's C(iPAddress) SAN
        entries. An C(iPAddress) SAN for some other address is no help - the
        handshake is verified against the address actually connected to - so
        the name is kept in that case as well.
      - A I(ca_path) holding more than one certificate is a trust store by
        construction, so nothing is inferred from it. A name matching one entry
        of a bundle says nothing about which certificate the peer serves, and
        the bundle may hold several switches or a stale entry. Point I(ca_path)
        at the single switch certificate, or set this option to C(false), for a
        host that has to be reached by name.
      - Nothing is inferred from a conventional CA bundle. I(ca_path) is a
        trust store, and an issuer certificate says nothing about the endpoint,
        so such deployments resolve to an address like any other. If the switch
        serves a certificate with only C(dNSName) entries, set this option to
        C(false) to keep connecting by name.
      - A self-signed certificate is read as the endpoint's own only when it
        says so - its C(extendedKeyUsage) names TLS server authentication, or,
        where that extension is absent, C(basicConstraints) marks it as not a
        CA. A root CA may legally omit both, so a certificate carrying neither
        says nothing about itself, is treated as a trust anchor, and the host is
        resolved to an address. Set this option to C(false) for a switch whose
        certificate cannot be told apart from a CA.
      - Set to C(false) to always connect by name. Note that a switch running
        an affected release then aborts the handshake, since connecting by name
        is what sends the SNI extension.
    type: bool
    default: true
    version_added: 1.3.0
    vars:
      - name: ansible_httpapi_resolve_hostname
"""

import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path

from ansible.errors import AnsibleConnectionFailure
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import ConnectionError
from ansible_collections.ansible.netcommon.plugins.plugin_utils.httpapi_base import (
    HttpApiBase,
)

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import (
    REQUEST_NOT_SENT,
    http_status,
    is_not_sent_code,
)

DEFAULT_CONTENT_TYPE = "application/json"
DEFAULT_ACCEPT = "application/json"
HTTPAPI_LOG = Path("/tmp/httpapi.log")


class HttpApi(HttpApiBase):
    FACTS_MODULES = ["extreme_fe_facts"]
    LOG_TRUNCATE_LIMIT = 4096
    # Seconds to wait when probing one resolver result for reachability. Kept
    # short: it only picks between candidates, and the result is cached for the
    # play, so at worst this costs one timeout per unreachable record per host.
    ADDRESS_PROBE_TIMEOUT = 2.0
    # Path fragments whose request/response bodies are never written to the
    # verbose (-vvv) log or the EXTREME_FE_HTTP_TRACE file, even truncated.
    # (The accounts endpoint is on LOG_SUPPRESSED_PATH_MARKERS, see there.)
    # The CLI endpoint (extreme_fe_command) is here too: its bodies are free-form
    # command text and output, so no credential can be found by key and scrubbed;
    # an HTTP/207 error echoing a password-bearing command or output must be fully
    # redacted. Normal per-command responses still reach the module unchanged.
    # The system-services (web server and IQAgent proxy passwords), SNMP
    # (communities, SNMPv3 passwords) and OSPF (authentication keyString)
    # endpoints are here as well: every GET returns those credentials, but no
    # module ever submits one to them (ssh and web PATCH flags only, snmp only
    # the system name, facts and OSPF only read), so a device error quoting a
    # stored credential has no submitted value to scrub it against. Their errors
    # keep their status code and lose the device text.
    SECRET_BEARING_PATH_MARKERS = (
        "/operation/system/cli",
        "/configuration/system-services",
        "/configuration/snmp",
        "/configuration/ospf",
    )
    # Paths whose HTTP 207 multi-status answer is returned to the module as data
    # instead of raised: the VLAN membership operations (extreme_fe_vlans) report
    # a result per interface, and the module classifies a partial failure itself
    # (changed=true, details.applied_interfaces). Raising would lose those
    # entries - only the message and code of an exception survive the
    # persistent connection.
    MULTI_STATUS_PASSTHROUGH_PATH_MARKERS = ("/interfaces/:add", "/interfaces/:remove")
    # Path fragments whose request/response bodies are likewise never written
    # to the -vvv log or the EXTREME_FE_HTTP_TRACE file, but whose parsed
    # device error detail is KEPT for a request that carries a body (a PATCH) -
    # only scrubbed of the credential values themselves (see
    # _sanitize_error_text()), unlike the full stand-in
    # SECRET_BEARING_PATH_MARKERS get. A GET carries no body, so a stored key the
    # device quotes in free-form error text could not be found: its parsed error
    # detail is fully redacted (status code kept). A free-form transport failure raised
    # by the underlying connection is fully redacted on these paths too (see
    # _sanitize_connection_error()). The autosense endpoint
    # (extreme_fe_autosense) carries the Fabric Attach authentication key
    # (fabricAttach.authKey.value) and the ISIS hello key
    # (isis.helloAuth.key.value) in its PATCH bodies and GET responses, but
    # its device errors (e.g. "Cvid is configurable only when i-sid has a
    # non-zero value.") are what a user needs to diagnose a failed change,
    # and that module never returns either key, so blanking the whole detail
    # would cost diagnosis without protecting anything the scrub does not.
    # The marker also matches /configuration/autosense/port/<port>, which
    # carries no secret: its bodies are suppressed too, a small debugging
    # cost for a rule that cannot miss the secret-bearing path. The RADIUS
    # endpoints (extreme_fe_radius) are treated the same way: their bodies carry
    # the global password, the AAA / dynamic-authorization shared secrets
    # (secret.value) and the secure-profile private key and passphrase (key,
    # password), and a GET returns the device's stored forms of them.
    # The same applies to /spbm/isis/ (extreme_fe_vlans reads logical-ifs;
    # ports share the schema): the ISIS circuit authKey. And to the accounts
    # endpoint (extreme_fe_local_users), which carries a password in both
    # directions: secret.value/oldSecret.value/superUserPassword on the way
    # in, and the device's own encrypted secret.value on the way back out on
    # a GET. Its bodies are never logged (the module redacts its own result,
    # but this plugin logs the raw body before the module sees it - the same
    # reason login() below suppresses the auth-token response body), while
    # the device's error for a POST or PATCH ("Invalid user type. Supported
    # values are ADMIN, ADMIN_LIMITED, READ_ONLY.", "Cannot update user
    # password and user state at the same time.") is kept, scrubbed of every
    # credential the request sent or the response carries. A GET,
    # a bodyless DELETE and a plain-text answer keep only the status code.
    # (/operation/system/cli, /configuration/system-services, /configuration/snmp
    # and /configuration/ospf are on SECRET_BEARING_PATH_MARKERS instead, see
    # there.)
    LOG_SUPPRESSED_PATH_MARKERS = (
        "/configuration/autosense",
        "/configuration/radius",
        "/spbm/isis/",
        "/configuration/accounts",
    )
    # Keys whose value is a credential inside a device response. Suppressing
    # the logged body is not enough on its own: a 207 or >= 400 answer has
    # its error message built from that same body below, and that message
    # travels to the module as the ConnectionError text. A GET carries no
    # request body for the module to scrub against, so a secret the DEVICE
    # returned has to be removed here, before the exception leaves this
    # plugin. 'secret'/'oldSecret' and SECRET_SCALAR_KEYS mirror
    # SECRET_OBJECT_KEYS/SECRET_SCALAR_KEYS in
    # modules/extreme_fe_local_users.py; keep those in step. 'authKey' and
    # 'key' are the autosense {isEncrypted, value} objects
    # (fabricAttach.authKey, isis.helloAuth.key). 'key' is a generic name,
    # but scrubbing an extra non-secret value from an error text is harmless.
    # 'password' and 'key' as plain strings are the RADIUS global password and
    # the secure-profile passphrase and private key; the same reasoning applies
    # to their generic names. 'roPassword' / 'rwaPassword' (web server),
    # 'password' (IQAgent HTTP proxy) and 'authenticationPassword' /
    # 'encryptionPassword' (SNMPv3) are {isEncrypted, value} / {value}
    # objects; 'community' (SNMP v1/v2c) and 'keyString' (OSPF) are strings.
    SECRET_OBJECT_KEYS = (
        "secret",
        "oldSecret",
        "authKey",
        "key",
        "password",
        "roPassword",
        "rwaPassword",
        "authenticationPassword",
        "encryptionPassword",
    )
    SECRET_SCALAR_KEYS = ("superUserPassword", "password", "key", "community", "keyString")
    # Transport failures whose text is worth one more attempt. Shared by
    # login() and send_request(), and by _loggable_error() so a redacted
    # failure line still names the reason the attempt was retried.
    RETRY_SIGNATURES = (
        "DECRYPTION_FAILED_OR_BAD_RECORD_MAC",
        "LENGTH_MISMATCH",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._trace_enabled = bool(int(os.getenv("EXTREME_FE_HTTP_TRACE", "0")))
        trace_path = os.getenv("EXTREME_FE_HTTP_TRACE_PATH")
        self._trace_log = Path(trace_path) if trace_path else None
        self._log_counter = 0
        self._decision_name: str | None = None
        self._decision_options: tuple | None = None
        self._decision_address: str | None = None
        self._hook_transport_test()

    def _hook_transport_test(self) -> None:
        """Own the probe ``wait_for_connection`` makes, and its teardown.

        Upstream's ``transport_test`` builds its URL straight from the ``host``
        option and never enters this plugin, so left alone it would connect by
        name and send the SNI extension the rest of this plugin exists to avoid.
        It also calls ``open_url`` with no options at all, which fails the
        documented self-signed setup and ignores the proxy settings the real
        request uses. There is no plugin-side hook for either it or ``close``,
        so the connection's own methods are wrapped.
        """
        connection = self.connection
        original = getattr(connection, "transport_test", None)
        if original is None or getattr(original, "_extreme_fe_resolves", False):
            return

        def transport_test(connect_timeout):
            try:
                self._resolve_host_to_ip()
                return self._probe_transport(connect_timeout, original)
            except Exception:
                # The probe is retried until it succeeds, and a reset between
                # attempts skips logout() while the connection is not yet
                # connected. Releasing the address here is what lets the next
                # attempt re-resolve instead of retrying one that has moved.
                self._release_decision()
                raise

        transport_test._extreme_fe_resolves = True
        try:
            connection.transport_test = transport_test
        except AttributeError:  # pragma: no cover - defensive
            return

        original_close = getattr(connection, "close", None)
        if original_close is None:
            return

        def close():
            # close() only reaches logout() when the connection is connected,
            # and the probe above never sets that flag, so the address has to be
            # released here too or a reset would carry it into the next attempt.
            try:
                return original_close()
            finally:
                self._release_decision()

        try:
            connection.close = close
        except AttributeError:  # pragma: no cover - defensive
            pass

    def _probe_transport(self, connect_timeout, original) -> None:
        """Request the API root the way a real request would reach it.

        Upstream passes nothing but a timeout, so its probe validates
        certificates against the system trust store, ignores I(ca_path),
        I(use_proxy) and the client certificate, and sends no credentials - and
        then fails a device the task itself can talk to. The options are
        mirrored from ``Connection.send`` so the probe answers the same
        question.
        """
        try:
            from ansible.module_utils.urls import open_url

            url = self.connection._url
            kwargs = {
                "timeout": connect_timeout,
                "use_proxy": self.connection.get_option("use_proxy"),
                "validate_certs": self.connection.get_option("validate_certs"),
                "ca_path": self.connection.get_option("ca_path"),
                "client_cert": self.connection.get_option("client_cert"),
                "client_key": self.connection.get_option("client_key"),
                "http_agent": self.connection.get_option("http_agent"),
            }
            # _connect() is what copies session_key into _auth, and it has not
            # run yet at probe time, so the option is read directly here -
            # otherwise a session-key inventory probes with no credentials.
            auth = self.connection._auth or self.connection.get_option("session_key")
            if auth:
                kwargs["headers"] = dict(auth)
            else:
                kwargs["force_basic_auth"] = True
                kwargs["url_username"] = self.connection.get_option("remote_user")
                kwargs["url_password"] = self.connection.get_option("password")
            ciphers = self.connection.get_option("ciphers")
            if ciphers:
                # meta/runtime.yml requires ansible-core >= 2.19, so `ciphers`
                # is always accepted here - upstream's version guard covers the
                # older cores this collection does not support.
                kwargs["ciphers"] = ciphers
        except Exception:  # pragma: no cover - defensive
            # Anything unexpected about the connection object and the upstream
            # probe is still better than no probe.
            return original(connect_timeout)

        open_url(url, **kwargs)

    @staticmethod
    def _strip_brackets(value: str) -> str:
        """Return an IPv6 literal without the brackets a URL authority needs."""
        if value.startswith("[") and value.endswith("]"):
            return value[1:-1]
        return value

    @classmethod
    def _is_ip_literal(cls, value: str) -> bool:
        """Whether the value is an IP address, bracketed or not."""
        candidate = cls._strip_brackets(value)
        for family in (socket.AF_INET, socket.AF_INET6):
            try:
                socket.inet_pton(family, candidate)
                return True
            except (OSError, ValueError):
                continue
        return False

    @classmethod
    def _as_url_host(cls, address: str) -> str:
        """Return an address in the form netcommon can put in a URL authority.

        ``ansible.netcommon.httpapi`` builds its URL as ``scheme://{host}:{port}``,
        so a bare IPv6 address has to be bracketed or the authority does not
        parse - ``https://2001:db8::1:9443`` is not a valid URL. IPv4 addresses
        and host names are returned unchanged.
        """
        candidate = cls._strip_brackets(address)
        try:
            socket.inet_pton(socket.AF_INET6, candidate)
        except (OSError, ValueError):
            return address
        return f"[{candidate}]"

    def _resolve_host_to_ip(self) -> None:
        """Point the connection at an IP address so no TLS SNI extension is sent.

        Fabric Engine 9.3.2.0 and 9.4.0.0 abort the handshake when the
        ClientHello carries SNI, which a client sends only when connecting by
        name. Overriding the connection's ``host`` option makes
        ``ansible.netcommon.httpapi`` build its request URL from the address,
        so the standard connection plugin performs the request unmodified.
        """
        host = self.connection.get_option("host")
        if not host:
            return
        host = str(host)

        # An IP literal is handled before the opt-out below. There is nothing to
        # resolve either way - which is what I(resolve_hostname) means by having
        # no effect for a literal - but an inventory may still supply an IPv6
        # address unbracketed, and netcommon cannot place that in a URL
        # authority. Turning resolution off must not leave the host in a form
        # that cannot be used at all. This also covers the address this method
        # set earlier in the play, since bracketing is idempotent.
        if self._is_ip_literal(host):
            url_host = self._as_url_host(host)
            if url_host != host:
                self.connection.set_option("host", url_host)
            if url_host != self._decision_address:
                # An address the inventory supplied rather than the one this
                # method put there, so the host really has changed and an
                # earlier decision must not outlive it.
                self._forget_decision()
            return

        if not self.get_option("resolve_hostname"):
            # Drop any earlier decision. Re-enabling the option later has to
            # start a fresh lookup, or the address from before the opt-out would
            # be re-asserted and a DNS failover in between missed.
            self._forget_decision()
            return

        if not self.connection.get_option("use_ssl"):
            # Without TLS there is no ClientHello and so no SNI to avoid, and
            # the name is what the plain-HTTP Host header - and any virtual
            # host routing behind it - is built from. Nothing to gain, and a
            # working connection to lose.
            self._forget_decision()
            return

        # The decision depends on more than the name: the certificate
        # inspection reads validate_certs and ca_path, and a later task of the
        # same play may set them differently. Keying on the name alone would
        # re-assert a decision the current task's options no longer support.
        options = self._decision_option_key()
        if host != self._decision_name or options != self._decision_options:
            # The key is stored only once the decision succeeds. Assigning it
            # first would make a transient resolver failure stick: the retry
            # would see the same name, skip this block with no address recorded,
            # and connect by name after all - reintroducing the SNI extension
            # this method exists to avoid.
            address = self._connect_address_for(host)
            self._decision_name = host
            self._decision_options = options
            self._decision_address = address

        if self._decision_address:
            # Ansible re-applies the inventory-derived connection options before
            # every task of a play, which resets `host` back to the name, so the
            # address has to be re-asserted rather than set once per connection.
            self.connection.set_option("host", self._decision_address)

    def _forget_decision(self) -> None:
        """Discard the cached connect-by-name/by-address decision."""
        self._decision_name = None
        self._decision_options = None
        self._decision_address = None

    def _release_decision(self) -> None:
        """Put the inventory name back in ``host`` and drop the decision.

        The name has to go back first: a caller that gets here before Ansible
        reapplies the inventory would otherwise find an IP literal in ``host``
        and never re-resolve it. It goes back only while ``host`` still holds
        the address this plugin put there - once the inventory names a different
        device, restoring the old name would send the next task to the wrong one.
        """
        if self._decision_name and self._decision_address:
            try:
                current = str(self.connection.get_option("host") or "")
                if current == self._decision_address:
                    self.connection.set_option("host", self._decision_name)
            except Exception:  # pragma: no cover - defensive
                pass
        self._forget_decision()

    def _decision_option_key(self) -> tuple:
        """The connection options the connect-by-name/by-address decision reads.

        Covers the certificate inspection (validate_certs, ca_path) and the
        candidate selection in _lookup_address(), which probes the configured
        port and skips probing when the request would be proxied.
        """
        try:
            return (
                bool(self.get_option("resolve_hostname")),
                bool(self.connection.get_option("validate_certs")),
                self.connection.get_option("ca_path"),
                self.connection.get_option("port"),
                bool(self.connection.get_option("use_ssl")),
                bool(self.connection.get_option("use_proxy")),
                self._proxy_environment_key(),
            )
        except Exception:  # pragma: no cover - defensive
            return ()

    @staticmethod
    def _proxy_environment_key() -> tuple:
        """The proxy settings _proxy_url_for() reads from the environment.

        They are not connection options, so the key has to sample them for a
        change to C(https_proxy) or C(no_proxy) to be noticed at all.
        """
        from urllib.request import getproxies

        try:
            proxies = getproxies()
        except Exception:  # pragma: no cover - defensive
            return ()
        return (proxies.get("http"), proxies.get("https"), proxies.get("no"))

    def _connect_address_for(self, host: str) -> str | None:
        """Return the address to connect to, or None to keep connecting by name."""
        covered = self._pinned_certificate_addresses(host)

        if covered is None:
            address = self._lookup_address(host)
            self._emit_http_debug(f"resolved host {host} to {address} for the TLS connection")
            return address

        if not covered:
            self._emit_http_debug(
                f"keeping the connection to {host} by name: the certificate at "
                "ca_path identifies it by name and carries no address, so "
                "verifying against a resolved address would fail"
            )
            return None

        # The certificate covers addresses, but only one it actually lists can
        # be connected to: any other would fail verification just as surely as
        # none at all, so the selection is confined to those.
        address = self._lookup_address(host, restrict_to=covered)
        if address is not None:
            self._emit_http_debug(f"resolved host {host} to {address} for the TLS connection")
            return address

        self._emit_http_debug(
            f"keeping the connection to {host} by name: the certificate at "
            f"ca_path covers {', '.join(sorted(covered))}, which is not among "
            "the addresses the name resolves to, so verifying against one of "
            "them would fail"
        )
        return None

    @classmethod
    def _canonical_address(cls, value: str) -> str:
        """An address in one comparable form, whatever notation it arrived in."""
        from ipaddress import ip_address

        candidate = cls._strip_brackets(value)
        try:
            return str(ip_address(candidate))
        except ValueError:
            return candidate

    def _pinned_certificate_addresses(self, host: str) -> set[str] | None:
        """The addresses the certificate pinned at ``ca_path`` covers for *host*.

        Returns ``None`` when ``ca_path`` is not a single pinned certificate
        naming this host - the ordinary case, where the host is resolved like
        any other. An empty set means the certificate names the host and covers
        no address at all, so only the name can be verified.

        ``ca_path`` is a trust store, not necessarily the peer certificate, so
        its contents say nothing about the server in the general case. There is
        one exception, and it is the setup ``examples/README.md`` documents: a
        self-signed switch certificate installed as its own trust anchor. There
        the file *is* the peer certificate.

        Only that case is inferred. A real CA bundle - anything not self-signed
        - describes an issuer, not the endpoint, so nothing is concluded from
        it. If such a deployment serves a certificate with only ``dNSName``
        entries, set C(ansible_httpapi_resolve_hostname=false) to keep
        connecting by name.
        """
        if not self.connection.get_option("validate_certs"):
            return None

        ca_path = self.connection.get_option("ca_path")
        if not ca_path:
            return None

        certificates = self._load_certificates(ca_path)
        if certificates is None:
            # The inspection could not run. Say so rather than silently
            # treating "unknown" as "resolve to the address".
            self._emit_http_debug(
                f"could not inspect {ca_path}, so the certificate was not "
                f"consulted for {host}; set resolve_hostname=false if this "
                "host must be reached by name"
            )
            return None

        # Only a file holding exactly one certificate is read as a pin. A
        # bundle is a trust store by construction, and a name matching one
        # entry of it says nothing about which certificate this peer serves -
        # it may hold several switches, or a stale or wildcard entry.
        if len(certificates) != 1:
            self._emit_http_debug(
                f"{ca_path} holds {len(certificates)} certificates, so it is a "
                f"trust store rather than {host}'s own certificate and was not "
                "used to decide how to connect; point ca_path at the single "
                "switch certificate, or set resolve_hostname=false, if this "
                "host must be reached by name"
            )
            return None

        # Only a self-signed server certificate can be assumed to be the peer's.
        # A trust store may hold self-signed roots too, so one whose subject
        # happens to match the inventory host is excluded rather than mistaken
        # for the endpoint.
        self_signed = [c for c in certificates if self._is_self_signed(c)]
        certificates = [c for c in self_signed if self._is_endpoint_certificate(c)]
        if not certificates:
            if self_signed:
                self._emit_http_debug(
                    f"{ca_path} holds a self-signed certificate that does not "
                    "identify itself as a server certificate - basicConstraints "
                    "marks it a CA and no extendedKeyUsage claims serverAuth - "
                    f"so it was read as a trust anchor and {host} will be "
                    "resolved to an address; set resolve_hostname=false if this "
                    "host must be reached by name"
                )
            else:
                self._emit_http_debug(
                    f"{ca_path} holds no self-signed certificate, so it is a "
                    f"trust store rather than {host}'s own certificate and was "
                    "not used to decide how to connect"
                )
            return None

        for certificate in certificates:
            names, ip_sans = self._certificate_names(certificate)
            if not any(self._name_matches(host, name) for name in names):
                continue
            return {self._canonical_address(value) for value in ip_sans}

        return None

    @staticmethod
    def _certificate_names(certificate) -> tuple[list[str], list[str]]:
        """The names a certificate identifies and the addresses it covers.

        The CN counts whenever the SAN carries no C(dNSName), not only when the
        extension is missing altogether - OpenSSL falls back to it in exactly
        that case, so a certificate with a CN and an address-only SAN does name
        its host.
        """
        from cryptography import x509

        def common_names() -> list[str]:
            return [
                attribute.value
                for attribute in certificate.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            ]

        try:
            san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        except x509.ExtensionNotFound:
            return (common_names(), [])
        except Exception:  # pragma: no cover - defensive
            return ([], [])

        dns_names = list(san.get_values_for_type(x509.DNSName))
        addresses = [str(value) for value in san.get_values_for_type(x509.IPAddress)]
        return (dns_names or common_names(), addresses)

    @staticmethod
    def _load_certificates(ca_path: str):
        """Load every certificate in a PEM file, or None if that is not possible.

        Returns None - meaning "unknown", not "none found" - when ``cryptography``
        is absent or the file cannot be read or parsed. ``load_pem_x509_certificates``
        arrived in cryptography 36.0; older versions fall back to reading the
        first certificate only, which is enough for the single self-signed
        certificate this inspection cares about.
        """
        try:
            from cryptography import x509
        except ImportError:
            return None

        try:
            with open(ca_path, "rb") as handle:
                data = handle.read()
        except OSError:
            return None

        loader = getattr(x509, "load_pem_x509_certificates", None)
        try:
            if loader is not None:
                return loader(data)
            # The single-block fallback cannot report how many certificates the
            # file really holds, and the caller reads that count as "pinned".
            # Say "unknown" instead of understating a bundle as one.
            if data.count(b"-----BEGIN CERTIFICATE-----") != 1:
                return None
            return [x509.load_pem_x509_certificate(data)]
        except Exception:
            return None

    @classmethod
    def _is_self_signed(cls, certificate) -> bool:
        """Whether a certificate carries its own signature.

        Matching subject and issuer only makes a certificate self-*issued*; a
        cross-signed one looks the same and is signed by somebody else's key.
        The signature is therefore checked against the certificate's own public
        key, and a certificate that cannot be checked is not treated as pinned.
        """
        try:
            if certificate.subject != certificate.issuer:
                return False
        except Exception:  # pragma: no cover - defensive
            return False

        verifier = getattr(certificate, "verify_directly_issued_by", None)
        if verifier is not None:
            try:
                verifier(certificate)
                return True
            except Exception:
                return False
        return cls._signature_verifies_with_own_key(certificate)

    @staticmethod
    def _signature_verifies_with_own_key(certificate) -> bool:
        """Check a certificate's signature by hand.

        ``verify_directly_issued_by`` arrived in cryptography 40 and the
        controller's version is not pinned, so on an older one the same question
        is asked of the key directly.
        """
        try:
            from cryptography.hazmat.primitives.asymmetric import (
                ec,
                ed448,
                ed25519,
                padding,
                rsa,
            )

            key = certificate.public_key()
            signature = certificate.signature
            body = certificate.tbs_certificate_bytes
            if isinstance(key, rsa.RSAPublicKey):
                key.verify(
                    signature,
                    body,
                    padding.PKCS1v15(),
                    certificate.signature_hash_algorithm,
                )
            elif isinstance(key, ec.EllipticCurvePublicKey):
                key.verify(signature, body, ec.ECDSA(certificate.signature_hash_algorithm))
            elif isinstance(key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
                key.verify(signature, body)
            else:
                return False
            return True
        except Exception:
            return False

    @staticmethod
    def _is_endpoint_certificate(certificate) -> bool:
        """Whether a self-signed certificate is a server's own, not a trust anchor.

        Only a positive marker counts, and the extended key usage is the one
        that settles it - a self-signed certificate may be CA-capable and serve
        TLS at the same time, so C(serverAuth) is read before anything the key
        usage says. Where that extension is absent, C(basicConstraints) decides.
        A root CA may legally omit both, so a certificate carrying neither says
        nothing about itself and is left as a trust anchor.
        """
        from cryptography import x509

        try:
            extensions = certificate.extensions
        except Exception:
            return False

        try:
            extended = extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        except x509.ExtensionNotFound:
            extended = None
        except Exception:
            return False
        if extended is not None:
            return x509.oid.ExtendedKeyUsageOID.SERVER_AUTH in extended

        try:
            if extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign:
                return False
        except x509.ExtensionNotFound:
            pass
        except Exception:
            return False

        try:
            basic = extensions.get_extension_for_class(x509.BasicConstraints).value
        except x509.ExtensionNotFound:
            return False
        except Exception:
            return False
        return not basic.ca

    @staticmethod
    def _to_ascii_name(name: str) -> str:
        """Return a host name in the A-label form a certificate carries.

        ``getaddrinfo()`` takes an internationalised name as Unicode, while an
        X.509 C(dNSName) spells the same name in punycode, so the two would
        never compare equal without this.
        """
        if name.isascii():
            return name
        try:
            return name.encode("idna").decode("ascii")
        except (UnicodeError, ValueError):
            return name

    @classmethod
    def _name_matches(cls, host: str, certificate_name: str) -> bool:
        host = cls._to_ascii_name(host.lower().rstrip("."))
        certificate_name = str(certificate_name).lower().rstrip(".")
        if certificate_name.startswith("*."):
            # A wildcard matches exactly one label (RFC 6125). The '*' is not a
            # valid label, so only the suffix goes through IDNA.
            suffix = cls._to_ascii_name(certificate_name[2:])
            return host.split(".", 1)[1:] == [suffix]
        return host == cls._to_ascii_name(certificate_name)

    def _lookup_address(self, host: str, restrict_to: set[str] | None = None) -> str | None:
        """Resolve *host* and return the first address that accepts a connection.

        A name with several A/AAAA records may have an unreachable or
        unsupported record first. The socket layer would normally try each
        candidate in turn, but replacing the connection host commits to one
        address before any connection is made, so the candidates are probed
        here. If none answer - the port is filtered, or the device is down -
        the first result is returned unchanged, leaving the real failure to
        surface from the request itself rather than from this probe.

        *restrict_to* limits the choice to the addresses a pinned certificate
        covers; C(None) is returned when no resolved address is among them, so
        the caller can keep connecting by name rather than commit to one that
        would fail verification.
        """
        try:
            results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ConnectionError(f"Unable to resolve host '{host}' to an IP address: {exc}") from exc

        if not results:
            raise ConnectionError(f"Unable to resolve host '{host}' to an IP address: no records")

        # Collect the distinct candidates first. A scoped IPv6 result is
        # dropped here: the zone identifier lives in sockaddr[3] and cannot
        # survive into the URL netcommon builds, so selecting one would yield
        # an address that resolves but cannot be connected to.
        candidates: list[tuple[int, tuple]] = []
        seen: set[str] = set()
        scoped_skipped = 0
        for family, _socktype, _proto, _canon, sockaddr in results:
            if self._is_scoped_ipv6(family, sockaddr):
                scoped_skipped += 1
                continue
            address = sockaddr[0]
            if address not in seen:
                seen.add(address)
                candidates.append((family, sockaddr))

        if not candidates:
            raise ConnectionError(
                f"Unable to use any address resolved for host '{host}': "
                f"all {scoped_skipped} record(s) are scoped IPv6 addresses, "
                "whose zone identifier cannot be carried in a request URL. "
                "Set ansible_httpapi_resolve_hostname=false to connect by "
                "name, or give the inventory a routable address."
            )

        if scoped_skipped:
            self._emit_http_debug(
                f"ignored {scoped_skipped} scoped IPv6 record(s) for {host}: "
                "a zone identifier cannot be carried in a request URL"
            )

        if restrict_to is not None:
            eligible = [
                candidate for candidate in candidates if self._canonical_address(candidate[1][0]) in restrict_to
            ]
            if not eligible:
                return None
            candidates = eligible

        # With a single candidate there is nothing to choose between, so the
        # probe is skipped entirely. Probing it would buy nothing - the address
        # is returned either way - and would add a full timeout to every
        # unreachable host before the real request reports the same failure.
        if len(candidates) == 1:
            return self._as_url_host(candidates[0][1][0])

        for family, sockaddr in candidates:
            # The route is decided per candidate: the request URL carries the
            # address chosen here, and no_proxy may cover one record and not
            # another, so one address can be proxied while the next is direct.
            proxy_url = self._proxy_url_for(sockaddr[0])
            if proxy_url:
                accepted = self._proxy_accepts_connection(proxy_url, sockaddr[0])
                if accepted is None:
                    # The probe cannot model this route, so its answer would be
                    # about the probe rather than about the address.
                    self._emit_http_debug(
                        f"the route to {host} through "
                        f"{self._redact_proxy_url(proxy_url)} cannot be probed, "
                        f"so its {len(candidates)} addresses were left "
                        f"unranked; using {candidates[0][1][0]} and letting the "
                        "request report any failure"
                    )
                    return self._as_url_host(candidates[0][1][0])
            else:
                accepted = self._address_accepts_connection(family, sockaddr)
            if accepted:
                self._emit_http_debug(
                    f"{host} resolved to {len(results)} records; using "
                    f"{sockaddr[0]}, the first that accepted a connection"
                    + (f" through {self._redact_proxy_url(proxy_url)}" if proxy_url else "")
                )
                return self._as_url_host(sockaddr[0])

        self._emit_http_debug(
            f"none of the {len(candidates)} addresses for {host} accepted a "
            f"connection; using {candidates[0][1][0]} and letting the request "
            "report the failure"
        )
        return self._as_url_host(candidates[0][1][0])

    @staticmethod
    def _redact_proxy_url(proxy_url: str) -> str:
        """A proxy URL with any credentials stripped, safe to log.

        C(https_proxy) may carry C(user:password@), which must not reach the
        debug log.
        """
        from urllib.parse import urlsplit

        try:
            parsed = urlsplit(proxy_url if "//" in proxy_url else f"//{proxy_url}")
            if not parsed.hostname:
                return "the configured proxy"
            authority = parsed.hostname
            if parsed.port:
                authority = f"{authority}:{parsed.port}"
            return f"{parsed.scheme}://{authority}" if parsed.scheme else authority
        except ValueError:
            return "the configured proxy"

    def _proxy_url_for(self, address: str) -> str | None:
        """The proxy netcommon would send a request for *address* through, if any.

        Asked per address rather than per host name, because by the time the
        request is made the name is gone - the URL carries whichever address
        was selected, and that is what C(no_proxy) is matched against.

        Only the scheme-specific entry is read. ``getproxies()`` also reports
        C(ALL_PROXY) as ``all``, but ``urllib`` never routes through it: its
        ``ProxyHandler`` is dispatched as ``<scheme>_open``, so the ``all_open``
        it installs is dead code and the request goes direct. Honouring ``all``
        here would model a route the real request does not take.
        """
        try:
            if not self.connection.get_option("use_proxy"):
                return None
            scheme = "https" if self.connection.get_option("use_ssl") else "http"
        except Exception:  # pragma: no cover - defensive
            return None

        from urllib.request import getproxies, proxy_bypass

        try:
            proxy_url = getproxies().get(scheme)
            if not proxy_url:
                return None
            return None if proxy_bypass(address) else proxy_url
        except Exception:  # pragma: no cover - defensive
            return None

    def _proxy_accepts_connection(self, proxy_url: str, address: str) -> bool | None:
        """Whether the proxy will open a tunnel to *address* on the API port.

        Mirrors what the real request asks of it - a C(CONNECT) to the address
        that is about to go into the URL - so a record the proxy cannot reach is
        passed over instead of being committed to. C(CONNECT) is the right
        question because this is only reached for a TLS connection; a plain
        HTTP connection is never resolved to an address in the first place.

        Returns C(None) when the probe cannot speak for the real request: a
        proxy reached over TLS, or one asking for an authentication scheme
        beyond the Basic credentials a proxy URL can carry. A C(False) from
        those would say the address is unreachable when nothing about the
        address was ever tested.
        """
        from base64 import b64encode
        from urllib.parse import unquote, urlsplit

        try:
            parsed = urlsplit(proxy_url if "//" in proxy_url else f"//{proxy_url}")
            proxy_host = parsed.hostname
            proxy_port = parsed.port or (443 if parsed.scheme == "https" else 80)
            username, password = parsed.username, parsed.password
        except ValueError:
            return None
        if not proxy_host:
            return None
        if parsed.scheme == "https":
            # The real request speaks TLS to the proxy itself. A plaintext
            # probe would fail for reasons that say nothing about the address.
            return None

        port = self._effective_port()
        target = f"[{address}]:{port}" if ":" in address else f"{address}:{port}"
        lines = [f"CONNECT {target} HTTP/1.1", f"Host: {target}"]
        if username is not None:
            secret = f"{unquote(username)}:{unquote(password or '')}".encode()
            lines.append("Proxy-Authorization: Basic " + b64encode(secret).decode("ascii"))
        request = ("\r\n".join(lines) + "\r\n\r\n").encode()
        try:
            with socket.create_connection((proxy_host, proxy_port), timeout=self.ADDRESS_PROBE_TIMEOUT) as probe:
                probe.settimeout(self.ADDRESS_PROBE_TIMEOUT)
                probe.sendall(request)
                status_line = probe.recv(256).split(b"\r\n", 1)[0]
        except OSError:
            return False
        if b" 407" in status_line:
            return None
        return b" 200 " in status_line or status_line.endswith(b" 200")

    @staticmethod
    def _is_scoped_ipv6(family: int, sockaddr: tuple) -> bool:
        """Whether a resolver result is a scoped (zone-bearing) IPv6 address.

        For ``AF_INET6`` the resolver returns
        ``(address, port, flowinfo, scope_id)``; a non-zero ``scope_id``, or a
        ``%zone`` suffix on the address itself, means the address is only
        meaningful together with that zone.
        """
        if family != socket.AF_INET6:
            return False
        if len(sockaddr) > 3 and sockaddr[3]:
            return True
        return "%" in str(sockaddr[0])

    def _effective_port(self) -> int:
        """The port the request will use, defaulted the way netcommon defaults it."""
        try:
            port = int(self.connection.get_option("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if port:
            return port
        return 443 if self.connection.get_option("use_ssl") else 80

    def _address_accepts_connection(self, family: int, sockaddr: tuple) -> bool:
        """Whether a TCP connection to *sockaddr* on the configured port succeeds.

        Takes the whole resolver tuple rather than the bare address so the
        IPv6 flow information and zone survive into the probe; connecting to
        ``sockaddr[0]`` alone would misreport those addresses.

        Used only to choose between several resolver results - it is never
        reached when the name resolves to one address. The probe is
        deliberately short, and the decision is cached for the play, so this
        runs at most once per host rather than once per task.
        """
        target = (sockaddr[0], self._effective_port()) + tuple(sockaddr[2:])
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(self.ADDRESS_PROBE_TIMEOUT)
                probe.connect(target)
            return True
        except OSError:
            return False

    def _coerce_connection_error(self, exc: Exception) -> ConnectionError:
        if isinstance(exc, ConnectionError):
            return exc

        kwargs = {}
        code = getattr(exc, "code", None)
        if code is not None:
            kwargs["code"] = code
        err = getattr(exc, "err", None)
        if err is not None:
            kwargs["err"] = err
        return ConnectionError(to_text(exc), **kwargs)

    def _sanitize_connection_error(self, exc: ConnectionError, log_body: bool) -> ConnectionError:
        """
        Return *exc* as-is on a path that may carry its body, or a copy whose
        message and .err are both replaced by the same redacted stand-in
        _loggable_error() uses for the log line.

        A transport failure raised by the underlying connection (rather than
        by this plugin's own >=400/207 handling, which already sanitizes
        before raising) can embed a request or response body verbatim,
        including the device's own encrypted secret.value on the accounts
        endpoint (a LOG_SUPPRESSED path). That exception is what ends up as the module's
        fail_json(msg=..., err=...), so redacting only the line written to
        the log - as _loggable_error() alone does - would still let the
        credential reach the playbook output through the exception itself.

        send_request() passes its log_body here, so a LOG_SUPPRESSED path
        (autosense) gets the full stand-in as well: this free text has no
        structure to scrub selectively, and the stored keys an autosense GET
        response carries are not known to the plugin beforehand. Its parsed
        device errors keep their scrubbed detail via _sanitize_error_text().
        The exception code and the retry signature suffix are kept.
        """
        if log_body:
            return exc
        safe_message = self._loggable_error(to_text(exc), log_body)
        kwargs = {}
        code = getattr(exc, "code", None)
        if code is not None:
            kwargs["code"] = code
        if getattr(exc, "err", None) is not None:
            kwargs["err"] = safe_message
        return ConnectionError(safe_message, **kwargs)

    def _full_path(self, path: str) -> str:
        base = self.get_option("base_path") or "/rest/openapi"
        return "/".join(
            [
                base.rstrip("/"),
                path.lstrip("/"),
            ]
        )

    def _ensure_connected_host(self) -> str | None:
        host = getattr(self.connection, "_connected_host", None)
        if host:
            return host

        candidates = [
            getattr(self.connection, "_host", None),
            getattr(self.connection, "host", None),
        ]

        httpapi = getattr(self.connection, "_httpapi", None)
        if httpapi is not None:
            candidates.extend(
                [
                    getattr(httpapi, "_host", None),
                    getattr(httpapi, "host", None),
                ]
            )
        url = getattr(self.connection, "_url", None)
        if url is not None:
            candidates.append(getattr(url, "hostname", None))
        play_context = getattr(self.connection, "_play_context", None)
        if play_context is not None:
            candidates.extend(
                [
                    getattr(play_context, "remote_addr", None),
                    getattr(play_context, "remote_host", None),
                ]
            )

        host_value: str | None = None
        for candidate in candidates:
            if candidate:
                host_value = str(candidate)
                break

        if host_value:
            port = getattr(self.connection, "_port", None) or getattr(self.connection, "port", None)
            if port:
                host_value = f"{host_value}:{port}"
            try:
                self.connection._connected_host = host_value
            except Exception:  # pragma: no cover - defensive
                pass
        return host_value

    def login(self, username: str, password: str) -> None:
        """Obtain the session token (netcommon calls this before the first request is sent).

        A failure is raised marked REQUEST_NOT_SENT (see _not_sent()): netcommon
        logs in from inside send(), before the request it was asked to send, so
        that request cannot have reached the device.
        """
        try:
            self._login(username, password)
        except Exception as exc:
            # from None: the login failure was already sanitized (its body carries
            # the password), and chaining the original would undo that.
            raise self._not_sent(exc) from None

    def _not_sent(self, exc: Exception) -> ConnectionError:
        """Return *exc* as a ConnectionError marked REQUEST_NOT_SENT.

        Only the code crosses the persistent connection to the module, so the
        marker is the code. Every failure is marked, one with an HTTP status
        too (the device answered the login with 401 or 500): that status is the
        login's, not the request's, and left as the code a module would take it
        for the request's own answer. It is kept in the message instead, and
        the marker lets _send_with_retries() turn a failed re-login after an
        attempt that may have been sent into an unknown outcome.
        """
        coerced = self._coerce_connection_error(exc)
        code = getattr(coerced, "code", None)
        if is_not_sent_code(code):
            return coerced
        message = to_text(coerced)
        status = http_status(code)
        if status is not None and str(status) not in message:
            message = "%s (HTTP %d)" % (message.rstrip("."), status)
        if "the request was not sent" not in message:
            message = "%s (the request was not sent)" % message.rstrip(".")
        kwargs = {"code": REQUEST_NOT_SENT}
        if getattr(coerced, "err", None) is not None:
            kwargs["err"] = coerced.err
        return ConnectionError(message, **kwargs)

    def _login(self, username: str, password: str) -> None:
        if self.connection._auth:
            return

        try:
            self._resolve_host_to_ip()
        except Exception:
            # netcommon marks the connection connected before calling login, so
            # a failure here would be remembered as a live connection with no
            # token, and `ensure_connect` would skip login from then on.
            self._release_decision()
            try:
                self.connection._connected = False
            except Exception:  # pragma: no cover - defensive
                pass
            raise

        payload = json.dumps({"username": username, "password": password})
        headers = {
            "Content-Type": DEFAULT_CONTENT_TYPE,
            "Accept": DEFAULT_ACCEPT,
        }
        path = self._full_path(self.get_option("auth_endpoint") or "/v0/operation/auth-token/:generate")
        # Cache the connected host for enhanced logging context.
        connected_host = getattr(self.connection, "_connected_host", None)
        if not connected_host:
            connected_host = getattr(self.connection, "_host", None) or getattr(self.connection, "host", None)
            if connected_host:
                try:
                    self.connection._connected_host = connected_host
                except Exception:  # pragma: no cover - defensive
                    pass

        max_attempts = 5
        last_exc: ConnectionError | None = None
        self._ensure_connected_host()
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                HTTPAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
                with HTTPAPI_LOG.open("a") as fh:
                    fh.write(f"{timestamp} login attempt {attempt}/{max_attempts} POST {path}\n")
            try:
                request_id = self._log_request("POST", path, None, is_retry=attempt > 1)
                response, response_data = self.connection.send(path, payload, headers=headers, method="POST")
                token_payload = self._parse_response(
                    response,
                    response_data,
                    method="POST",
                    path=path,
                    log_body=False,
                    request_id=request_id,
                )
                token = None
                if isinstance(token_payload, dict):
                    token = token_payload.get("token")
                if not token:
                    raise ConnectionError(
                        "Failed to obtain authentication token from device",
                        code=getattr(response, "code", None),
                    )
                cookie = f"x-auth-token={token}"
                self.connection._auth = {"Cookie": cookie, "x-auth-token": token}
                if attempt > 1:
                    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    with HTTPAPI_LOG.open("a") as fh:
                        fh.write(f"{timestamp} login success on attempt {attempt} POST {path}\n")
                return
            except (ConnectionError, AnsibleConnectionFailure) as exc:
                coerced_exc = self._coerce_connection_error(exc)
                message = to_text(coerced_exc)
                # The auth-token endpoint always carries a password, so its
                # failure text is never loggable or returnable raw - see
                # _sanitize_connection_error(). last_exc/the raise below use
                # the sanitized exception; only the retry-signature match
                # above needs the original text.
                coerced_exc = self._sanitize_connection_error(coerced_exc, False)
                last_exc = coerced_exc
                if any(sig in message for sig in self.RETRY_SIGNATURES) and attempt < max_attempts:
                    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    log_line = f"{timestamp} login retry {attempt} for POST {path}: " f"{to_text(coerced_exc)}\n"
                    HTTPAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
                    with HTTPAPI_LOG.open("a") as fh:
                        fh.write(log_line)
                    time.sleep(2)
                    continue
                # from None, not from exc: exc is the unsanitized original
                # _sanitize_connection_error() just replaced coerced_exc
                # with a redacted copy of - chaining it as the cause would
                # still let its raw message reach a chained traceback (e.g.
                # jsonrpc.py's traceback.format_exc() at -vvv), undoing the
                # redaction.
                raise coerced_exc from None
        if last_exc is not None:
            timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            log_line = (
                f"{timestamp} login retries exhausted POST {path}: "
                f"{self._loggable_error(to_text(last_exc), False)}\n"
            )
            HTTPAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
            with HTTPAPI_LOG.open("a") as fh:
                fh.write(log_line)
            raise last_exc
        raise ConnectionError("Retries exhausted while contacting device during login")

    def logout(self) -> None:
        self.connection._auth = None
        # The connection is being torn down or reset, so the resolved address
        # must not outlive it: after a DNS failover or a readdressed device the
        # same name belongs somewhere else.
        self._release_decision()
        # The logging context is part of the same decision: left behind, every
        # later message would still name the host this connection used to reach.
        try:
            self.connection._connected_host = None
        except Exception:  # pragma: no cover - defensive
            pass

    def send_request(self, data, **message_kwargs):
        try:
            # Everything before _send_with_retries() runs before the request
            # leaves (resolving the host, building the body): a failure here is
            # marked REQUEST_NOT_SENT, so a module never reports such a write as
            # possibly applied.
            self._resolve_host_to_ip()
            method = (message_kwargs.get("method") or "GET").upper()
            path = message_kwargs.get("path") or ""
            body, headers = self._request_body_and_headers(data, message_kwargs)

            self._ensure_connected_host()
            full_path = self._full_path(path)
            log_body, keep_error_detail, request_secrets = self._request_log_policy(full_path, method, body)
        except Exception as exc:
            # from None: the body may already be serialized here, and a chained
            # traceback (jsonrpc.py at -vvv) must not carry it.
            raise self._not_sent(exc) from None
        response, response_data, request_id = self._send_with_retries(method, full_path, body, headers, log_body)
        parsed = self._parse_response(
            response,
            response_data,
            method=method,
            path=full_path,
            log_body=log_body,
            request_id=request_id,
        )
        status_code = getattr(response, "code", None) or getattr(response, "status", None)
        # On a path whose bodies are suppressed, a plain-text (non-JSON) answer
        # has no structure to scrub: it could echo a stored password that neither
        # it nor the request names by key, so its detail is not kept.
        if not log_body and not isinstance(parsed, (dict, list)):
            keep_error_detail = False
        error_context = (method, full_path, keep_error_detail, request_secrets)
        # multi_status_passthrough=True (a send_request() keyword) does the same as
        # MULTI_STATUS_PASSTHROUGH_PATH_MARKERS for one request: extreme_fe_facts
        # classifies a 207 itself and skips the endpoint with a warning.
        passthrough = bool(message_kwargs.get("multi_status_passthrough")) or self._multi_status_passthrough(full_path)
        if status_code == 207 and not passthrough:
            self._raise_for_multi_status(parsed, status_code, error_context)
        if isinstance(status_code, int) and status_code >= 400:
            self._raise_for_error_status(parsed, status_code, error_context)
        return parsed

    @staticmethod
    def _request_body_and_headers(data, message_kwargs) -> tuple:
        """Return the serialized request body and the headers for send_request()."""
        headers = {}

        accept = message_kwargs.get("accept") or DEFAULT_ACCEPT
        if accept:
            headers["Accept"] = accept

        content_type = message_kwargs.get("content_type")
        body = None
        if data is not None:
            if isinstance(data, (str, bytes)):
                body = data if isinstance(data, str) else data.decode("utf-8")
            else:
                body = json.dumps(data)
            if not content_type:
                content_type = DEFAULT_CONTENT_TYPE
        if content_type:
            headers["Content-Type"] = content_type
        return body, headers

    def _request_log_policy(self, full_path: str, method: str, body) -> tuple:
        """Return (log_body, keep_error_detail, request_secrets) for one request."""
        # Two separate decisions: log_body governs only what
        # _log_request()/_log_response() write; keep_error_detail governs the
        # sanitizers of the device errors parsed below. A SECRET_BEARING path
        # loses both; a LOG_SUPPRESSED path loses the logged bodies and, for a
        # request with a non-empty body, keeps its parsed device error detail,
        # scrubbed of the credentials its response or the request body we sent
        # carries (a device may echo a submitted key). A free-form transport
        # failure raised by the underlying connection is governed by log_body
        # instead - see the except clause in _send_with_retries().
        full_redact = self._path_carries_secrets(full_path)
        log_body = not (full_redact or self._path_suppresses_logs(full_path))
        # A request without a body (a GET, or a bodyless DELETE such as the
        # RADIUS server/profile DELETE) submits no secret, so a key the device
        # quotes in free-form error text cannot be found and scrubbed: on a
        # LOG_SUPPRESSED path such an error loses its detail entirely. A
        # request carrying a non-empty body (a PATCH, POST or PUT) keeps the
        # scrubbed detail, because the keys it carries are known; a GET stays
        # suppressed whatever it carries. A path that is not LOG_SUPPRESSED
        # (log_body True) keeps its detail as before.
        keep_error_detail = not full_redact and (log_body or (method != "GET" and self._has_request_body(body)))
        request_secrets = self._request_secret_values(body) if keep_error_detail and not log_body else []
        return log_body, keep_error_detail, request_secrets

    @staticmethod
    def _has_request_body(body) -> bool:
        """Return True when *body* is a non-empty request body (not None, blank, {} or [])."""
        if isinstance(body, bytes):
            body = to_text(body, errors="surrogate_then_replace")
        if not isinstance(body, str) or not body.strip():
            return False
        return body.strip() not in ("{}", "[]")

    @staticmethod
    def _append_httpapi_log(line: str) -> None:
        """Append one timestamped line to HTTPAPI_LOG."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        HTTPAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
        with HTTPAPI_LOG.open("a") as fh:
            fh.write(f"{timestamp} {line}\n")

    def _send_with_retries(self, method: str, full_path: str, body, headers: dict, log_body: bool) -> tuple:
        """
        Send one request, retrying transport failures that match RETRY_SIGNATURES.

        Returns (response, response_data, request_id). Any other transport
        failure, or the last retryable one, is raised sanitized for log_body.
        """
        max_attempts = 5
        last_exc: ConnectionError | None = None
        request_id: str | None = None
        # True once an attempt failed in a way that may have reached the device:
        # a later attempt failing before it is sent (a re-login marked
        # REQUEST_NOT_SENT) must not hide that the request may be applied.
        maybe_sent = False
        for attempt in range(1, max_attempts + 1):
            try:
                # Before connection.send(): a failure here (an unwritable log or
                # trace path, say) did not send this attempt. It is not sent at
                # all unless an earlier attempt may have been (maybe_sent).
                if attempt > 1:
                    self._append_httpapi_log(f"attempt {attempt}/{max_attempts} {method} {full_path}")
                is_retry = attempt > 1
                request_id = self._log_request(method, full_path, body, is_retry=is_retry, log_body=log_body)
            except Exception as exc:
                failure = self._not_sent(exc)
                if maybe_sent:
                    failure = self._unmark_not_sent(failure)
                # from None: the log line being written may carry the body.
                raise failure from None
            try:
                response, response_data = self.connection.send(
                    full_path,
                    body,
                    headers=headers,
                    method=method,
                )
                if attempt > 1:
                    self._append_httpapi_log(f"success on attempt {attempt} {method} {full_path}")
                return response, response_data, request_id
            except (ConnectionError, AnsibleConnectionFailure) as exc:
                coerced_exc = self._coerce_connection_error(exc)
                message = to_text(coerced_exc)
                # The failure text may quote the body this path is not
                # allowed to log or return - see _sanitize_connection_error().
                # last_exc/the raise below use the sanitized exception; only
                # the retry-signature match further down needs the original
                # text.
                unsanitized_exc = coerced_exc
                # log_body, not keep_error_detail: on a LOG_SUPPRESSED path
                # this free-form text is fully redacted like a SECRET_BEARING
                # one. Unlike a parsed device error it has no structure to
                # scrub, and a GET sends no request body to collect secrets
                # from, so a response body it quotes (stored authKey/helloAuth
                # key values) could not be scrubbed reliably. A device HTTP
                # error (e.g. the 422 "Cvid is configurable only when i-sid
                # has a non-zero value.") does not come this way: netcommon's
                # send() passes the HTTPError to handle_httperror(), whose
                # inherited default returns it as the response for any code
                # but 401, so it reaches the parsed >=400 handling in
                # send_request().
                coerced_exc = self._sanitize_connection_error(coerced_exc, log_body)
                if not is_not_sent_code(getattr(coerced_exc, "code", None)):
                    maybe_sent = True
                elif maybe_sent:
                    coerced_exc = self._unmark_not_sent(coerced_exc)
                safe_message = to_text(coerced_exc)
                last_exc = coerced_exc
                self._emit_http_debug(f"{request_id} !! {method} {full_path} failed: {safe_message}")
                if any(sig in message for sig in self.RETRY_SIGNATURES):
                    self._append_httpapi_log(f"retry {attempt} for {method} {full_path}: {safe_message}")
                    if attempt < max_attempts:
                        time.sleep(2)
                        continue
                # from None on a secret-bearing path, not from exc: exc is
                # the unsanitized original _sanitize_connection_error() just
                # replaced coerced_exc with a redacted copy of - chaining it
                # as the cause would still let its raw message reach a
                # chained traceback (e.g. jsonrpc.py's traceback.format_exc()
                # at -vvv), undoing the redaction. A non-secret path never
                # got sanitized (coerced_exc is exc itself), so chaining it
                # is unchanged from before. A LOG_SUPPRESSED path is redacted
                # too, so it never chains either.
                raise coerced_exc from (exc if coerced_exc is unsanitized_exc else None)
        # pragma: no cover - safeguard: the last attempt always returns or raises above.
        if last_exc is not None:
            self._append_httpapi_log(
                f"retries exhausted for {method} {full_path}: {self._loggable_error(to_text(last_exc), log_body)}"
            )
            raise last_exc
        raise ConnectionError("Retries exhausted while contacting device")

    @staticmethod
    def _unmark_not_sent(exc: ConnectionError) -> ConnectionError:
        """Return *exc* without the REQUEST_NOT_SENT code: an earlier attempt may have been sent."""
        kwargs = {}
        if getattr(exc, "err", None) is not None:
            kwargs["err"] = exc.err
        return ConnectionError(to_text(exc).replace(" (the request was not sent)", ""), **kwargs)

    def _raise_for_multi_status(self, parsed, status_code, error_context: tuple) -> None:
        """Raise ConnectionError when a 207 multi-status document carries errors."""
        method, full_path, keep_error_detail, request_secrets = error_context
        errors, total_entries = self._multi_status_errors(parsed)
        if not errors:
            return
        message = "; ".join(msg for _code, msg in errors)
        # Preserve the embedded status when EVERY sub-response
        # failed and agrees on one KNOWN code - notably an all-404
        # 207 (an empty accounts collection wrapped in a
        # multi-status document), which _call_api()'s
        # allow_not_found only recognises via exc.code == 404, not
        # 207. codes is built WITHOUT dropping None: an error entry
        # with no recognised code (errorMessage but no
        # errorCode/statusCode/status) is unknown, not "assumed to
        # agree" - filtering it out before the len(codes) == 1 check
        # would let a genuine 404 entry sitting next to such an
        # unknown-coded entry still get promoted, which is exactly
        # as wrong as a 404 mixed with a real 500. len(errors) ==
        # total_entries separately rules out a partial failure: a
        # 404 mixed with a successful sub-response is an INCOMPLETE
        # inventory, not an absent one. Any mix - of codes, or with
        # an unknown code, or with a success - falls back to the
        # transport status like before.
        codes = {code for code, _msg in errors}
        effective_code = (
            codes.pop() if len(codes) == 1 and None not in codes and len(errors) == total_entries else status_code
        )
        raise ConnectionError(
            self._sanitize_error_text(
                f"Multi-status failure for {method} {full_path}: {message}",
                parsed,
                keep_error_detail,
                extra_secrets=request_secrets,
            ),
            code=effective_code,
        )

    @staticmethod
    def _first_error_message(entry) -> str | None:
        """Return the first non-empty error text field of a device error dict."""
        for key in ("errorMessage", "message", "detail", "error"):
            value = entry.get(key)
            if value:
                return to_text(value)
        return None

    def _raise_for_error_status(self, parsed, status_code: int, error_context: tuple) -> None:
        """Raise ConnectionError for an HTTP status >= 400, with the device's error text."""
        method, full_path, keep_error_detail, request_secrets = error_context
        error_message = None
        if isinstance(parsed, dict):
            error_message = self._first_error_message(parsed)
        elif isinstance(parsed, list) and parsed:
            first = parsed[0]
            if isinstance(first, dict):
                error_message = self._first_error_message(first)
            elif first:
                error_message = to_text(first)
        elif parsed:
            error_message = to_text(parsed)

        if not error_message:
            error_message = f"HTTP {status_code} returned for {method} {full_path}"
        raise ConnectionError(
            self._sanitize_error_text(error_message, parsed, keep_error_detail, extra_secrets=request_secrets),
            code=status_code,
        )

    def _emit_http_debug(self, message: str) -> None:
        host = getattr(self.connection, "_connected_host", None)
        if host:
            message = f"[{host}] {message}"
        display = getattr(self.connection, "_display", None)
        if display is not None and getattr(display, "verbosity", 0) >= 3:
            display.vvv(message)
        if self._trace_enabled and self._trace_log:
            timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            self._trace_log.parent.mkdir(parents=True, exist_ok=True)
            with self._trace_log.open("a") as fh:
                fh.write(f"{timestamp} {message}\n")

    def _multi_status_passthrough(self, path: str) -> bool:
        """Return True when a 207 on *path* is returned to the module, see MULTI_STATUS_PASSTHROUGH_PATH_MARKERS."""
        return any(marker in path for marker in self.MULTI_STATUS_PASSTHROUGH_PATH_MARKERS)

    def _path_carries_secrets(self, path: str) -> bool:
        """Return True when *path* is on SECRET_BEARING_PATH_MARKERS."""
        return any(marker in path for marker in self.SECRET_BEARING_PATH_MARKERS)

    def _path_suppresses_logs(self, path: str) -> bool:
        """Return True when *path* is on LOG_SUPPRESSED_PATH_MARKERS."""
        return any(marker in path for marker in self.LOG_SUPPRESSED_PATH_MARKERS)

    @classmethod
    def _request_secret_values(cls, body) -> list[str]:
        """Collect the credential strings inside the request *body* we sent."""
        payload = body
        if isinstance(payload, bytes):
            payload = to_text(payload, errors="surrogate_then_replace")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                return []
        return cls._collect_secret_values(payload)

    @staticmethod
    def _scrub_values(message: str, values) -> str:
        """
        Replace every non-empty value in *values* inside *message*, longest first.

        A device error that quotes the serialized request shows a value in its
        JSON-encoded form, with quotes, backslashes and control characters
        escaped and, with ensure_ascii, non-ASCII characters as \\uXXXX. Both
        encoded forms are replaced along with the raw value. So is the Python
        repr form: _first_error_message() turns a nested error or detail object
        into text with str(), which escapes a value holding both quote types
        (and backslashes or control characters) differently from JSON.
        """
        forms = set()
        for value in values:
            if not value:
                continue
            forms.add(value)
            forms.add(json.dumps(value)[1:-1])
            forms.add(json.dumps(value, ensure_ascii=False)[1:-1])
            forms.add(repr(value)[1:-1])
        for form in sorted((f for f in forms if f), key=len, reverse=True):
            message = message.replace(form, "**REDACTED**")
        return message

    @classmethod
    def _collect_secret_values(cls, payload) -> list[str]:
        """Collect every credential string inside a parsed response body."""
        values: list[str] = []
        if isinstance(payload, dict):
            for secret_key in cls.SECRET_OBJECT_KEYS:
                secret = payload.get(secret_key)
                if isinstance(secret, dict):
                    value = secret.get("value")
                    if isinstance(value, str) and value:
                        values.append(value)
            for scalar_key in cls.SECRET_SCALAR_KEYS:
                value = payload.get(scalar_key)
                if isinstance(value, str) and value:
                    values.append(value)
            for value in payload.values():
                values.extend(cls._collect_secret_values(value))
        elif isinstance(payload, list):
            for item in payload:
                values.extend(cls._collect_secret_values(item))
        return values

    def _sanitize_error_text(self, message: str, parsed, log_body: bool = True, *, extra_secrets=()) -> str:
        """
        Remove any credential *parsed* carries from an error *message*.

        _collect_secret_values() only finds a credential at a known key
        inside a dict/list - 'secret'/'oldSecret'.value or
        'superUserPassword'. That misses a credential the device quotes
        somewhere else in the SAME structured error (the submitted password
        echoed inside errorMessage text, say), and a plain-text body has no
        structure to search at all. Neither gap is acceptable on a
        secret-bearing path, so log_body False suppresses the entire detail
        outright - the same redacted stand-in _loggable_error() uses -
        rather than attempt a selective redaction that cannot be guaranteed
        complete.

        A non-secret path (log_body True) keeps the narrower, best-effort
        scrub instead: applied on every such path regardless of whether it
        is expected to carry a credential, since a body with none in it
        yields nothing to replace either way. This includes a
        LOG_SUPPRESSED path (autosense): its bodies are not logged, but
        send_request() passes True here so its device error survives, plus
        *extra_secrets* - the credentials in the request body it sent - so a
        key the device echoes back is scrubbed too.
        """
        if not log_body:
            return self._loggable_error(message, log_body)
        return self._scrub_values(message, list(self._collect_secret_values(parsed)) + list(extra_secrets))

    def _loggable_error(self, message: str, log_body: bool) -> str:
        """
        Return *message* if bodies may be logged for this path, else a stand-in.

        A transport failure is free text the underlying HTTP layer built, and
        on several failure modes it embeds the request or the response body
        verbatim. Suppressing only the bodies _log_request()/_log_response()
        write would still leak secret.value, oldSecret.value or
        superUserPassword through the failure line, so the same log_body
        decision governs these too. The retry signature, which is what the
        line is actually read for, is matched on the original text and kept.
        """
        if log_body:
            return message
        signature = next((sig for sig in self.RETRY_SIGNATURES if sig in message), None)
        suffix = f" ({signature})" if signature else ""
        return f"<redacted: error detail suppressed for a secret-bearing request>{suffix}"

    def _log_request(
        self,
        method: str,
        path: str,
        body: str | None,
        *,
        is_retry: bool = False,
        log_body: bool = True,
    ) -> str:
        self._log_counter += 1
        request_id = f"#{self._log_counter}"
        retry_suffix = " (retry)" if is_retry else ""
        self._emit_http_debug(f"{request_id} => {method} {path}{retry_suffix}")
        if body and log_body:
            truncated = (
                body if len(body) <= self.LOG_TRUNCATE_LIMIT else f"{body[:self.LOG_TRUNCATE_LIMIT]}... (truncated)"
            )
            self._emit_http_debug(f"{request_id} => payload: {truncated}")
        elif body:
            self._emit_http_debug(f"{request_id} => payload: <redacted>")
        return request_id

    def _log_response(
        self, response, method: str, path: str, raw_text: str | None, log_body: bool, *, request_id: str | None = None
    ) -> None:
        status = getattr(response, "code", None) or getattr(response, "status", None)
        status_display = status if status is not None else ""
        rid = request_id or ""
        rid_prefix = f"{rid} " if rid else ""
        self._emit_http_debug(f"{rid_prefix}<= {status_display} {method} {path}")
        if log_body and raw_text:
            truncated = (
                raw_text
                if len(raw_text) <= self.LOG_TRUNCATE_LIMIT
                else f"{raw_text[:self.LOG_TRUNCATE_LIMIT]}... (truncated)"
            )
            self._emit_http_debug(f"{rid_prefix}<= payload: {truncated}")
        elif raw_text:
            self._emit_http_debug(f"{rid_prefix}<= payload: <redacted>")

    def _parse_response(
        self,
        response,
        buffer,
        *,
        method: str | None = None,
        path: str | None = None,
        log_body: bool = True,
        request_id: str | None = None,
    ):
        raw = buffer.read()
        raw_text = to_text(raw, errors="surrogate_then_replace") if raw else ""
        if method and path:
            self._log_response(response, method, path, raw_text, log_body, request_id=request_id)
        if not raw_text:
            return None
        try:
            return json.loads(raw_text)
        except ValueError:
            return raw_text

    def _multi_status_errors(self, payload) -> tuple[list[tuple[int | None, str]], int]:
        """
        Return (each erroring sub-response as (status_code, message), the
        total number of sub-responses examined - errors and successes alike).

        The code travels alongside the message - not just baked into it -
        so send_request() can raise with that embedded code instead of the
        207 transport status when every sub-response agrees on one; see its
        call site. The total count travels with it so that call site can
        tell "every sub-response failed the same way" (safe to promote)
        apart from "some of them succeeded" (a partial failure, not
        eligible for the not-found - or any other single-code - shortcut
        even when the failing ones happen to agree).
        """
        errors: list[tuple[int | None, str]] = []
        total = 0

        def inspect_entry(entry) -> None:
            nonlocal total
            # Counted before the type check, not after: a non-dict entry
            # (a malformed sub-response) contributes no (code, message) to
            # errors below, so leaving it out of total here would make
            # len(errors) == total_entries at the call site true for a
            # payload that is actually incomplete/malformed rather than
            # genuinely all-error - promoting it to a single embedded code
            # (e.g. treating it as an all-404 not-found) when it should
            # fail closed instead.
            total += 1
            if not isinstance(entry, dict):
                return
            # errorCode first: that is the field Fabric Engine's own error
            # documents use (see _error_code() in extreme_fe_local_users.py,
            # which checks it ahead of statusCode/code for the very same
            # reason) - code/status remain as a fallback for any other
            # schema this multi-status handling also covers.
            status = entry.get("errorCode") or entry.get("statusCode") or entry.get("code") or entry.get("status")
            if isinstance(status, str) and status.isdigit():
                status = int(status)
            is_error = False
            if isinstance(status, int) and status >= 400:
                is_error = True
            if status is None and entry.get("errorMessage"):
                is_error = True
            if is_error:
                iface_type = entry.get("interfaceType") or entry.get("interface_type")
                iface_name = entry.get("interfaceName") or entry.get("interface_name")
                location = []
                if iface_type:
                    location.append(str(iface_type))
                if iface_name:
                    location.append(str(iface_name))
                location_str = " ".join(location)
                prefix = f"{status}" if status is not None else "error"
                message = entry.get("errorMessage") or entry.get("message") or "request failed"
                code = status if isinstance(status, int) else None
                if location_str:
                    errors.append((code, f"{prefix} - {location_str}: {message}"))
                else:
                    errors.append((code, f"{prefix}: {message}"))

        if isinstance(payload, list):
            for item in payload:
                inspect_entry(item)
        elif isinstance(payload, dict):
            responses = None
            if isinstance(payload.get("responses"), list):
                responses = payload.get("responses")
            elif isinstance(payload.get("items"), list):
                responses = payload.get("items")
            if responses is not None:
                for item in responses:
                    inspect_entry(item)
            else:
                inspect_entry(payload)

        return errors, total
