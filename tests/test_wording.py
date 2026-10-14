"""WORDING.md is the only wording source. These checks need no access to the signed files."""
import ast, hashlib, pathlib, re, subprocess, sys
import helpers  # noqa: F401
import messages

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEXT = (ROOT / "WORDING.md").read_text()
sys.path.insert(0, str(ROOT / "scripts"))
import sync_wording


def test_wording_matches_its_header_hash():
    head, body = TEXT.split("\n\n", 1)
    assert re.search(r"^sha256: ([0-9a-f]{64})$", head, re.M).group(1) == hashlib.sha256(body.encode()).hexdigest()
    assert messages.SHA256 == hashlib.sha256(body.encode()).hexdigest()
    assert set(messages.LINES) == sync_wording.SIGNED_IDS | set(sync_wording.REUSED)


def test_used_ids_are_signed():
    for p in ROOT.glob("*.py"):
        for n in ast.walk(ast.parse(p.read_text())):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and re.fullmatch(r"(FD|SRC|VAL|FL|CQ|PV|RF|ST|REL)-[A-Z0-9-]*[A-Z0-9]", n.value):
                assert n.value in messages.LINES or n.value == "RF-NOT-YOURS", (p.name, n.value)


def test_agent_name_only_in_one_line():
    own = [k for k, v in messages.LINES.items() if "[agent_name]" in v and k in sync_wording.SIGNED_IDS]
    assert own == ["PV-DRAFT-NOT-SENT"]
    assert "[display name]" not in TEXT


def _signed():
    rows = "\n".join(f"| {k} | patient | x |" for k in sorted(sync_wording.SIGNED_IDS))
    reused = "\n".join(f"| {k} | y |" for k in sync_wording.REUSED)
    return rows, reused


def test_sync_refuses_wrong_count_before_hashing(monkeypatch):
    rows, reused = _signed()
    calls = []
    real = hashlib.sha256
    monkeypatch.setattr(sync_wording.hashlib, "sha256", lambda *a: calls.append(a) or real(*a))
    assert sync_wording.render(rows, reused).count("| x |") == 49 and calls
    calls.clear()
    lines = rows.splitlines()
    for bad in ("\n".join(lines[:-1]), rows + "\n" + lines[0], rows.replace("RF-SESSION-ENDED", "RF-SESSION-END"),
                rows + "\n| RF-EXTRA | session | z |"):
        try:
            sync_wording.render(bad, reused)
            raise AssertionError("not refused")
        except sync_wording.Mismatch:
            pass
    try:
        sync_wording.render(rows, reused.replace("RF-REVOKED", "RF-GONE"))
        raise AssertionError("not refused")
    except sync_wording.Mismatch:
        pass
    assert calls == []


def test_synthetic_only():
    for p in list(ROOT.glob("examples/*.toml")):
        t = p.read_text()
        assert all(re.match(r"SYNTH-", m) for m in re.findall(r'"([A-Z]+-[A-Z]+-\d+)"', t)), p
        assert all(d.startswith("193") for d in re.findall(r'"(\d{4})-\d\d-\d\d"', t)), p


def test_no_coded_content():
    bad = re.compile(r"\b(WHO|SNOMED|AMT|ICD-?\d+)\b")
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    files = [ROOT / f for f in out] or [p for d in ("", "scripts", "tests", "examples") for p in (ROOT / d).glob("*.*")]
    for p in files:
        if p.suffix in (".py", ".md", ".toml") and p.name != "test_wording.py":
            assert not bad.search(p.read_text()), p
