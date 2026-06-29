#!/usr/bin/env python3
"""Meldet ein deterministisches Set EVR-PVs in der lokalen Archiver Appliance zum Archivieren an.

Warum standalone + plain ``requests`` (gleiche STRUKTUR wie ``seed_channelfinder.py``, aber eine
ANDERE REST-API): Der MCP-eigene ``ArchiverClient`` ist **GET-only** (er kann nur LESEN —
``is_archived``/``get_pv_history``) und kann keine PV zum Archivieren anmelden. Dieser Seeder ruft
die mgmt-BPL-API ``archivePV`` und pollt dann ``getPVStatus``, bis die Appliance die PV als
``"Being archived"`` führt (die Engine braucht eine ~Minuten-„Initial sampling"-Phase, bevor sie
kippt — der Poll-Loop ist genau dafür).

⚠ Diese Liste ist BEWUSST vom ChannelFinder-Seed (``seed_channelfinder.py``) **entkoppelt**: sie
enthält ``3V3Value`` (die nie-manuell-CF-geseedete, aber via recsync-auto-populate registrierte
Proof-PV) statt ``CmdRst`` — so beweist sich der Archiver-Pfad unabhängig vom CF-Seed. Alle Namen
sind echte e3-IOC-Records (Gerät ``FBIS-DLN01:Ctrl-EVR-01``); eine getemplatete/tote PV würde die
Engine ins Leere archivieren.

Defaults via Env: ``ARCHIVER_URL`` / ``ARCHIVE_POLL_TRIES`` / ``ARCHIVE_POLL_INTERVAL``.

Lauf (nach ``docker compose up archiver``, ~1-2 Min Anlauf):  python sandbox/seed/archive_evr_pvs.py
"""

from __future__ import annotations

import os
import sys
import time

import requests

ARCH_URL = os.getenv("ARCHIVER_URL", "http://localhost:17665").rstrip("/")
TIMEOUT = 10.0
POLL_TRIES = int(os.getenv("ARCHIVE_POLL_TRIES", "30"))
POLL_INTERVAL = float(os.getenv("ARCHIVE_POLL_INTERVAL", "10"))
# Status-String der MGMT-API für eine aktiv-archivierte PV (= ArchiverClient.ARCHIVING_STATUS).
ARCHIVING_STATUS = "Being archived"

# Deterministisches Archiver-Set — echte e3-IOC-Records, entkoppelt vom CF-Seed (s. Docstring).
ARCHIVE_PVS: tuple[str, ...] = (
    "FBIS-DLN01:Ctrl-EVR-01:12VValue",
    "FBIS-DLN01:Ctrl-EVR-01:Temp1Value",
    "FBIS-DLN01:Ctrl-EVR-01:EvtACnt-I",
    "FBIS-DLN01:Ctrl-EVR-01:3V3Value",
    "FBIS-DLN01:Ctrl-EVR-01:BMod",
)


def _archive(session: requests.Session, pv: str) -> None:
    """Meldet *pv* zum Archivieren an (mgmt-BPL ``archivePV``, Default-Policy)."""
    resp = session.get(f"{ARCH_URL}/mgmt/bpl/archivePV", params={"pv": pv}, timeout=TIMEOUT)
    resp.raise_for_status()


def _status(session: requests.Session, pv: str) -> str:
    """Liest den MGMT-Status von *pv* (``getPVStatus`` liefert eine 1-Element-Liste)."""
    resp = session.get(f"{ARCH_URL}/mgmt/bpl/getPVStatus", params={"pv": pv}, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return str(data[0].get("status", "Unknown"))
    return "Unknown"


def main() -> int:
    session = requests.Session()
    session.headers.update({"accept": "application/json"})
    try:
        for pv in ARCHIVE_PVS:
            _archive(session, pv)
            sys.stdout.write(f"archivePV angefordert: {pv}\n")
        # Pollen, bis alle „Being archived" sind (oder Versuche erschöpft) — Sampling dauert.
        pending = set(ARCHIVE_PVS)
        last_status: dict[str, str] = {}
        for _ in range(POLL_TRIES):
            for pv in sorted(pending):
                status = _status(session, pv)
                last_status[pv] = status
                if status == ARCHIVING_STATUS:
                    pending.discard(pv)
                    sys.stdout.write(f"  {pv}: {status}\n")
            if not pending:
                break
            time.sleep(POLL_INTERVAL)
        if pending:
            # Den TATSÄCHLICHEN Status je pending-PV zeigen — „Not being archived" (verpufft) vs
            # „Initial sampling" (nur Geduld) sind sonst nicht unterscheidbar.
            detail = ", ".join(f"{pv}={last_status.get(pv, '?')}" for pv in sorted(pending))
            sys.stderr.write(
                f"WARN: nicht '{ARCHIVING_STATUS}' nach {POLL_TRIES} Versuchen: {detail} "
                f"(Initial sampling dauert; getPVStatus später erneut prüfen).\n"
            )
            return 0  # nicht-fatal: die Anmeldung ist durch, nur das Kippen dauert
        sys.stdout.write("alle PVs werden archiviert.\n")
    except requests.HTTPError as exc:
        sys.stderr.write(
            f"FEHLER: {exc} — Appliance unter {ARCH_URL} erreichbar? archivePV-API verfügbar?\n"
        )
        return 1
    except requests.RequestException as exc:
        sys.stderr.write(f"FEHLER: Archiver unter {ARCH_URL} nicht erreichbar: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
