#!/usr/bin/env python3
"""Seedet ein paar Kanäle in eine lokale ChannelFinder-Instanz (Sandbox-Smoke-Test).

Warum standalone + plain ``requests``: Der MCP-eigene ``ChannelFinderClient`` ist
**GET-only** (kann keine Kanäle anlegen), und das Upstream-``channelfinder``-pip-Paket
ist im venv **nicht** installiert. Dieser Seeder schreibt darum per ``requests``-PUT
genau die ``iocName``/``hostName``-Properties, die ``find_channels``/``find_device``
lesen — sonst liefert ein frisch hochgefahrenes (leeres) ChannelFinder still ``[]``
und der ``find_device``-DoD sähe fälschlich „funktioniert, nur keine Daten" aus.

ChannelFinder-Auth: **Lesen** braucht keine Auth; **Schreiben** (PUT) braucht die
Admin-Credentials der lokalen Instanz (eingebettetes LDAP aus ``cf.ldif`` — Test-Creds,
NIE Produktion). Defaults via Env überschreibbar: ``CF_URL`` / ``CF_ADMIN_USER`` /
``CF_ADMIN_PASS`` / ``CF_OWNER``. Die exakten Default-Creds des CF-Images sind in
Phase B aus dem Image (``cf.ldif``/``application.properties``) zu bestätigen; ein
PUT-401 ist der zuerst zu lösende Blocker (Reads verifizieren trotzdem).

Lauf (nach ``docker compose up``):  python sandbox/seed/seed_channelfinder.py
"""

from __future__ import annotations

import json
import os
import sys

import requests

CF_URL = os.getenv("CF_URL", "http://localhost:8080/ChannelFinder").rstrip("/")
CF_USER = os.getenv("CF_ADMIN_USER", "admin")
# demo_auth ist die am Upstream-CF-5.1.0-Image AKTIVE Auth (application.properties:
# embedded_ldap.enabled=false, demo_auth.users=admin / pwds=adminPass). Die cf.ldif-Creds admin/1234
# gehören zur DEAKTIVIERTEN embedded-LDAP-Variante (= ESS-Prod). Per Env überschreibbar.
CF_PASS = os.getenv("CF_ADMIN_PASS", "adminPass")
CF_OWNER = os.getenv("CF_OWNER", "admin")
TIMEOUT = 10.0

# Fallback-Seed: NUR nötig, wenn die echte reccaster->recceiver-Auto-Population (essioc, Phase B)
# nicht läuft. Namen MÜSSEN exakt den e3-IOC-Records entsprechen (Gerät FBIS-DLN01:Ctrl-EVR-01),
# damit find_device(...) (Glob -> exakter Filter) und find_channels treffen.
_IOC = "FBIS-DLN01-Ctrl-EVR-01"
_HOST = "epics-sandbox-test-ioc"
CHANNELS: tuple[tuple[str, str, str], ...] = (
    ("FBIS-DLN01:Ctrl-EVR-01:12VValue", _IOC, _HOST),
    ("FBIS-DLN01:Ctrl-EVR-01:Temp1Value", _IOC, _HOST),
    ("FBIS-DLN01:Ctrl-EVR-01:BMod", _IOC, _HOST),
    ("FBIS-DLN01:Ctrl-EVR-01:EvtACnt-I", _IOC, _HOST),
    ("FBIS-DLN01:Ctrl-EVR-01:CmdRst", _IOC, _HOST),
)
PROPERTY_NAMES: tuple[str, ...] = ("iocName", "hostName")


def _channel_payload(name: str, ioc: str, host: str) -> dict[str, object]:
    """ChannelFinder-Kanal-JSON: properties als Liste {name,value,owner} (RecSync-Konvention)."""
    return {
        "name": name,
        "owner": CF_OWNER,
        "properties": [
            {"name": "iocName", "value": ioc, "owner": CF_OWNER},
            {"name": "hostName", "value": host, "owner": CF_OWNER},
        ],
        "tags": [],
    }


def _ensure_properties(session: requests.Session) -> None:
    """Eine Property muss existieren, bevor ein Kanal sie referenziert (PUT properties/<name>)."""
    for prop in PROPERTY_NAMES:
        resp = session.put(
            f"{CF_URL}/resources/properties/{prop}",
            json={"name": prop, "owner": CF_OWNER},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()


def main() -> int:
    session = requests.Session()
    session.auth = (CF_USER, CF_PASS)
    session.headers.update({"content-type": "application/json", "accept": "application/json"})
    try:
        _ensure_properties(session)
        for name, ioc, host in CHANNELS:
            resp = session.put(
                f"{CF_URL}/resources/channels/{name}",
                json=_channel_payload(name, ioc, host),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            sys.stdout.write(f"seeded {name} -> iocName={ioc} hostName={host}\n")
        # Seed-Verify (read braucht keine Auth) — fängt den „leeres CF -> false-OK"-Fall.
        first = CHANNELS[0][0]
        check = session.get(f"{CF_URL}/resources/channels/{first}", timeout=TIMEOUT)
        check.raise_for_status()
        sys.stdout.write(f"verify {first}:\n" + json.dumps(check.json(), indent=2) + "\n")
    except requests.HTTPError as exc:
        sys.stderr.write(
            f"FEHLER: {exc} — Admin-Creds prüfen (CF_ADMIN_USER/CF_ADMIN_PASS) "
            f"und ob ChannelFinder läuft.\n"
        )
        return 1
    except requests.RequestException as exc:
        sys.stderr.write(f"FEHLER: ChannelFinder unter {CF_URL} nicht erreichbar: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
