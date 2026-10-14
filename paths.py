"""Where the frozen answer files live: a local setting, never a path in the repo. Read from the environment
(CARDS_TRUTH, CARDS_WORDING) or, failing that, from the untracked file local.toml beside this one
(truth = "...", wording = "..."). Both folders are read-only. Unset: the traces are not run."""
import os, pathlib, tomllib

LOCAL = pathlib.Path(os.environ.get("CARDS_LOCAL") or pathlib.Path(__file__).resolve().parent / "local.toml")
_KEY = {"CARDS_TRUTH": "truth", "CARDS_WORDING": "wording"}


def root(var, given=None):
    r = given or os.environ.get(var)
    if not r and LOCAL.is_file():
        r = tomllib.loads(LOCAL.read_text()).get(_KEY.get(var, ""))
    return pathlib.Path(r) if r else None


def traces_set():
    """True only when both answer-file folders are set."""
    return root("CARDS_TRUTH") is not None and root("CARDS_WORDING") is not None
