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
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.live

_NO_SANDBOX = not os.getenv("EPICS_SANDBOX")
_SKIP_REASON = "EPICS_SANDBOX=1 setzen + sandbox/docker-compose starten, um Live-Tests zu fahren"

# Eigenes Gate für den ChannelFinder-Test: CF ist Phase B (noch nicht da). Ohne dieses separate
# Gate würde die dokumentierte IOC-Live-Lane (``-m live`` mit nur dem e3-IOC) am CF-Connect rot.
_NO_CF = not os.getenv("EPICS_SANDBOX_CF")
_SKIP_CF_REASON = "EPICS_SANDBOX_CF=1 + ChannelFinder (Phase B) seeden, um den CF-Test zu fahren"

# Eigenes Gate für den reccaster-Auto-Populate-Test (Phase B / M2): braucht zusätzlich den laufenden
# recceiver-Service + den test-ioc-channelfinder-net-Join. Ohne dieses Gate würde die geseedete
# IOC-Live-/CF-Lane an einem (noch) fehlenden recceiver rot.
_NO_RECSYNC = not os.getenv("EPICS_SANDBOX_RECSYNC")
_SKIP_RECSYNC_REASON = (
    "EPICS_SANDBOX_RECSYNC=1 + recceiver-Service + test-ioc-channelfinder-net-Join (M2) nötig, "
    "um den reccaster-Auto-Populate-Test zu fahren"
)

# Beide cf_unregistered-Tests brauchen den angehobenen CF-Cap: gegen das ~576-Kanal-EVR-Prefix
# withholdet der CF-Checker beim Default 500 (cf_unregistered → []). Ohne diesen Guard erschiene das
# als kryptische „len 0"-Assertion statt als aktionierbare Skip-Meldung (s. sandbox/README §CF-Cap).
_CF_CAP_MIN = 2000
_CF_CAP_SKIP_REASON = (
    "EPICS_MCP_CHANNELFINDER_MAX_RESULTS=2000 setzen — der CF-Checker withholdet beim Default 500 "
    "gegen das ~576-Kanal-EVR-Prefix (cf_unregistered → []); sonst bräche der Test mit „len 0“."
)


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

# Echtes e3-IOC-Record, das NICHT im M1-Seed steht (Seed = 12VValue/Temp1Value/BMod/
# EvtACnt-I/CmdRst). Sein Auftauchen in CF kann nur vom reccaster stammen
# (essioc→reccaster→recceiver→CF), nicht vom Seed.
_PV_UNSEEDED = "FBIS-DLN01:Ctrl-EVR-01:3V3Value"
_EXPECTED_IOC = "FBIS-DLN01-Ctrl-EVR-01"


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


@pytest.mark.skipif(_NO_RECSYNC, reason=_SKIP_RECSYNC_REASON)
def test_find_channels_no_seed() -> None:
    """Ein NICHT geseedetes Gerät liegt mit iocName im CF → reccaster-Auto-Populate (kein Seed).

    Beweist die Kette essioc→reccaster→recceiver→CF: ``3V3Value`` ist ein echtes IOC-Record,
    aber NICHT unter den fünf M1-Seeds — sein Vorhandensein in CF kann nur der reccaster
    geschrieben haben. Retry-Poll, weil der recceiver alle ~15 s announced und der erste
    CF-Commit nach IOC-(Re)start einige Sekunden braucht.
    """
    from epics_pv_mcp.config import get_config
    from epics_pv_mcp.services.channelfinder_client import ChannelFinderClient

    url = get_config().channelfinder_url or "http://localhost:8080/ChannelFinder"
    client = ChannelFinderClient(url)

    # Auf einen FRISCHEN, aktiven Kanal pollen, nicht nur auf Existenz: cleanOnStart inaktiviert die
    # recceiver-eigenen Kanäle beim Start, der reccaster reaktiviert sie erst beim Reporten →
    # pvStatus=="Active" beweist einen Commit aus DIESEM Lauf (CF löscht Kanäle nie physisch, ein
    # stale "Inactive"-Überbleibsel aus einem früheren Lauf würde sonst false-green machen).
    deadline = time.monotonic() + 90.0
    channels = client.find_channels(_PV_UNSEEDED)
    while not (channels and channels[0]["properties"].get("pvStatus") == "Active"):
        if time.monotonic() >= deadline:
            break
        time.sleep(5.0)
        channels = client.find_channels(_PV_UNSEEDED)

    assert channels, (
        f"{_PV_UNSEEDED} nicht im CF — kam der reccaster-Announce an und schrieb der "
        "recceiver nach CF? recceiver-Log prüfen (CF_COMMIT / 'Total channels to update')."
    )
    status = channels[0]["properties"].get("pvStatus")
    assert status == "Active", (
        f"{_PV_UNSEEDED} im CF, aber pvStatus={status!r} (erwartet 'Active') — die "
        "reccaster→recceiver-Kette hat in DIESEM Lauf nicht frisch geschrieben (evtl. stale)."
    )
    assert channels[0]["ioc_name"] == _EXPECTED_IOC, (
        f"iocName={channels[0]['ioc_name']!r}, erwartet {_EXPECTED_IOC!r} — "
        "sendet der reccaster IOCNAME?"
    )


