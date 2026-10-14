#!/usr/bin/env python3
"""Local pre-push check (installed as .git/hooks/pre-push; not run in CI). Fails if WORDING.md differs from what
sync_wording.py makes from the signed files, if rulecheck fails, if the tests fail, or if any tracked file holds an
internal name or a local workspace path.

    python3 scripts/prepush.py CARDS_SIGNED.md REUSED_SIGNED.md
The hook passes the two paths from CARDS_SIGNED and REUSED_SIGNED in its environment."""
import os, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sync_wording
sys.path.insert(0, str(ROOT))
import paths
from messages import msg

ANSWER = re.compile(r"C\d\d\.toml(\.bak\d*)?")
FORBIDDEN = [re.compile(p) for p in (r"\bB" + r"IO\b", r"/work" + r"space\b", r"\bheld" + r"out\d", r"patient-" + r"store")]


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / f for f in out.split()]


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    if not paths.traces_set():                   # the safety bar can't pass without the traces
        print(msg("RUN-TRACES-NOT-RUN"))
        return 1
    problems = []
    import mutation_hash
    if not mutation_hash.fresh():
        problems.append(mutation_hash.STALE)
    truth = {p.name for p in paths.root("CARDS_TRUTH").iterdir()} | {"patient_wording.md"}
    for p in tracked():
        if p.name in truth or ANSWER.fullmatch(p.name):
            problems.append(f"{p.relative_to(ROOT)}: answer file in the commit")
    try:
        want = sync_wording.render(pathlib.Path(argv[1]).read_text(), pathlib.Path(argv[2]).read_text())
        if (ROOT / "WORDING.md").read_text() != want:
            problems.append("WORDING.md differs from the signed files: run scripts/sync_wording.py")
    except sync_wording.Mismatch as e:
        problems.append(f"signed file: {e}")
    for p in tracked():
        try:
            text = p.read_text()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for rx in FORBIDDEN:
            for m in rx.finditer(text):
                problems.append(f"{p.relative_to(ROOT)}:{text.count(chr(10), 0, m.start()) + 1}: internal name or path")
    if subprocess.run([sys.executable, "scripts/rulecheck.py"], cwd=ROOT).returncode:
        problems.append("rulecheck failed")
    if not paths.wording_dirs():
        problems.append("WORDING_DIRS not set: the signing files can't be checked")
    env = dict(os.environ, CARDS_SIGNED=str(pathlib.Path(argv[1]).resolve()),
               REUSED_SIGNED=str(pathlib.Path(argv[2]).resolve()))
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                       capture_output=True, text=True, env=env)
    print(r.stdout[-2000:])
    if r.returncode:
        problems.append("tests failed")
    if re.search(r"\d+ (skipped|deselected|xfailed)", r.stdout) or msg("RUN-TRACES-NOT-RUN") in r.stdout:
        problems.append("tests skipped or traces not run")
    for x in problems:
        print(x)
    print(f"prepush: {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
