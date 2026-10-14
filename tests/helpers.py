"""Synthetic fixtures shared by the tests."""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import cards

PATIENT = (ROOT / "examples" / "patient.toml").read_text()
PROVIDER = (ROOT / "examples" / "provider.toml").read_text()
REGISTRY = {"SYNTH-REG-0001": {"body": "SYNTH-BOARD", "status": "current", "discipline": "medicine",
                               "scope": ["read", "check", "draft"]}}


def records(**over):
    r = {f"SYNTH-REC-000{i}": {"recorded": "1937-01-04", "value": v, "discipline": "medicine"}
         for i, v in enumerate(["penicillin", "synthmed_a", "low_mood", "home_care"], 1)}
    r.update(over)
    return r


def env(**over):
    return cards.Env(REGISTRY, records(**over), now="1937-02-01")


def agent(e, text=PATIENT, grant="SYNTH-GR-0001", aid="SYNTH-AG-0001"):
    s = e.session("agent", aid, grant)
    s.open(text)
    return s


def patient(e, text=PATIENT):
    s = e.session("patient", "SYNTH-P0101")
    s.open(text)
    return s


def drop_fact(text, field):
    """Remove one [[fact]] block by field name."""
    blocks = text.split("[[fact]]")
    keep = [b for b in blocks[1:] if f'field = "{field}"' not in b]
    return "[[fact]]".join([blocks[0]] + keep)