@pytest.mark.skipif(_NO_CF, reason=_SKIP_CF_REASON)
async def test_cf_unregistered_w1_mechanism(tmp_path: Path) -> None:
    """W1: das cf_unregistered-Mechanismus-Urteil gegen die LIVE ChannelFinder (Subset-Mechanismus).

    Ein winziges synthetisches Display referenziert zwei BEDIENTE Records (12VValue/3V3Value, in CF
    registriert) und ein referenziertes-aber-unbedientes EVR-Register (DlyGen0Prescaler-SP — ein
    echtes mTCA-EVR-300-Register, das die fbis-Displays nutzen, das Spielzeug-IOC aber nicht
    bedient). Assertiert: die bedienten sind NICHT cf_unregistered, das unbediente IST es — die
    exakte Subset-Membership, die die Headline 645/650 nur im Maßstab (vollständiges CF) belegt.
    Schnell + deterministisch (winziges Inventar, ein CF-GET); KEINE 60-s-fbis-Walk.
    """
    _reset_epics_singletons()
    from epics_pv_mcp.config import get_config
    from epics_pv_mcp.tools.crossplane import _crossplane_check

    if get_config().channelfinder_max_results < _CF_CAP_MIN:
        pytest.skip(_CF_CAP_SKIP_REASON)

    prefix = "FBIS-DLN01:Ctrl-EVR-01:"
    served_a = f"{prefix}12VValue"
    served_b = f"{prefix}3V3Value"
    unserved = f"{prefix}DlyGen0Prescaler-SP"

    displays = tmp_path / "displays"
    displays.mkdir()
    (displays / "w1.bob").write_text(
        '<display version="2.0.0"><name>W1</name>'
        f"<macros><P>{prefix}</P></macros>"
        '<widget type="textupdate"><name>a</name><pv_name>$(P)12VValue</pv_name></widget>'
        '<widget type="textupdate"><name>b</name><pv_name>$(P)3V3Value</pv_name></widget>'
        '<widget type="textentry"><name>u</name>'
        "<pv_name>$(P)DlyGen0Prescaler-SP</pv_name></widget></display>",
        encoding="utf-8",
    )
    st_cmd = tmp_path / "st.cmd"
    st_cmd.write_text(
        f'epicsEnvSet("P", "{prefix}")\ndbLoadRecords("evr.db", "P=$(P)")\n', encoding="utf-8"
    )

    result = await _crossplane_check(str(displays), str(st_cmd), query_channelfinder=True)
    report = result["report"]
    assert isinstance(report, dict)
    # Der CF-Query lief wirklich (URL für die Live-Lane gesetzt) — keine "skipped"-Note.
    assert not any("cf_unregistered skipped" in note for note in report["notes"]), (
        "EPICS_MCP_CHANNELFINDER_URL nicht gesetzt — der CF-Check wurde übersprungen."
    )
    cf_unregistered = report["cf_unregistered"]
    assert isinstance(cf_unregistered, list)
    assert unserved in cf_unregistered, (
        f"{unserved} sollte cf_unregistered sein (referenziert, in linked, nicht unter den 9 "
        f"bedienten CF-Kanälen); bekam {cf_unregistered}"
    )
    assert served_a not in cf_unregistered  # bedient + in CF registriert
    assert served_b not in cf_unregistered
    assert report["cf_registered"] >= 5  # CF hält den Gerätesatz unter diesem Prefix (W2: ~576)


