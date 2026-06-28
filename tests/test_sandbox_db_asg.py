"""Statische ASG-Security-Regression für die Sandbox-`.db` (kein IOC nötig).

Nagelt den Read-only-Vertrag der lokalen e3-Test-Sandbox fest: GENAU die 7 Readbacks tragen
`field(ASG,"private")` (am IOC via QSRV2/PVA write-denied), und GENAU die 2 Schreibziele
(`Temp1ThrUpCrt-SP`, `CmdRst`) tragen es NICHT (ASG DEFAULT = writable). Fällt ein künftiger
`.db`-Edit das `private`-Feld eines Readbacks, schlägt dieser Test fehl — statt einen Readback
still LAN-schreibbar zu machen. `test_write_pattern_matches_exactly_the_default_records` prüft
zusätzlich, dass die MCP-Write-Allowlist (gespiegelt aus `.mcp.json` → `EPICS_MCP_PV_WRITE_PATTERN`)
deckungsgleich mit der ASG-Verteilung ist (Allowlist == DEFAULT/writable-Records, kein Readback).

Die IOC-seitige Durchsetzung (essioc `configuration.acf` → `ASG(private){RULE(1,READ)}`) ist eine
stabile essioc-Eigenschaft; der realistische Drift-Vektor ist unsere eigene `.db` — genau die pinnt
dieser Test im Default-Lane (kein `EPICS_SANDBOX`, kein Netz).
"""

import re
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "sandbox" / "ioc-e3" / "fbis-dln01-evr.db"

# Die geräterelativen Signal-Namen (die `.db` nutzt den `$(P)`-Makro für den Prefix).
_READBACKS_EXPECTED = frozenset(
    {"BMod", "BDest", "DbufBInhSwFBIS-Sts", "Temp1Value", "12VValue", "3V3Value", "EvtACnt-I"}
)
_WRITE_TARGETS_EXPECTED = frozenset({"Temp1ThrUpCrt-SP", "CmdRst"})
_EXPECTED_RECORD_COUNT = 9

# Gespiegelt aus `.mcp.json` → epics-pv.env.EPICS_MCP_PV_WRITE_PATTERN (Workspace-Wurzel).
_WRITE_PATTERN = r"^FBIS-DLN01:Ctrl-EVR-01:(Temp1ThrUpCrt-SP|CmdRst)$"
_PREFIX = "FBIS-DLN01:Ctrl-EVR-01:"

_RECORD_RE = re.compile(r'record\(\s*\w+\s*,\s*"\$\(P\)([^"]+)"')
_ASG_RE = re.compile(r'field\(\s*ASG\s*,\s*"([^"]*)"')


def _record_asg_map() -> dict[str, str | None]:
    """Map Record-Name (`$(P)`-relativ) → ASG-Wert (oder None, wenn kein ASG-Feld)."""
    out: dict[str, str | None] = {}
    current: str | None = None
    for line in _DB_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        record = _RECORD_RE.search(line)
        if record:
            current = record.group(1)
            out.setdefault(current, None)
            continue
        if current is not None:
            asg = _ASG_RE.search(line)
            if asg:
                out[current] = asg.group(1)
            if stripped == "}":
                current = None
    return out


def test_db_has_exactly_nine_records() -> None:
    assert len(_record_asg_map()) == _EXPECTED_RECORD_COUNT


def test_seven_readbacks_are_asg_private() -> None:
    asg = _record_asg_map()
    private = frozenset(name for name, value in asg.items() if value == "private")
    assert private == _READBACKS_EXPECTED


def test_two_write_targets_carry_no_asg() -> None:
    asg = _record_asg_map()
    default = frozenset(name for name, value in asg.items() if value is None)
    assert default == _WRITE_TARGETS_EXPECTED


def test_write_pattern_matches_exactly_the_default_records() -> None:
    # Die Write-Allowlist muss GENAU die ASG-DEFAULT (writable) Records decken und keinen Readback —
    # so bleiben `.db`-ASG-Verteilung und MCP-Pattern deckungsgleich.
    asg = _record_asg_map()
    for name, value in asg.items():
        full_pv = f"{_PREFIX}{name}"
        write_allowed = re.fullmatch(_WRITE_PATTERN, full_pv) is not None
        assert write_allowed == (value is None), (
            f"{name}: write-allowlist={write_allowed} aber ASG={value!r} — divergiert"
        )


def test_write_pattern_rejects_field_suffix_on_a_target() -> None:
    # `re.fullmatch` + `$`-Anker: ein Feld-Suffix (`.VAL`) auf einem Ziel darf NICHT matchen.
    assert re.fullmatch(_WRITE_PATTERN, f"{_PREFIX}Temp1ThrUpCrt-SP.VAL") is None
