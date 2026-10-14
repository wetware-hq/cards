"""Loads user-facing text from WORDING.md; no wording is written here. Every line is keyed by its wording-table id.
Text in [ ] is filled only from typed card fields or signed rows, never from free text or raw ids."""
import pathlib, re

WORDING = pathlib.Path(__file__).resolve().parent / "WORDING.md"
_TEXT = WORDING.read_text()
_BODY = _TEXT.split("\n\n", 1)[1]
SHA256 = re.search(r"^sha256: ([0-9a-f]{64})$", _TEXT, re.M).group(1)
LINES = dict(re.findall(r"^\| ([A-Z]{2,4}-[A-Z0-9-]+) \| ([^|]*?) \|$", _BODY, re.M))
PENDING = {}
SLOT = re.compile(r"\[([^\]]+)\]")
KEY = {"field label": "label", "date": "date", "source": "source", "discipline": "discipline",
       "registration body": "body", "registration status": "status", "agent_name": "agent_name",
       "person_name": "person_name", "value": "value", "record_id": "record_id", "REL-*-PT": "rel", "REL-*-CLIN": "rel"}


def msg(line_id, **f):
    return SLOT.sub(lambda m: str(f[KEY[m.group(1)]]), LINES[line_id])


def code(name):
    return "ERR:" + name