# --- W2: voller EVR-Spiegel (567 Sim-Records + 1 bewusste Lücke) ---------------------------------

# Workspace-ROOT der fbis-Displays (BIS/fbis-systemexpert liegt eine Ebene über EPICS-MCP-Server).
_FBIS_ROOT = Path(__file__).resolve().parents[2] / "BIS" / "fbis-systemexpert"
_SANDBOX_ST_CMD = Path(__file__).resolve().parent.parent / "sandbox" / "ioc-e3" / "st.cmd"
# Die EINE bewusst injizierte Lücke (gen_evr_full_db.py GAP). MUSS dem Harvest-Cap entsprechen.
_W2_GAP = "FBIS-DLN01:Ctrl-EVR-01:DlyGen0Prescaler-SP"
# Harvest- UND Test-Cap müssen identisch sein (sonst divergieren bediente vs. linked Menge):
# der Generator erntete evr-records.txt bei DEFAULT context_cap=256 → hier EXPLIZIT 256 pinnen
# (nicht auf DEFAULT_PV_CONTEXT_CAP verlassen — eine Default-Änderung bräche den Beweis still).
_W2_CONTEXT_CAP = 256


@pytest.mark.skipif(_NO_CF, reason=_SKIP_CF_REASON)
@pytest.mark.skipif(
    not _FBIS_ROOT.is_dir(), reason="BIS/fbis-systemexpert nicht im Workspace gefunden"
)
async def test_cf_unregistered_w2_full_mirror_collapses_to_gap() -> None:
    """W2: gegen das volle fbis kollabiert cf_unregistered auf GENAU die eine Lücke.

    Das Sandbox-IOC bedient jetzt den vollen EVR-Registersatz (567 Sim-Records), den die
    fbis-Displays referenzieren — bis auf ``DlyGen0Prescaler-SP``. Damit ist jeder linked-Record
    entweder generiert, kuratiert oder DIESE Lücke → cf_unregistered == [Lücke] (exakt 1). Das ist
    der „gesunder Spiegel + saubere Lücke"-Beweis (gegen die 645/650-Headline des Spielzeug-IOC).

    Robustheit: erst auf die recsync→CF-Populate warten (billiger ``find_channels``-Poll, 90 s —
    nicht den ~60-s-fbis-Walk pollen), DANN cross-plane EINMAL bei context_cap=256 rechnen.
    """
    _reset_epics_singletons()
    from epics_pv_mcp.config import get_config
    from epics_pv_mcp.services.channelfinder_client import ChannelFinderClient
    from epics_pv_mcp.tools.crossplane import _crossplane_check

    if get_config().channelfinder_max_results < _CF_CAP_MIN:
        pytest.skip(_CF_CAP_SKIP_REASON)

    prefix = "FBIS-DLN01:Ctrl-EVR-01:"

    # 1) Warten, bis der Spiegel in CF angekommen ist: alle bedienten Records aktiv, die Lücke NICHT
    #    registriert. Billiger CF-GET-Poll (~1 s/Iteration), nicht der teure fbis-Walk.
    url = get_config().channelfinder_url or "http://localhost:8080/ChannelFinder"
    client = ChannelFinderClient(url)
    deadline = time.monotonic() + 90.0
    while True:
        channels = client.find_channels(f"{prefix}*", max_results=2000)
        names = {c["name"] for c in channels}
        active = all(c["properties"].get("pvStatus") == "Active" for c in channels)
        # Erwartung: ~576 bediente, alle Active, die Lücke fehlt.
        if len(names) >= 570 and active and _W2_GAP not in names:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(5.0)
    assert _W2_GAP not in names, f"Lücke {_W2_GAP} unerwartet in CF registriert — Spiegel falsch?"
    assert len(names) >= 570, (
        f"nur {len(names)} Kanäle unter {prefix}* (erwartet ~576) — Populate unvollständig? "
        "recceiver-Log (CF_COMMIT) prüfen; bei Diskrepanz longin-/dbd + Boot-Log."
    )

    # 2) Cross-Plane EINMAL gegen das volle fbis rechnen (context_cap EXPLIZIT = Harvest-Cap).
    report = (
        await _crossplane_check(
            str(_FBIS_ROOT),
            str(_SANDBOX_ST_CMD),
            query_channelfinder=True,
            context_cap=_W2_CONTEXT_CAP,
        )
    )["report"]
    assert isinstance(report, dict)
    cf_unregistered = report["cf_unregistered"]
    assert isinstance(cf_unregistered, list)

    # Harter Guard: die Lücke ist IMMER cf_unregistered (referenziert, in linked, nicht bedient).
    assert _W2_GAP in cf_unregistered, (
        f"{_W2_GAP} fehlt in cf_unregistered (len {len(cf_unregistered)}) — CF-Check lief nicht, "
        "war gecappt, oder die Lücke wurde versehentlich bedient."
    )
    # Der Beweis: GENAU die eine Lücke, nichts sonst.
    assert cf_unregistered == [_W2_GAP], (
        f"cf_unregistered != [{_W2_GAP}] (ist {cf_unregistered}) — Spiegel bedient nicht alle "
        "linked-Records (Boot-/Typ-Problem), oder der Cap divergiert vom Harvest."
    )
    # Kein Cap-Withhold, und die Ratio-Caveat-Note (>= 50% unregistriert = unvollständiges CF) ist
    # ABWESEND (1/573 << 50%). Die separate LOWER-BOUND-Note (context-capped) darf vorkommen.
    assert report["cf_capped"] is False
    assert not any(">= 50%" in note for note in report["notes"]), (
        "Ratio-Caveat-Note vorhanden — cf_unregistered ist unerwartet groß (unvollständiges CF?)."
    )


