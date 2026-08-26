#!/usr/bin/env python3
"""Check that the VPS's public sites answer and their certificates are current.

DSM Task Scheduler runs this on the NAS and mails the output when it exits
non-zero, so a failing exit *is* the alert. It goes out over the public
internet rather than the tailnet on purpose: that path also covers DNS, Caddy
and certificate renewal, none of which a tailnet check would touch.

Deployed to the NAS by hand; DSM is outside Ansible's reach. DSM 7 ships
Python 3.8, so this stays within that.
"""

from __future__ import annotations

import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

SITES = (
    "michalkozak.cz",
    "miniflux.michalkozak.cz",
    "git.michalkozak.cz",
)

CERT_WARN_DAYS = 14
TIMEOUT = 10
# A single blip on the home connection should not raise an alarm.
ATTEMPTS = 3
RETRY_WAIT = 5


def http_failure(host: str) -> str | None:
    """Return why the site did not answer 200, or None if it did."""
    failure = None
    for attempt in range(ATTEMPTS):
        if attempt:
            time.sleep(RETRY_WAIT)
        try:
            with urllib.request.urlopen(
                f"https://{host}/", timeout=TIMEOUT
            ) as response:
                if response.getcode() == 200:
                    return None
                failure = f"HTTP {response.getcode()}"
        except urllib.error.HTTPError as exc:
            failure = f"HTTP {exc.code}"
        except OSError as exc:
            failure = str(exc)
    return failure


def cert_days_left(host: str) -> int:
    context = ssl.create_default_context()
    # Closing the TLS socket closes the plain one it wrapped.
    sock = socket.create_connection((host, 443), timeout=TIMEOUT)
    with context.wrap_socket(sock, server_hostname=host) as tls:
        cert = tls.getpeercert()
    if not cert:
        raise ValueError("no certificate presented")
    seconds = ssl.cert_time_to_seconds(str(cert["notAfter"]))
    expiry = datetime.fromtimestamp(seconds, timezone.utc)
    return (expiry - datetime.now(timezone.utc)).days


def problem(host: str) -> str | None:
    """Return what is wrong with the host, or None; print a line either way."""
    failure = http_failure(host)
    if failure:
        return f"{host} unreachable: {failure}"
    try:
        days = cert_days_left(host)
    except (OSError, ssl.SSLError, ValueError) as exc:
        return f"{host} certificate unreadable: {exc}"
    if days < CERT_WARN_DAYS:
        return f"{host} certificate expires in {days} days"
    print(f"{host} ok, certificate valid {days} more days")
    return None


def main() -> None:
    problems = [found for host in SITES if (found := problem(host))]
    if problems:
        sys.exit("\n".join(problems))


if __name__ == "__main__":
    main()
