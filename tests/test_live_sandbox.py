"""Live-Regressionstests gegen eine laufende lokale EPICS-Sandbox (opt-in).

Diese Tests sprechen echte Services auf localhost an und sind darum **doppelt** gegated:
  * der ``live``-pytest-Marker (in ``pyproject.toml`` registriert) — wählen mit ``-m live``;
  * ein ``skipif`` auf die Env-Var ``EPICS_SANDBOX`` — so SKIPpt ein explizites ``-m live``
    auf einem Host ohne Sandbox, statt zu ERRORen.
Das Default-Gate (``uv run pytest`` bzw. ``-m "not live"``) deselektiert sie; CI bleibt ohne
Sandbox grün. Lauf nach ``docker compose up`` + PVA-Env (name-server = der funktionierende Pfad):
  ``EPICS_SANDBOX=1 EPICS_MCP_PROVIDER=pva EPICS_PVA_NAME_SERVERS=127.0.0.1:5075``
  ``uv run pytest -m live``

ALLE Client-/``Context``-/Env-Arbeit passiert **innerhalb** der Test-Funktionen — nie auf
Modul-Ebene —, damit die pytest-Collection (die das Modul importiert, bevor ``-m`` greift)
nie das Netz anfasst.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live

_NO_SANDBOX = not os.getenv("EPICS_SANDBOX")
_SKIP_REASON = "EPICS_SANDBOX=1 setzen + sandbox/docker-compose starten, um Live-Tests zu fahren"

# Eigenes Gate für den ChannelFinder-Test: CF ist Phase B (noch nicht da). Ohne dieses separate
# Gate würde die dokumentierte IOC-Live-Lane (``-m live`` mit nur dem e3-IOC) am CF-Connect rot.
_NO_CF = not os.getenv("EPICS_SANDBOX_CF")
_SKIP_CF_REASON = "EPICS_SANDBOX_CF=1 + ChannelFinder (Phase B) seeden, um den CF-Test zu fahren"


def _reset_epics_singletons() -> None:
    """Gecachte Config + p4p-Context verwerfen, damit der Test das aktuelle Shell-Env sieht.

    ``get_config()``/``get_context()`` memoisieren beim ersten Aufruf; ohne diesen Reset
    würde ein früherer In-Session-Aufruf einen veralteten provider/URL festpinnen.
    """
    import epics_pv_mcp.config as config_module
    import epics_pv_mcp.services.epics_client as epics_client_module

    config_module._config = None
    epics_client_module._context = None


# Echte ESS-benannte PV des e3-Test-IOC (Gerät FBIS-DLN01:Ctrl-EVR-01); VAL=12.0 deterministisch.
_PV_ANALOG = "FBIS-DLN01:Ctrl-EVR-01:12VValue"
_PV_ENUM = "FBIS-DLN01:Ctrl-EVR-01:BMod"


@pytest.mark.skipif(_NO_SANDBOX, reason=_SKIP_REASON)
async def test_get_pv_value_returns_live_value() -> None:
    """ai-Record vom e3-Test-IOC über PVA lesen -> der .db-Default 12.0 V (Proof of Life)."""
    _reset_epics_singletons()
    from epics_pv_mcp.services.epics_client import pv_get

    result = await pv_get(_PV_ANALOG)
    assert result["pv_name"] == _PV_ANALOG
    assert result["value"] == pytest.approx(12.0)
    # NT display kommt nur über PVA/QSRV2 (CA traegt das nicht) — bestaetigt den PVA-Pfad.
    display = result.get("display")
    assert isinstance(display, dict) and display.get("units") == "V"


@pytest.mark.skipif(_NO_SANDBOX, reason=_SKIP_REASON)
async def test_get_pv_value_enum_ntenum() -> None:
    """mbbi-Record -> NTEnum (index + label); beweist die enum-Dekodierung gegen ein echtes IOC."""
    _reset_epics_singletons()
    from epics_pv_mcp.services.epics_client import pv_get

    result = await pv_get(_PV_ENUM)
    enum = result.get("enum")
    assert isinstance(enum, dict) and enum.get("label") == "Production"


@pytest.mark.skipif(_NO_CF, reason=_SKIP_CF_REASON)
def test_find_channels_returns_source_ioc() -> None:
    """find_channels(<PV>) -> iocName/hostName-Provenienz (GET, keine Auth) — Phase B."""
    from epics_pv_mcp.config import get_config
    from epics_pv_mcp.services.channelfinder_client import ChannelFinderClient

    url = get_config().channelfinder_url or "http://localhost:8080/ChannelFinder"
    channels = ChannelFinderClient(url).find_channels(_PV_ANALOG)
    assert channels, "ChannelFinder lieferte keine Kanäle — wurde die Sandbox geseedet?"
    assert channels[0]["ioc_name"]