# --- Wedge 4: diagnose_connection gegen die Live-Sandbox (L1–L6) ---------------------------------

# Ein echter Typo (nirgends referenziert/bedient) — auf dem PVA-Name-Server timeoutet er (der
# §Name-Server-Timeout-Collapse), NIE PV_NOT_FOUND (das gäbe es nur bei UDP-Broadcast-Search).
_PV_TYPO = "FBIS-DLN01:Ctrl-EVR-01:NoSuchPV12345"
# Fremd-Prefix = nicht-laufendes IOC → IOC-down SIMULIEREN, ohne das test-ioc zu stoppen (andere
# Live-Tests hängen dran).
_PV_WRONG_PREFIX = "WRONG-DLN99:Ctrl-EVR-01:12VValue"


@pytest.mark.skipif(_NO_SANDBOX, reason=_SKIP_REASON)
async def test_diagnose_l1_served_pv_is_healthy() -> None:
    """L1: eine bediente, verbundene PV → state=connected, likely_cause=healthy (kein Claim)."""
    _reset_epics_singletons()
    from epics_pv_mcp.services.diagnose import diagnose

    report = await diagnose(_PV_ANALOG)
    assert report.state == "connected"
    assert report.likely_cause == "healthy"
    # Ehrlichkeit: keine „einzige Quelle"/Uniqueness-Behauptung.
    joined = " ".join(report.next_steps).lower()
    assert "not uniqueness" in joined or "one responder" in joined


