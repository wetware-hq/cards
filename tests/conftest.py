"""Seeded shuffle of test order: set TEST_SEED to an int to shuffle (standard library only). Without the answer-file
setting the trace tests are not run and RUN-TRACES-NOT-RUN is printed; that run never counts as a pass of the bar."""
import os, pathlib, random, sys
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import paths  # noqa: E402
from messages import msg  # noqa: E402

NEEDS_TRUTH = "needs_truth"
NEEDS_SIGNED = "needs_signed"


def pytest_configure(config):
    config.addinivalue_line("markers", f"{NEEDS_TRUTH}: runs only with the answer-file setting present")
    config.addinivalue_line("markers", f"{NEEDS_SIGNED}: runs only with CARDS_SIGNED and REUSED_SIGNED set")


def pytest_collection_modifyitems(config, items):
    seed = os.environ.get("TEST_SEED")
    if seed is not None:
        random.Random(int(seed)).shuffle(items)
    if not paths.traces_set():
        drop = [i for i in items if i.get_closest_marker(NEEDS_TRUTH)]
        items[:] = [i for i in items if not i.get_closest_marker(NEEDS_TRUTH)]
        config.hook.pytest_deselected(items=drop)
    if not paths.signed_set() or not paths.wording_dirs():
        drop = [i for i in items if i.get_closest_marker(NEEDS_SIGNED)]
        items[:] = [i for i in items if not i.get_closest_marker(NEEDS_SIGNED)]
        config.hook.pytest_deselected(items=drop)


def pytest_terminal_summary(terminalreporter):
    if not paths.traces_set():
        terminalreporter.write_line(msg("RUN-TRACES-NOT-RUN"))


@pytest.fixture(autouse=True)
def _scenario_clock():
    """Every cards test runs on an explicit clock: test mode (tests of the unset or real modes change it).
    Its own MonkeyPatch, so a test calling monkeypatch.undo() keeps the explicit clock."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CARDS_CLOCK", "test")
        yield
