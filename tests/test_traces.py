"""C01-C14 traces. A trace counts only against a frozen answer file; otherwise it is BLOCKED-NO-TRUTH (skip)."""
import pytest
import helpers  # noqa: F401
import traces


@pytest.mark.parametrize("cid", list(traces.TRACES))
def test_trace(cid):
    status, diff = traces.score(cid)
    if status == traces.BLOCKED:
        pytest.skip(traces.BLOCKED)
    assert status == "PASS", diff


def test_fourteen_traces_run_deterministically():
    assert len(traces.TRACES) == 14
    for cid, fn in traces.TRACES.items():
        assert fn() == fn(), cid


def test_blocked_without_truth(tmp_path):
    assert traces.score("C01", str(tmp_path)) == (traces.BLOCKED, {})


def test_scored_only_against_answer_file(tmp_path):
    (tmp_path / "C07").mkdir()
    (tmp_path / "C07" / "truth.toml").write_text('[expect]\nupgrade = "RF-SOURCE-UPGRADE"\n')
    assert traces.score("C07", str(tmp_path)) == ("PASS", {})
    (tmp_path / "C07" / "truth.toml").write_text('[expect]\nupgrade = "nope"\n')
    assert traces.score("C07", str(tmp_path))[0] == "FAIL"
    (tmp_path / "C07" / "truth.toml").write_text('[expect]\n')
    assert traces.score("C07", str(tmp_path))[0] == "FAIL"
