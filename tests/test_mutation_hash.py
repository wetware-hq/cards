"""The mutation hash covers the bodies of the listed safety functions, not only safety_functions.toml."""
import shutil, sys
from helpers import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import mutation_hash  # noqa: E402


def _copy(tmp_path):
    for f in ("safety_functions.toml", "cards.py", "sleeve.py"):
        shutil.copy(ROOT / f, tmp_path / f)
    mutation_hash.record(tmp_path)
    return tmp_path


def test_unchanged_hash_passes(tmp_path):
    root = _copy(tmp_path)
    assert mutation_hash.fresh(root)
    p = root / "cards.py"
    p.write_text(p.read_text().replace("def save_card(path, text):", "def save_card(path, text):  # a comment", 1))
    assert mutation_hash.fresh(root)                            # comments don't count


def test_edited_function_body_fails(tmp_path):
    root = _copy(tmp_path)
    p = root / "cards.py"
    p.write_text(p.read_text().replace("os.replace(tmp, path)", "os.replace(tmp, str(path))", 1))
    assert not mutation_hash.fresh(root)


def test_edited_toml_fails_and_missing_record_fails(tmp_path):
    root = _copy(tmp_path)
    t = root / "safety_functions.toml"
    t.write_text(t.read_text() + "\n# note\n")
    assert not mutation_hash.fresh(root)
    (root / mutation_hash.RECORD).unlink()
    assert not mutation_hash.fresh(root)
