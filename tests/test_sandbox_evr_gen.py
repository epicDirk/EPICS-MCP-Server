"""Unit-Test für den W2-EVR-Spiegel-Generator (``sandbox/ioc-e3/gen_evr_full_db.py``).

Prüft RELATIONEN, nicht die Zahl 567 (die ist eine context-cap-Untergrenze, vom Inventar
getrieben): kuratierte Records + Lücke ausgeschlossen, keine Doppel-Records, totale Typ-
Heuristik, kein ``info()``-Tag, reine LF-Ausgabe, und dass ``generate`` determiniert
(byte-identische ``.db``) + sortiert. Lädt den standalone-Generator per ``importlib``
(``sandbox/`` ist kein Package); ``mypy --strict`` verlangt die ``spec``/``spec.loader``-
Asserts. Ein Regressionstest pinnt, dass die committete ``fbis-dln01-evr-full.db`` eine
treue, aktuelle Generierung aus ``evr-records.txt`` ist.
"""

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

_SANDBOX = Path(__file__).resolve().parent.parent / "sandbox" / "ioc-e3"
_GEN_PATH = _SANDBOX / "gen_evr_full_db.py"
_RECORDS_PATH = _SANDBOX / "evr-records.txt"
_FULL_DB_PATH = _SANDBOX / "fbis-dln01-evr-full.db"

# Eine Record-Kopfzeile: record(<typ>, "$(P)<name>") {
_RECORD_RE = re.compile(r'^record\((\w+), "\$\(P\)([^"]+)"\) \{$')


