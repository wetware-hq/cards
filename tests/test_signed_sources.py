"""Every signed line is checked against its one current signed source file, never against a copy of itself
(room ruling 15 Oct 10:18): (a) a guard on the signed-content tests, (b) the scorer's lines, (c) clean-run traces."""
import ast, pathlib, re
import pytest
import helpers  # noqa: F401
import sys
import paths, signing, traces
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import sync_wording  # noqa: E402
from messages import LINES

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = pathlib.Path(__file__).resolve().parent
SOURCE_CALLS = {"signed_rows", "reused_signed", "wording_dirs"}            # how a test reaches a signed source
SOURCE_KEYS = {"CARDS_SIGNED", "REUSED_SIGNED"}
CONTENT_NAME = re.compile(r"signed|exact|word_for_word|copied")
# ids-only checks (not line content): they read WORDING.md, which test_scorer_lines_* checks byte-exact against the
# signed sources, so no content is ever checked against itself.
IDS_ONLY = {"test_used_ids_are_signed", "test_every_raised_id_is_a_signed_row", "test_no_line_id_signed_in_more_than_one_file",
            "test_signing_file_row_counts_match_committed_numbers",
            "test_unsigned_reference_is_pending",                       # an unsigned id is held, no line text
            "test_signed_content_tests_take_expected_from_signed_source",  # the guard itself
            "test_guard_catches_a_test_checking_a_file_against_itself"}


def signed_rows():
    """{id: (bytes of the signed line, signing file stem)}: own rows from the cards signed file, reused rows from
    the one file they are reused from."""
    own, reused = paths.root("CARDS_SIGNED"), paths.root("REUSED_SIGNED")
    out = {k: (v, own.name) for k, v in signing.rows(own.read_text()).items()}
    src = signing.rows(reused.read_text())
    out.update({k: (src[k], reused.name) for k in sync_wording.REUSED if k in src})
    return out


def _reaches_source(fn):
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and n.id in SOURCE_CALLS | {"signed_rows"}:
            return True
        if isinstance(n, ast.Attribute) and n.attr in SOURCE_CALLS:
            return True
        if isinstance(n, ast.Constant) and n.value in SOURCE_KEYS:
            return True
    return False


def _content_tests():
    for f in sorted(TESTS.glob("test_*.py")):
        for n in ast.parse(f.read_text()).body:
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_") and CONTENT_NAME.search(n.name):
                yield f.name, n


def guard_problems(tests):
    return [f"{f}::{n.name}" for f, n in tests if n.name not in IDS_ONLY and not _reaches_source(n)]


def test_signed_content_tests_take_expected_from_signed_source():
    found = list(_content_tests())
    assert len(found) >= 4 and guard_problems(found) == []


def test_guard_catches_a_test_checking_a_file_against_itself():
    bad = ast.parse("def test_reused_lines_exact():\n    assert LINES['RF-REVOKED'] == open('WORDING.md').read()\n").body[0]
    good = ast.parse("def test_reused_lines_exact():\n    assert LINES['RF-REVOKED'] == signed_rows()['RF-REVOKED'][0]\n").body[0]
    assert guard_problems([("x.py", bad)]) == ["x.py::test_reused_lines_exact"]
    assert guard_problems([("x.py", good)]) == []


@pytest.mark.needs_signed
def test_scorer_lines_come_from_their_current_single_signed_source():
    rows, where = signed_rows(), signing.sources(paths.wording_dirs())
    own, reused = paths.root("CARDS_SIGNED").name, paths.root("REUSED_SIGNED").name
    stem = lambda name: signing.FILE.match(name).group(1)
    for k, text in LINES.items():                                  # every line the scorer resolves (traces._pattern)
        assert k in rows, f"{k}: not in its signed source"
        assert text == rows[k][0], f"{k}: differs from {rows[k][1]}"   # byte-exact
        assert where.get(k) == [stem(rows[k][1])], f"{k}: signed in {where.get(k)}"
        assert rows[k][1] == (reused if k in sync_wording.REUSED else own), k


@pytest.mark.needs_signed
@pytest.mark.parametrize("cid", list(traces.TRACES))
def test_clean_run_every_emitted_signed_line_matches_its_source(cid):
    rows = signed_rows()
    pats = {k: signing.pattern(v) for k, (v, _) in rows.items()}
    copy = {k: signing.pattern(v) for k, v in LINES.items()}
    got = traces.run(cid)
    emitted = [t for t in got["view"] + got["outputs"] + got["clinician_queue"] if isinstance(t, str) and t]
    checked = 0
    for t in emitted:
        ids = [k for k, rx in copy.items() if rx.match(t)]
        for k in ids:
            checked += 1
            assert pats[k].match(t), f"{cid}: {k} emitted as {t!r}, not its signed line"
    for t in got["clinician_queue"]:                                 # every clinician line is a signed line
        assert any(rx.match(t) for rx in pats.values()), f"{cid}: unsigned clinician line {t!r}"
    assert checked, cid


@pytest.mark.needs_signed
def test_clean_run_check_catches_a_changed_line(monkeypatch):
    rows = signed_rows()
    k = next(k for k in rows if not re.search(r"\[", rows[k][0]))
    assert not signing.pattern(rows[k][0]).match(rows[k][0] + " ")    # one extra byte fails
