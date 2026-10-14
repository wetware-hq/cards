"""C01-C14 traces. Scored only against frozen answer files ($CARDS_TRUTH, $CARDS_WORDING); otherwise
BLOCKED-NO-TRUTH (skip). Ids waiting on a ruling are PENDING-RULING (skip), never pass or fail."""
import pytest
import helpers  # noqa: F401
import traces


@pytest.mark.needs_truth
@pytest.mark.parametrize("cid", list(traces.TRACES))
def test_trace(cid):
    status, diff = traces.score(cid)
    assert status == "PASS", (status, diff)        # never skipped: blocked or pending is a failure here


def test_fourteen_traces_run_deterministically():
    assert len(traces.TRACES) == 15 and "C15" in traces.TRACES
    for cid in traces.TRACES:
        a, b = traces.run(cid), traces.run(cid)
        a.pop("loaded"), b.pop("loaded")
        assert a == b, cid


def test_blocked_without_truth(monkeypatch, tmp_path):
    monkeypatch.delenv("CARDS_TRUTH", raising=False)
    monkeypatch.setattr(traces.paths, "LOCAL", tmp_path / "none.toml")
    assert traces.score("C01") == (traces.BLOCKED, {})


def test_missing_answer_file_fails_when_set(tmp_path):
    assert traces.score("C01", str(tmp_path), str(tmp_path)) == ("FAIL", {"answer_file_missing": "C01"})
    (tmp_path / "C01.toml").write_text('expected_outcome = "pass"\n')
    assert traces.score("C01", str(tmp_path), str(tmp_path)) == ("FAIL", {"answer_file_missing": "C01"})


def test_pending_ruling_never_scored(tmp_path, monkeypatch):
    (tmp_path / "C04.toml").write_text('expected_outcome = "nonsense"\n')
    (tmp_path / "C04").mkdir()
    (tmp_path / "C04" / "patient_wording.md").write_text("")
    monkeypatch.setattr(traces, "PENDING_RULING", {"C04"})
    assert traces.score("C04", str(tmp_path), str(tmp_path)) == (traces.PENDING, {})


def test_unsigned_reference_is_pending(tmp_path):
    (tmp_path / "C04.toml").write_text('expected_lines = ["PV-NOT-SIGNED-YET"]\n')
    (tmp_path / "C04").mkdir()
    (tmp_path / "C04" / "patient_wording.md").write_text("")
    assert traces.score("C04", str(tmp_path), str(tmp_path)) == (traces.PENDING, {"unsigned_or_unsynced": ["PV-NOT-SIGNED-YET"]})


def test_scored_only_against_answer_file(tmp_path):
    p = tmp_path / "C07.toml"
    (tmp_path / "C07").mkdir()
    (tmp_path / "C07" / "patient_wording.md").write_text("")
    p.write_text('expected_outcome = "pass"\nexpected_refusals = ["RF-SOURCE-UPGRADE"]\nexpected_lines = ["SRC-PATIENT-PT"]\n'
                 'raw_ids_in_patient_view = 0\nforbidden_in_patient_view = ["scope"]\nmissing_fact_is = "unknown"\n'
                 'facts_must_carry = ["source_record_id", "recorded_at", "source_kind"]\nupgraded = false\n')
    assert traces.score("C07", str(tmp_path), str(tmp_path)) == ("PASS", {})
    for bad in ('expected_refusals = []\n', 'expected_lines = ["SRC-CLINICIAN-CLIN"]\n', 'upgraded = true\n',
                'missing_fact_is = "none"\n', 'raw_ids_in_patient_view = 2\n', 'expected_open_queue_entries_at_end = 1\n',
                'forbidden_in_patient_view = ["you"]\n', 'facts_must_carry = ["colour"]\n',
                'expected_queue_statuses = ["ST-DECLINED"]\n', 'expected_outcome = "blocked"\n'):
        p.write_text(bad)
        assert traces.score("C07", str(tmp_path), str(tmp_path))[0] == "FAIL", bad


def test_patient_wording_file_scored(tmp_path):
    (tmp_path / "C13.toml").write_text('expected_outcome = "pass"\n')
    (tmp_path / "C13").mkdir()
    w = tmp_path / "C13" / "patient_wording.md"
    w.write_text("## Patient-visible lines (in order)\n1. FD-ALLERGIES-PT: x\n\n## Never shown to the patient\n- x\n")
    assert traces.score("C13", str(tmp_path), str(tmp_path)) == ("PASS", {})
    for bad in ("## Patient-visible lines (in order)\n1. PV-FACT-HIDDEN: x\n",
                "## Never shown to the patient\n- SRC-CLINICIAN-PT \"x\"\n"):
        w.write_text(bad)
        assert traces.score("C13", str(tmp_path), str(tmp_path))[0] == "FAIL", bad
    w.write_text("## Never shown to the patient\n- SRC-CLINICIAN-PT \"x\" for this fact.\n")
    assert traces.score("C13", str(tmp_path), str(tmp_path))[0] == "PASS"


def test_prepush_fails_when_traces_not_run(tmp_path):
    import os, subprocess, sys
    from messages import msg
    root = helpers.ROOT
    envv = {k: v for k, v in os.environ.items() if k not in ("CARDS_TRUTH", "CARDS_WORDING")}
    envv["CARDS_LOCAL"] = str(tmp_path / "absent.toml")
    r = subprocess.run([sys.executable, str(root / "scripts" / "prepush.py"), "a", "b"], capture_output=True,
                       text=True, env=envv, cwd=tmp_path)
    assert r.returncode != 0 and msg("RUN-TRACES-NOT-RUN") in r.stdout
