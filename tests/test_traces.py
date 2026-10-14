"""C01-C14 traces. Scored only against frozen answer files ($CARDS_TRUTH, $CARDS_WORDING); otherwise
BLOCKED-NO-TRUTH (skip). Ids waiting on a ruling are PENDING-RULING (skip), never pass or fail."""
import pytest
import helpers  # noqa: F401
import traces


@pytest.mark.parametrize("cid", list(traces.TRACES))
def test_trace(cid):
    status, diff = traces.score(cid)
    if status in (traces.BLOCKED, traces.PENDING):
        pytest.skip(status)
    assert status == "PASS", diff


def test_fourteen_traces_run_deterministically():
    assert len(traces.TRACES) == 14
    for cid in traces.TRACES:
        a, b = traces.run(cid), traces.run(cid)
        a.pop("loaded"), b.pop("loaded")
        assert a == b, cid


def test_blocked_without_truth(tmp_path):
    assert traces.score("C01", str(tmp_path)) == (traces.BLOCKED, {})


def test_pending_ruling_never_scored(tmp_path):
    (tmp_path / "C04.toml").write_text('expected_outcome = "nonsense"\n')
    assert traces.score("C04", str(tmp_path)) == (traces.PENDING, {})


def test_scored_only_against_answer_file(tmp_path):
    p = tmp_path / "C07.toml"
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
