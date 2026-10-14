#!/usr/bin/env python3
"""Local pre-push check (installed as .git/hooks/pre-push; not run in CI). Fails if WORDING.md differs from what
sync_wording.py makes from the signed files, if rulecheck fails, if the tests fail, or if any tracked file holds an
internal name or a local workspace path.

    python3 scripts/prepush.py CARDS_SIGNED.md REUSED_SIGNED.md
The hook passes the two paths from CARDS_SIGNED and REUSED_SIGNED in its environment."""
import pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sync_wording

FORBIDDEN = [re.compile(p) for p in (r"\bB" + r"IO\b", r"/work" + r"space\b", r"\bheld" + r"out\d", r"patient-" + r"store")]


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / f for f in out.split()]


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    problems = []
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
    if subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT).returncode:
        problems.append("tests failed")
    for x in problems:
        print(x)
    print(f"prepush: {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
