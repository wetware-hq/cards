"""One approved clock (clock.today), as figures 4112225. Mode set explicitly by CARDS_CLOCK: 'test' gives the scenario
clock, 'real' the real clock; unset refuses with RF-CLOCK-UNSET (staff-only) and nothing changes. The grant expires_at
check takes its time from it. No other cards code reads the box clock."""
import pathlib, re
import pytest
import cards, clock
from messages import msg

HERE = pathlib.Path(__file__).resolve().parent.parent
C13 = (HERE / "examples" / "S13-C13.toml").read_text()
BOX = re.compile(r"\b(datetime\.(now|utcnow|today)|date\.today|time\.(time|time_ns|localtime|gmtime|strftime|monotonic|perf_counter))\b")


def test_test_mode_gives_the_scenario_clock(monkeypatch):
    monkeypatch.setenv("CARDS_CLOCK", "test")
    assert clock.today("1936-03-09") == "1936-03-09"
    assert cards.Env(now="1936-03-09").now == "1936-03-09"


def test_expiry_check_uses_the_scenario_clock(monkeypatch):
    monkeypatch.setenv("CARDS_CLOCK", "test")
    for now, line in (("1936-02-28", None), ("1936-03-09", "RF-GRANT-ENDED")):
        env = cards.Env(now=now)
        s = env.session("decision_maker", "SYNTH-PERSON-G13E", "SYNTH-GR-1302")
        if line is None:
            s.open(C13)
        else:
            with pytest.raises(cards.Refused) as e:
                s.open(C13)
            assert e.value.line_id == line


@pytest.mark.parametrize("mode", [None, "", "scenario", "TEST"])
def test_unset_clock_refuses_and_nothing_changes(monkeypatch, mode):
    if mode is None:
        monkeypatch.delenv("CARDS_CLOCK", raising=False)
    else:
        monkeypatch.setenv("CARDS_CLOCK", mode)
    env = cards.Env(now="1936-03-09")
    s = env.session("decision_maker", "SYNTH-PERSON-G13", "SYNTH-GR-1301")
    with pytest.raises(clock.ClockUnset) as e:
        s.open(C13)
    assert e.value.line_id == "RF-CLOCK-UNSET" and e.value.text == msg("RF-CLOCK-UNSET")
    assert s.card is None and env.log == [] and env.queue == []


def test_real_mode_never_gives_a_1930s_date(monkeypatch):
    monkeypatch.setenv("CARDS_CLOCK", "real")
    assert not clock.today("1936-03-09").startswith("193")


def test_clock_unset_is_staff_only_never_a_patient_line():
    assert not msg("RF-CLOCK-UNSET").startswith("Your") and "RF-CLOCK-UNSET" not in cards.SIGN_ONLY.values()
    src = (HERE / "cards.py").read_text()
    assert "RF-CLOCK-UNSET" not in src                       # never put into a view; only clock.py raises it


def test_no_code_outside_clock_py_reads_the_box_clock():
    bad = []
    for p in HERE.rglob("*.py"):
        rel = p.relative_to(HERE).as_posix()
        if "__pycache__" in rel or rel == "clock.py" or p.name.startswith("test_"):
            continue
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if BOX.search(line.split("#")[0]):
                bad.append(f"{rel}:{n}")
    assert bad == [], bad
