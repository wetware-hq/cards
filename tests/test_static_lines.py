"""Static check (ast, not a sweep): every refusal or line id cards can raise or show, read from the source, is a
signed row in WORDING.md. f-string ids built from a module table are expanded over that table; any other
dynamic id fails the check."""
import ast, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import cards, messages

SOURCES = ("cards.py", "sleeve.py")


def _key_values(tree, key):
    """Constant strings ever stored under a dict key (e["st"] = "X" or {"st": "X"})."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            pairs = []
            for tg in n.targets:
                tgs = tg.elts if isinstance(tg, ast.Tuple) else [tg]
                vals = n.value.elts if isinstance(tg, ast.Tuple) and isinstance(n.value, ast.Tuple) else [n.value]
                pairs += list(zip(tgs, vals))
            for tg, v in pairs:
                if isinstance(tg, ast.Subscript) and isinstance(tg.slice, ast.Constant) and tg.slice.value == key \
                        and isinstance(v, ast.Constant) and isinstance(v.value, str):
                    out.add(v.value)
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value == key and isinstance(v, ast.Constant) and isinstance(v.value, str):
                    out.add(v.value)
    return out


def _name_values(tree, name, mod):
    out, dyn = set(), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(isinstance(tg, ast.Name) and tg.id == name for tg in n.targets):
            i, d = _expand(n.value, mod, tree); out |= i; dyn += d
    return out, dyn if out or dyn else [name]


def _table(a, mod):
    """A module dict or set reached as NAME or module.NAME."""
    if isinstance(a, ast.Name):
        return getattr(mod, a.id, None)
    if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name):
        return getattr(getattr(mod, a.value.id, None), a.attr, None)


def _expand(a, mod, tree=None):
    if isinstance(a, ast.Constant) and isinstance(a.value, str):
        return {a.value}, []
    if isinstance(a, ast.IfExp):
        i1, d1 = _expand(a.body, mod, tree); i2, d2 = _expand(a.orelse, mod, tree)
        return i1 | i2, d1 + d2
    if isinstance(a, ast.Name) and tree is not None:
        return _name_values(tree, a.id, mod)
    if isinstance(a, ast.Subscript) and isinstance(a.slice, ast.Constant) and isinstance(a.slice.value, str) \
            and tree is not None and _key_values(tree, a.slice.value):
        return _key_values(tree, a.slice.value), []
    if isinstance(a, ast.JoinedStr):
        parts = [{""}]
        for v in a.values:
            if isinstance(v, ast.Constant):
                parts.append({v.value})
            elif isinstance(v.value, ast.Subscript) and isinstance(_table(v.value.value, mod), dict):
                parts.append({str(x) for x in _table(v.value.value, mod).values()})
            elif isinstance(v.value, ast.Call) and getattr(v.value.func, "attr", None) == "upper" \
                    and isinstance(v.value.func.value, ast.Subscript) and isinstance(v.value.func.value.slice, ast.Constant) \
                    and v.value.func.value.slice.value == "rel":
                parts.append({x.upper() for x in cards.RELS})      # rel is validated against the signed RELS set
            else:
                return set(), [ast.unparse(a)]
        out = {""}
        for p in parts:
            out = {o + x for o in out for x in p}
        return out, []
    if isinstance(a, ast.Subscript) and isinstance(_table(a.value, mod), dict):
        return {str(x) for x in _table(a.value, mod).values()}, []
    return set(), [ast.unparse(a)]


def raised_ids():
    ids, dyn = set(), []
    for name in SOURCES:
        mod = __import__(name[:-3])
        tree = ast.parse((ROOT / name).read_text())
        for n in ast.walk(tree):
            f = n.func if isinstance(n, ast.Call) else None
            if f is not None and (getattr(f, "id", None) in ("msg", "Refused") or getattr(f, "attr", None) == "Refused") and n.args:
                i, d = _expand(n.args[0], mod, tree)
                ids |= i; dyn += [f"{name}: {x}" for x in d]
    return ids, dyn


def test_every_raised_id_is_a_signed_row():
    ids, dyn = raised_ids()
    assert len(ids) > 10
    assert dyn == [] and sorted(i for i in ids if i not in messages.LINES) == []


def test_static_check_fails_on_unknown_id():
    assert "XX-NOT-SIGNED" not in messages.LINES
    ids, _ = raised_ids()
    assert sorted(i for i in ids | {"XX-NOT-SIGNED"} if i not in messages.LINES) == ["XX-NOT-SIGNED"]
