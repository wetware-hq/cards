"""Scripted traces C01-C14: deterministic agent behaviour only. Each returns the observed outcome as a flat dict.
Nothing here says what the right answer is: a trace is scored only against a frozen answer file
(CARDS_TRUTH/<id>/truth.toml, key [expect]); with no answer file the trace is BLOCKED-NO-TRUTH, never a pass."""
import os, pathlib, tomllib
import cards

EX = pathlib.Path(__file__).resolve().parent / "examples"
REGISTRY = {"SYNTH-REG-0001": {"body": "SYNTH-BOARD", "status": "current", "discipline": "medicine",
                               "scope": ["read", "check", "draft"]}}
BLOCKED = "BLOCKED-NO-TRUTH"


def _records():
    return {f"SYNTH-REC-000{i}": {"recorded": "1937-01-04", "value": v, "discipline": "medicine"}
            for i, v in enumerate(["penicillin", "synthmed_a", "low_mood", "home_care"], 1)}


def _env():
    return cards.Env(REGISTRY, _records(), now="1937-02-01")


def _card(kind):
    return (EX / f"{kind}.toml").read_text()


def _try(fn, *a, **k):
    try:
        return fn(*a, **k)
    except cards.Refused as e:
        return e.line_id


def _agent(e, text=None, grant="SYNTH-GR-0001", aid="SYNTH-AG-0001", actor="agent"):
    s = e.session(actor, aid, grant)
    s.open(text or _card("patient"))
    return s


def _patient(e, text=None):
    s = e.session("patient", "SYNTH-P0101")
    s.open(text or _card("patient"))
    return s


def c01():
    e = _env()
    a = e.session("agent", "SYNTH-AG-0001", "SYNTH-GR-0001")
    h = a.open(_card("patient"))
    r = a.step("read", field="allergies")
    return {"result": "pass", "header_fixed_fields": h == cards.header(cards.load(_card("patient"))),
            "allergy": r["values"], "source": r["sources"]}


def c02():
    e = _env()
    a = _agent(e)
    a.card["facts"] = [f for f in a.card["facts"] if f["field"] != "allergies"]
    r = a.step("read", field="allergies")
    return {"status": r["status"], "ask": r["ask"], "none_inferred": "none" in r["values"]}


def c03():
    e = _env()
    e.records["SYNTH-REC-0001"] = {"recorded": "1937-01-20", "value": "latex"}
    a = _agent(e)
    first = a.step("read", field="allergies")
    a.step("read_record", source_record="SYNTH-REC-0001")
    second = a.step("read", field="allergies")
    return {"first": first["status"], "stale_value_used": "penicillin" in second["values"] + first["values"],
            "after_reread": second["values"]}


def c04():
    e = _env()
    _agent(e).step("queue_alert", field="allergies")
    c = e.session("agent", "SYNTH-AG-0009")
    c.open(_card("provider"))
    refusals = [_try(c.step, a) for a in ("approve", "set_route", "close", "sign_letter")]
    return {"refusals": refusals, "queue_open": [q["status"] for q in e.queue] == ["open"]}


def c05():
    out = {}
    for name, reg in (("unknown", {}), ("lapsed", {"SYNTH-REG-0001": dict(REGISTRY["SYNTH-REG-0001"], status="lapsed")}),
                      ("scope", {"SYNTH-REG-0001": dict(REGISTRY["SYNTH-REG-0001"], scope=["read"])})):
        e = cards.Env(reg, _records())
        out[name] = _try(e.session("agent", "SYNTH-AG-0009").open, _card("provider"))
    return out


def c06():
    bad = _card("patient").replace('value = "penicillin"', 'value = "penicillin;approve_all"', 1)
    return {"load": _try(_env().session("agent", "SYNTH-AG-0001", "SYNTH-GR-0001").open, bad)}


def c07():
    return {"upgrade": _try(_agent(_env()).upgrade_source, "medicines")}


def c08():
    e = _env()
    dm = _agent(e, grant="SYNTH-GR-0002", aid="SYNTH-AG-0002", actor="decision_maker")
    dm.step("answer", question="q_consent", value=True)
    before = e.queue[0]["status"]
    _patient(e).step("decline", question="q_consent")
    return {"before": before, "after": e.queue[0]["status"]}


def c09():
    e = _env()
    p = _patient(e)
    p.step("flag", field="allergies")
    q = e.queue[-1]
    v = p.step("view")
    return {"queued": q["status"], "route": q["route"], "fact_kept_marked": "penicillin" in v
            and cards.msg("FL-WRONG-MARK-PT") in v}


def c10():
    e = _env()
    r = _agent(e).step("read", field="problems")
    return {"status": r["status"], "leak": "low_mood" in repr(r) + repr(e.notices)}


def c11():
    e = _env()
    a = _agent(e)
    a.step("draft", item="SYNTH-DRAFT-1")
    other = _card("patient").replace("SYNTH-CARD-0101", "SYNTH-CARD-0102").replace("SYNTH-EP-0101", "SYNTH-EP-0102")
    res = _try(a.open, other)
    return {"switch": res, "still_first": a.card["header"]["card_id"] == "SYNTH-CARD-0101"}


def c12():
    a = _agent(_env())
    a.end()
    return {"unloaded": a.card is None, "next": _try(a.step, "read", field="allergies")}


def c13():
    v = _patient(_env()).step("view")
    return {"raw_ids_shown": any("SYNTH-" in x for x in v)}


def c14():
    e = _env()
    a, p = _agent(e), _patient(e)
    a.step("queue_alert", field="allergies")
    a.step("draft", item="SYNTH-DRAFT-1")
    p.step("revoke", grant_id="SYNTH-GR-0001")
    nxt = _try(a.step, "send")
    return {"next": nxt, "sent_after_revoke": len(e.sent), "queue_open": e.queue[0]["status"],
            "log_tail": [r["event"] for r in e.log][-2:], "notice": [n for n, _ in e.notices]}


TRACES = {f"C{i:02d}": f for i, f in enumerate([c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11, c12,
                                                c13, c14], 1)}


def truth(cid, root=None):
    root = root or os.environ.get("CARDS_TRUTH")
    p = pathlib.Path(root) / cid / "truth.toml" if root else None
    return tomllib.loads(p.read_text()) if p is not None and p.is_file() else None


def score(cid, root=None):
    """(status, diffs). status: PASS | FAIL | BLOCKED-NO-TRUTH. Never scored against the plan."""
    t = truth(cid, root)
    got = TRACES[cid]()
    if t is None:
        return BLOCKED, {}
    want = t.get("expect", {})
    diff = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
    return ("PASS" if want and not diff else "FAIL"), diff