@pytest.mark.skipif(_NO_CF, reason=_SKIP_CF_REASON)
async def test_diagnose_l2_cf_gap_is_not_healthy_or_typo() -> None:
    """L2: der CF-Gap (referenziert, nicht bedient, nicht in CF) → disconnected, nicht healthy/typo.

    CF wird konsultiert und meldet registered=False; ohne lokales Naming kollabiert der Split auf
    ``indeterminate`` (ehrliche Sandbox-Grenze — der unregistered/typo-Split braucht Naming).
    """
    _reset_epics_singletons()
    from epics_pv_mcp.services.diagnose import diagnose

    report = await diagnose(_W2_GAP, timeout=3.0)
    assert report.state == "disconnected"
    assert report.likely_cause not in {"healthy", "name_typo"}
    assert report.likely_cause in {"indeterminate", "unregistered", "ioc_down"}
    assert report.evidence.channelfinder.consulted is True
    assert report.evidence.channelfinder.registered is False


@pytest.mark.skipif(_NO_SANDBOX, reason=_SKIP_REASON)
async def test_diagnose_l3_typo_collapses_to_timeout_not_not_found() -> None:
    """L3 (load-bearing): auf dem Name-Server ist ein Typo PV_TIMEOUT, NIE PV_NOT_FOUND.

    Fixiert den §Name-Server-Timeout-Collapse: der Cause darf nie am Error-Code hängen. Ohne Naming
    (Sandbox) ist der Cause ``indeterminate`` (bzw. ``name_typo``-Kandidat nur MIT Naming).
    """
    _reset_epics_singletons()
    from epics_pv_mcp.services.diagnose import diagnose

    report = await diagnose(_PV_TYPO, timeout=3.0)
    assert report.state == "disconnected"
    assert report.evidence.live.error_code == "PV_TIMEOUT", (
        f"erwartet PV_TIMEOUT auf dem Name-Server, bekam {report.evidence.live.error_code!r} — "
        "der Name-Server-Timeout-Collapse (Typo == toter IOC == Timeout) ist die tragende Annahme."
    )
    assert report.evidence.live.error_code != "PV_NOT_FOUND"
    assert report.likely_cause in {"indeterminate", "name_typo"}


@pytest.mark.skipif(_NO_SANDBOX, reason=_SKIP_REASON)
async def test_diagnose_l4_wrong_prefix_is_disconnected() -> None:
    """L4: ein nicht-laufender Prefix (IOC-down-Simulation) → disconnected, nicht healthy."""
    _reset_epics_singletons()
    from epics_pv_mcp.services.diagnose import diagnose

    report = await diagnose(_PV_WRONG_PREFIX, timeout=3.0)
    assert report.state == "disconnected"
    assert report.likely_cause != "healthy"


@pytest.mark.skipif(_NO_SANDBOX, reason=_SKIP_REASON)
async def test_diagnose_l5_all_planes_off_no_plane_consulted() -> None:
    """L5: bediente PV, alle Planes AUS → healthy, keine Plane konsultiert, kein Withhold."""
    _reset_epics_singletons()
    from epics_pv_mcp.services.diagnose import diagnose

    report = await diagnose(
        _PV_ANALOG,
        check_channelfinder=False,
        check_naming=False,
        check_archiver=False,
        check_alarm=False,
    )
    assert report.state == "connected"
    assert report.likely_cause == "healthy"
    ev = report.evidence
    assert not any(p.consulted for p in (ev.channelfinder, ev.naming, ev.archiver, ev.alarm))
    # withheld = REQUESTED-aber-unerreichbar; nichts requested → nichts withheld.
    assert report.withheld == ()


@pytest.mark.skipif(_NO_SANDBOX, reason=_SKIP_REASON)
async def test_diagnose_l6_cf_disabled_is_indeterminate_anti_overclaim() -> None:
    """L6 (anti-over-claim): der Gap OHNE CF → indeterminate (kein Directory-Signal)."""
    _reset_epics_singletons()
    from epics_pv_mcp.services.diagnose import diagnose

    report = await diagnose(_W2_GAP, timeout=3.0, check_channelfinder=False)
    assert report.state == "disconnected"
    assert report.likely_cause == "indeterminate"
