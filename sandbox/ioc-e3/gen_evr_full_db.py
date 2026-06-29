#!/usr/bin/env python3
"""Generiert ``fbis-dln01-evr-full.db`` — den NAMES-treuen mTCA-EVR-300-Spiegel (W2).

Die Sandbox bedient damit den vollen Satz EVR-Register, den die fbis-Displays referenzieren
(Quelle: ``evr-records.txt`` = makro-expandierte ``crossplane_check.pvs_linked``), **bis auf eine
bewusst injizierte Lücke** (``DlyGen0Prescaler-SP``). Danach kollabiert ``cf_unregistered`` gegen
das volle fbis auf genau diese eine Lücke ("gesunder Spiegel + saubere Lücke"-Beweis).

NAMES-treuer **Sim-Spiegel**: Soft-Records mit den echten Record-Namen, VAL=0, **read-only**
(``ASG(private)``), autosave-frei (keine ``info()``-Tags) — KEIN echtes mrfioc2. Die 9 kuratierten
Records leben separat in ``fbis-dln01-evr.db`` (eigene ``dbLoadRecords``-Zeile) und werden hier
ausgeschlossen, weil ein zweiter Record gleichen Namens über zwei ``dbLoadRecords`` ein Boot-Fehler
wäre.

Lauf (im ``EPICS-MCP-Server/``):  ``uv run python sandbox/ioc-e3/gen_evr_full_db.py``
Deterministisch (sortiert, kein time/random) → byte-identische Re-Runs.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from epics_pv_mcp.services.crossplane import _record_name

# Die 9 kuratierten Records (fbis-dln01-evr.db). Ein zweiter Record gleichen Namens über zwei
# dbLoadRecords = Boot-Fehler → alle 9 hier zwingend ausschließen (auch die 4, die gar nicht
# display-referenziert sind und daher nicht in evr-records.txt stehen).
CURATED: frozenset[str] = frozenset(
    {
        "BMod",
        "BDest",
        "DbufBInhSwFBIS-Sts",
        "Temp1Value",
        "12VValue",
        "3V3Value",
        "Temp1ThrUpCrt-SP",
        "EvtACnt-I",
        "CmdRst",
    }
)

# Bewusst injizierte Lücke: dieses display-referenzierte Record bedient der Spiegel NICHT, damit
# cf_unregistered gegen das volle fbis auf genau diesen einen Namen kollabiert (W1/W2-Beweisziel).
GAP = "DlyGen0Prescaler-SP"

# DESC = 28 Zeichen (< 40, das DESC-Feldlimit).
_DESC = "sim EVR register (W2 mirror)"

_HEADER = (
    "# fbis-dln01-evr-full.db — GENERIERT von gen_evr_full_db.py, NICHT von Hand editieren\n"
    "# (regenerieren: uv run python sandbox/ioc-e3/gen_evr_full_db.py).\n"
    "# NAMES-treuer Sim-Spiegel des mTCA-EVR-300: Soft-Records mit den echten Record-Namen,\n"
    "# die die fbis-Displays referenzieren (Quelle: evr-records.txt). VAL=0, read-only\n"
    "# (ASG private), autosave-frei (ohne autosaveFields-Tags). ASG(private) liefert essioc\n"
    "# common_config.iocsh (access-security) — live bewiesen an den kuratierten Readbacks.\n"
    f"# Bewusst injizierte Lücke (NICHT bedient): {GAP} — cf_unregistered kollabiert darauf.\n"
    "# Die 9 kuratierten Records liegen separat in fbis-dln01-evr.db (eigene Lade-Zeile).\n"
)


def _record_type(suffix: str) -> str:
    """Deterministische, totale Typ-Heuristik (alle boot-bewiesen; KEIN mbbi/calc/longout).

    Die Schlüssel sind paarweise kein Suffix voneinander → die Zweig-Reihenfolge ist irrelevant;
    ``else``=``ai`` ist der Catch-all, jedes Suffix trifft genau einen Zweig.
    """
    if suffix.endswith("-SP"):
        return "ao"
    if suffix.endswith("-Cmd"):
        return "bo"
    if suffix.endswith("-Sts"):
        return "bi"
    if suffix.endswith("-I"):
        return "longin"
    return "ai"


def _record_block(suffix: str) -> str:
    """Ein .db-Record-Block für *suffix* — mehrzeilig (Source ≤100), ``$(P)``-makro-relativ.

    VAL=0 + PINI=YES (deterministischer Wert beim Boot), ASG(private) = read-only, KEINE
    ``info()``-Tags (sonst zieht ESS-Autosave sie ein).
    """
    rtype = _record_type(suffix)
    return (
        f'record({rtype}, "$(P){suffix}") {{\n'
        f'    field(DESC, "{_DESC}")\n'
        '    field(VAL,  "0")\n'
        '    field(PINI, "YES")\n'
        '    field(ASG,  "private")\n'
        "}\n"
    )


def build_db_text(suffixes: list[str], *, curated: set[str], gap: str) -> str:
    """Baue den .db-Text aus *suffixes*, ohne *curated* (Doppel-Record) und *gap* (die Lücke).

    Rein + deterministisch: gleiche (sortierte) Eingabe → byte-gleiche Ausgabe. Anti-Drift: jedes
    Suffix muss bereits feld-suffix-normalisiert sein (``_record_name`` idempotent) — sonst bricht
    der Generator laut, statt still einen ``.FIELD``-Record zu erzeugen.
    """
    excluded = set(curated) | {gap}
    blocks: list[str] = []
    for suffix in suffixes:
        if _record_name(suffix) != suffix:
            raise ValueError(f"Suffix nicht feld-normalisiert (Grammatik-Drift?): {suffix!r}")
        if suffix in excluded:
            continue
        blocks.append(_record_block(suffix))
    return _HEADER + "\n" + "\n".join(blocks)


def _read_suffixes(records_file: Path) -> list[str]:
    """Lies ``evr-records.txt``: nicht-leere, nicht-``#``-Zeilen → sortierte, deduplizierte Liste.

    ``sorted(set(...))`` ist die EINZIGE Nichtdeterminismus-Senke → hier zentral fixiert, damit
    ``build_db_text`` eine bereits sortierte Liste bekommt.
    """
    lines = records_file.read_text(encoding="utf-8").splitlines()
    names = {line.strip() for line in lines if line.strip() and not line.startswith("#")}
    return sorted(names)


def generate(directory: Path) -> int:
    """Lies ``evr-records.txt`` aus *directory*, schreibe ``fbis-dln01-evr-full.db`` (LF) dorthin.

    Gibt die Zahl der generierten Records zurück. Reine Datei-Operation (kein stdout-Encoding-Setup
    — das macht ``main`` für die Konsole) → der Pfad ist gegen ein tmp-Verzeichnis testbar.
    """
    suffixes = _read_suffixes(directory / "evr-records.txt")
    if GAP not in suffixes:
        raise ValueError(
            f"Lücke {GAP!r} fehlt in evr-records.txt — sie wäre dann nicht display-referenziert "
            f"und cf_unregistered könnte nicht auf sie kollabieren."
        )
    text = build_db_text(suffixes, curated=set(CURATED), gap=GAP)
    out = directory / "fbis-dln01-evr-full.db"
    # LF erzwingen (Windows-Default newline=None machte CRLF); die kuratierte .db ist LF-only.
    out.write_text(text, encoding="utf-8", newline="\n")
    curated_overlap = len(set(suffixes) & CURATED)
    generated = len(suffixes) - curated_overlap - 1
    sys.stdout.write(
        f"{out.name}: {generated} Records generiert "
        f"(von {len(suffixes)} distinct - {curated_overlap} kuratiert - 1 Lücke)\n"
    )
    return generated


def main() -> int:
    # Unter Windows ist die Konsole cp1252 → die deutsche Statuszeile (Umlaut in „Lücke") bräche
    # sonst mit UnicodeEncodeError. UTF-8 erzwingen, wo stdout ein echter TextIOWrapper ist (unter
    # pytest-Capture/Pipe greift der Guard nicht — dort ist stdout ohnehin UTF-8-fähig).
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    generate(Path(__file__).resolve().parent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