def _load_gen() -> ModuleType:
    """Lade den standalone-Generator als Modul (sandbox/ ist kein Package)."""
    spec = importlib.util.spec_from_file_location("gen_evr_full_db", _GEN_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_gen = _load_gen()


def _records(db_text: str) -> list[tuple[str, str]]:
    """Parse die Record-Köpfe → Liste von (Typ, Record-Name) in Datei-Reihenfolge."""
    out: list[tuple[str, str]] = []
    for line in db_text.splitlines():
        match = _RECORD_RE.match(line)
        if match:
            out.append((match.group(1), match.group(2)))
    return out


def test_desc_within_record_field_limit() -> None:
    assert len(_gen._DESC) <= 40


def test_read_suffixes_sorts_dedups_and_skips_comments(tmp_path: Path) -> None:
    """``_read_suffixes`` ist die einzige Nichtdeterminismus-Senke: sortiert + dedupliziert, und
    überspringt ``#``-Kommentar- sowie Leerzeilen."""
    records = tmp_path / "evr-records.txt"
    records.write_text(
        "# Header-Kommentar\n\nGgg-RB\nAaa-SP\nGgg-RB\n  Bbb-Cmd  \n# noch ein Kommentar\n",
        encoding="utf-8",
    )
    result = _gen._read_suffixes(records)
    assert result == ["Aaa-SP", "Bbb-Cmd", "Ggg-RB"]  # sortiert, dedupliziert, getrimmt, ohne #


def test_record_type_heuristic_is_total_and_correct() -> None:
    """Jedes Suffix trifft genau einen Zweig; else=ai ist der Catch-all."""
    assert _gen._record_type("DlyGen0Delay-SP") == "ao"
    assert _gen._record_type("Foo-Cmd") == "bo"
    assert _gen._record_type("Bar-Sts") == "bi"
    assert _gen._record_type("Baz-I") == "longin"
    assert _gen._record_type("Qux-RB") == "ai"
    assert _gen._record_type("Quux-Sel") == "ai"
    assert _gen._record_type("PlainName") == "ai"  # Catch-all


def test_build_db_text_excludes_curated_and_gap_and_is_well_formed() -> None:
    """RELATIONEN auf einer synthetischen Eingabe: kuratierte + Lücke raus, kein Dup, jeder Record
    trägt DESC/VAL/PINI/ASG(private), Typ-Heuristik je Suffix, kein ``info(``, reine LF."""
    curated = {"12VValue", "Temp1ThrUpCrt-SP"}  # zwei der 9 kuratierten
    gap = "DlyGen0Prescaler-SP"
    suffixes = sorted(
        {
            "12VValue",  # kuratiert → raus
            "Temp1ThrUpCrt-SP",  # kuratiert → raus
            gap,  # Lücke → raus
            "DlyGen0Delay-SP",  # ao
            "Reset-Cmd",  # bo
            "Link-Sts",  # bi
            "Count-I",  # longin
            "Level-RB",  # ai
            "Mode-Sel",  # ai
        }
    )
    text = _gen.build_db_text(suffixes, curated=curated, gap=gap)
    recs = _records(text)
    names = [name for _, name in recs]

    assert set(names).isdisjoint(curated)  # kuratierte ausgeschlossen
    assert gap not in names  # Lücke ausgeschlossen
    assert len(names) == len(set(names))  # keine Doppel-Records
    assert names == sorted(names)  # Reihenfolge = Eingabe-Sortierung (deterministisch)
    assert "info(" not in text  # autosave-frei
    assert "\r" not in text  # reine LF
    # jeder erwartete Record ist vorhanden + typ-korrekt
    type_by_name = dict((name, rtype) for rtype, name in recs)
    assert type_by_name == {
        "DlyGen0Delay-SP": "ao",
        "Reset-Cmd": "bo",
        "Link-Sts": "bi",
        "Count-I": "longin",
        "Level-RB": "ai",
        "Mode-Sel": "ai",
    }
    # jeder Record-Block trägt genau DESC/VAL/PINI/ASG(private)
    assert text.count('field(ASG,  "private")') == len(recs)
    assert text.count('field(VAL,  "0")') == len(recs)
    assert text.count('field(PINI, "YES")') == len(recs)
    assert text.count(f'field(DESC, "{_gen._DESC}")') == len(recs)


def test_build_db_text_is_deterministic() -> None:
    suffixes = sorted({"A-SP", "B-Cmd", "C-Sts", "D-I", "E-RB"})
    first = _gen.build_db_text(suffixes, curated=set(), gap="X-SP")
    second = _gen.build_db_text(suffixes, curated=set(), gap="X-SP")
    assert first == second


def test_build_db_text_rejects_unnormalized_suffix() -> None:
    """Anti-Drift: ein Feld-Suffix (`.VAL`) ist nicht ``_record_name``-idempotent → laut."""
    with pytest.raises(ValueError, match="feld-normalisiert"):
        _gen.build_db_text(["Foo-SP.VAL"], curated=set(), gap="X")


def test_generate_is_deterministic_and_writes_lf(tmp_path: Path) -> None:
    """Der echte ``generate``-Datei-Pfad (nicht nur ``build_db_text``): zweimal in ein tmp-Dir
    → byte-identisch, reine LF. Fängt einen unsortierten ``set()``-Pfad in ``generate``."""
    (tmp_path / "evr-records.txt").write_text(
        _RECORDS_PATH.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    out = tmp_path / "fbis-dln01-evr-full.db"

    _gen.generate(tmp_path)
    first = out.read_bytes()
    _gen.generate(tmp_path)
    second = out.read_bytes()

    assert first == second  # byte-identisch über zwei Läufe
    assert b"\r" not in first  # reine LF (kein Windows-CRLF)


def test_generate_requires_the_gap_in_records(tmp_path: Path) -> None:
    """Fehlt die Lücke in evr-records.txt → ``generate`` bricht (sie wäre nicht referenziert)."""
    (tmp_path / "evr-records.txt").write_text("Foo-SP\nBar-I\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="fehlt in evr-records"):
        _gen.generate(tmp_path)


def test_committed_full_db_matches_generator() -> None:
    """Regression: die committete ``fbis-dln01-evr-full.db`` ist eine treue, AKTUELLE
    Generierung aus ``evr-records.txt`` — fängt „.txt editiert, .db nicht regeneriert"."""
    suffixes = _gen._read_suffixes(_RECORDS_PATH)
    expected = _gen.build_db_text(suffixes, curated=set(_gen.CURATED), gap=_gen.GAP)
    assert _FULL_DB_PATH.read_bytes() == expected.encode("utf-8")


def test_committed_full_db_excludes_all_nine_curated_and_gap() -> None:
    """Kein kuratierter Name (auch nicht die 4 nicht-display-referenzierten) und nicht die Lücke
    landen in der vollen ``.db`` — sonst Doppel-Record-Boot-Fehler bzw. keine saubere Lücke."""
    names = {name for _, name in _records(_FULL_DB_PATH.read_text(encoding="utf-8"))}
    assert names.isdisjoint(_gen.CURATED)
    assert _gen.GAP not in names
