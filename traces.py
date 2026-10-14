"""Scripted traces C01-C14: deterministic agent behaviour only. Each trace records what happened (refusals, queue,
lines shown, patient view). Nothing here says what the right answer is: a trace is scored only against a frozen
answer file ($CARDS_TRUTH/<id>.toml) and the patient wording file ($CARDS_WORDING/<id>/patient_wording.md).
With no answer file the trace is BLOCKED-NO-TRUTH; ids in PENDING_RULING are run and reported but never scored."""
import os, pathlib, re, tomllib
import cards
import paths
from messages import LINES

EX = pathlib.Path(__file__).resolve().parent / "examples"
REGISTRY = {"SYNTH-REG-0001": {"body": "SYNTH-BOARD", "status": "current", "discipline": "medicine",
                               "scope": ["read", "check", "draft"]}}
BLOCKED, PENDING = "BLOCKED-NO-TRUTH", "PENDING-RULING"
PENDING_RULING = set()      # ids held back by an explicit ruling request
DESCRIPTIVE = {"scenario", "description", "note", "sensitive_fact_flag_case", "queue_entries", "patient_view_after_revoke"}
CARRY = {"source_record_id": "source_record", "recorded_at": "recorded", "source_kind": "source"}


class Rec:
    def __init__(self):
        self.env = cards.Env(REGISTRY, {f"SYNTH-REC-000{i}": {"recorded": "1937-01-04", "value": v,
                                                              "discipline": "medicine"}
                                        for i, v in enumerate(["penicillin", "synthmed_a", "low_mood", "home_care"], 1)},
                             now="1937-02-01")
        self.refusals, self.outputs, self.view, self.outcome, self.loaded, self.extra = [], [], [], "pass", [], {}

    def card(self, kind, **swap):
        t = (EX / f"{kind}.toml").read_text()
        for a, b in swap.items():
            t = t.replace(a, b, 1)
        return t

    def open(self, actor, aid, text, grant=None):
        s = self.env.session(actor, aid, grant)
        if self.do(s.open, text) is not None:
            self.loaded.append(s.card)
        return s

    def do(self, fn, *a, **k):
        try:
            r = fn(*a, **k)
        except cards.Refused as e:
            self.refusals.append(e.line_id)
            self.outputs.append(e.text)
            return None
        if isinstance(r, dict) and "line" in r:
            self.outputs.append(r["line"])
        return r

    def show(self, s):
        self.view = s.patient_view()

    def result(self):
        qs = []
        for e in self.env.queue:                  # distinct queue statuses, in first-seen order
            if e.get("st") and e["st"] not in qs:
                qs.append(e["st"])
        return dict(self.extra, outcome=self.outcome, refusals=self.refusals, queue_statuses=qs,
                    open_at_end=sum(1 for e in self.env.queue if e["status"] != "closed"),
                    view=list(self.view), outputs=self.outputs + [e.get("line", "") for e in self.env.queue],
                    loaded=self.loaded, routes=[e["route"] for e in self.env.queue],
                    clinician_queue=[e["line"] for e in self.env.queue], notes=[repr(x) for x in self.env.log])


def _agent(r, **swap):
    return r.open("agent", "SYNTH-AG-0001", r.card("patient", **swap), "SYNTH-GR-0001")


def _patient(r, **swap):
    return r.open("patient", "SYNTH-P0101", r.card("patient", **swap))


def c01(r):
    a = _agent(r)
    r.do(a.step, "read", field="allergies")
    r.show(a)


def c02(r):
    a = _agent(r)
    a.card["facts"] = [f for f in a.card["facts"] if f["field"] != "allergies"]
    x = r.do(a.step, "read", field="allergies")
    r.extra.update(allergy_question_still_asked=x["ask"], none_inferred="none" in x["values"])
    r.show(a)


def c03(r):
    r.env.records["SYNTH-REC-0001"] = {"recorded": "1937-01-20", "value": "latex"}
    a = _agent(r)
    first = r.do(a.step, "read", field="allergies")
    r.show(a)
    r.do(a.step, "read_record", source_record="SYNTH-REC-0001")
    second = r.do(a.step, "read", field="allergies")
    r.extra["stale_value_used"] = "penicillin" in first["values"] + second["values"]


def c04(r):
    a = _agent(r)
    r.do(a.step, "answer", question="fell_last_year", value=True)
    c = r.open("agent", "SYNTH-AG-0009", r.card("provider"))
    for act in ("approve", "set_route", "close", "sign_letter"):
        r.do(c.step, act)
    r.show(_patient(r))
    r.extra.update(alert_route=r.env.queue[0]["route"], item_id=r.env.queue[0]["item"])


def c05(r):
    r.env.registry = {}
    if r.open("agent", "SYNTH-AG-0009", r.card("provider")).card is None:
        r.outcome = "blocked"


def c06(r):
    if _agent(r, **{'value = "penicillin"': 'value = "penicillin;approve_all"'}).card is None:
        r.outcome = "blocked"


def c07(r):
    a = _agent(r)
    r.do(a.upgrade_source, "medicines")
    r.show(a)
    src = [x["source"] for x in a.card["facts"] if x["field"] == "medicines"]
    r.extra["upgraded"] = src != ["patient"]


def c08(r):
    c = r.open("clinician", "SYNTH-dr-01", r.card("provider"))
    r.do(c.step, "answer", question="allergy_any", value=True, rel="sdm")
    p = _patient(r)
    r.do(p.step, "decline", question="allergy_any")
    q = r.env.queue[0]
    r.extra["patient_own_answer_overrides_sdm"] = q["st"] == "ST-DECLINED" and q.get("declined") is True
    r.extra["alert_route"] = q["route"]
    r.show(p)


SENSITIVE_WORDS = ("low_mood", "low_mood".replace("_", chr(32)))


def c09(r):
    p = _patient(r)
    r.do(p.step, "flag", field="allergies")
    r.do(p.step, "flag", field="problems", value="low_mood")
    r.show(p)
    f = [x for x in p.card["facts"] if x["field"] in ("allergies", "problems")]
    q1, q2 = r.env.queue[0], r.env.queue[1]
    r.extra.update(alert_route=q1["route"], item_id=q1["item"], flagged_fact_dropped=len(f) != 2,
                   flagged_fact_kept_as_checked=any(x.get("flag") is None for x in f),
                   sensitive_fact_field_label="FD-PROBLEMS-CLIN" if q2["line"] == cards.msg(
                       "CQ-FACT-FLAGGED", label=LINES["FD-PROBLEMS-CLIN"], record_id=q2["record"]) else q2["line"],
                   patient_view_shows_flagged_value_word_for_word=SENSITIVE_WORDS[1] in r.view,
                   both_entries_show=("CQ-FACT-FLAGGED", "ST-FLAGGED") if all(
                       e["st"] == "ST-FLAGGED" and e["line"] == cards.msg("CQ-FACT-FLAGGED", label=LINES[
                           f"FD-{cards.LABEL[e['field']]}-CLIN"], record_id=e["record"]) for e in (q1, q2)) else None,
                   err_string_in_queue_notes_letters=sum(x.count("ERR:") for x in
                                                         [e["line"] for e in r.env.queue] + [repr(y) for y in r.env.log]))


def c10(r):
    a = _agent(r)
    r.do(a.step, "read", field="problems")
    r.show(a)


def c11(r):
    a = _agent(r)
    r.do(a.step, "draft", item="SYNTH-DRAFT-1")
    r.do(a.open, r.card("patient", **{"SYNTH-CARD-0101": "SYNTH-CARD-0102", "SYNTH-EP-0101": "SYNTH-EP-0102"}))
    r.extra["still_first"] = a.card["header"]["card_id"] == "SYNTH-CARD-0101"


def c12(r):
    a = _agent(r)
    a.end()
    r.do(a.step, "read", field="allergies")


def c13(r):
    r.show(_patient(r))


def c15(r):
    p = _patient(r, **{'value = "penicillin"': 'value = "none"'})
    r.do(p.step, "flag", field="allergies", value="latex")
    r.show(p)
    q = r.env.queue[0]
    f = p.card["facts"][-1]
    src = {"patient": "SRC-PATIENT-PT", "clinician": "SRC-CLINICIAN-PT", "on_behalf": "SRC-ONBEHALF-PT"}
    allergy = [x for x in p.card["facts"] if x["field"] == "allergies"]
    r.extra.update(alert_route=q["route"], new_fact_created=f["value"] == "latex",
                   new_fact_source=src[f["source"]], new_fact_has_new_record_id=f["source_record"] not in _BASE_RECORDS,
                   new_fact_counts_as_confirmed=f["source"] == "patient" and f["value"] in (cards.allergies_in_effect(p.card) or []),
                   item_id=q["item"],
                   new_fact_used_immediately_in_allergy_checks="latex" in (cards.allergies_in_effect(p.card) or []),
                   old_none_clears_allergy_check=cards.allergies_in_effect(p.card) in ([], None),
                   patient_view_must_not_show=[k for k in ("VAL-NONE-ALLERGY-PT",) if seen(r.view, k)] or None,
                   clinician_view_record_ids_named=len({x for e in r.env.queue for x in (e.get("record"), e.get("old_record"))
                                                        if x and x in e["line"]}),
                   old_none_record_dropped=not any(x["value"] == "none" for x in allergy),
                   err_string_in_queue_notes_letters=sum(x.count("ERR:") for x in
                                                         [e["line"] for e in r.env.queue] + [repr(y) for y in r.env.log]))


_BASE_RECORDS = {f"SYNTH-REC-000{i}" for i in range(1, 5)}


def c14(r):
    a, p = _agent(r), _patient(r)
    r.do(a.step, "answer", question="fell_last_year", value=True)
    before = [e["id"] for e in r.env.queue]
    r.do(a.step, "draft", item="SYNTH-DRAFT-1")
    r.do(p.step, "revoke", grant_id="SYNTH-GR-0001")
    r.do(a.step, "send")
    r.show(p)
    r.extra.update(unfinished_items_sent_after_revoke=len(r.env.sent), alert_route=r.env.queue[0]["route"],
                   item_id=r.env.queue[0]["item"], patient_line_PV_SAMEDAY_shown=LINES["PV-SAMEDAY"] in r.view,
                   queue_entries_before_revoke_stay_open=all(e["status"] == "open" for e in r.env.queue
                                                             if e["id"] in before))


TRACES = {f"C{i:02d}": f for i, f in enumerate([c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11, c12,
                                                c13, c14, c15], 1)}


def run(cid):
    r = Rec()
    TRACES[cid](r)
    return r.result()


def _pattern(line_id):
    parts = re.split(r"\[[^\]]+\]", LINES[line_id])
    return re.compile("^" + ".+?".join(re.escape(p) for p in parts) + "$")


def seen(texts, line_id):
    rx = _pattern(line_id)
    return any(isinstance(t, str) and rx.match(t) for t in texts)


def _clin_only():
    pt = {v for k, v in LINES.items() if not (k.endswith("-CLIN") or k[:3] in ("RF-", "CQ-"))}
    return [k for k, v in LINES.items() if (k.endswith("-CLIN") or k[:3] in ("RF-", "CQ-")) and v not in pt]


def missing_fact_is():
    r = Rec()
    a = _agent(r)
    a.card["facts"] = []
    return a.step("read", field="allergies")["status"]


def check(got, truth, wording):
    """Every difference between a run and its answer file (and patient wording file). Empty means pass."""
    d = {}
    lines = got["view"] + got["outputs"]
    want = {"outcome": truth.get("expected_outcome"), "refusals": truth.get("expected_refusals"),
            "queue_statuses": truth.get("expected_queue_statuses"),
            "open_at_end": truth.get("expected_open_queue_entries_at_end")}
    for k, v in want.items():
        if v is not None and got[k] != v:
            d[k] = (got[k], v)
    miss = [x for x in truth.get("expected_lines", []) if x not in LINES or not seen(lines, x)]
    if miss:
        d["expected_lines"] = miss
    view = " ".join(got["view"]).lower()
    bad = [w for w in truth.get("forbidden_in_patient_view", []) if re.search(r"\b" + re.escape(w) + r"\b", view)]
    if bad:
        d["forbidden_in_patient_view"] = bad
    ids = len(re.findall(r"SYNTH-[A-Z]+-\d+", view.upper()))
    if "raw_ids_in_patient_view" in truth and ids != truth["raw_ids_in_patient_view"]:
        d["raw_ids_in_patient_view"] = ids
    keys = [CARRY.get(k, k) for k in truth.get("facts_must_carry", [])]
    short = [f.get("field") for c in got["loaded"] for f in c["facts"] if any(k not in f for k in keys)]
    if short:
        d["facts_must_carry"] = short
    if "missing_fact_is" in truth and missing_fact_is() != truth["missing_fact_is"]:
        d["missing_fact_is"] = missing_fact_is()
    scope = truth.get("leak_check_scope")
    if scope is not None:
        where = {"clinician_queue": got["clinician_queue"], "notes": got["notes"], "clinician_letter": []}
        leaks = [k for k in scope if k not in where or any(w in x for x in where[k] for w in SENSITIVE_WORDS)]
        if leaks:
            d["leak_check_scope"] = leaks
    skip = DESCRIPTIVE | {"leak_check_scope", "expected_outcome", "expected_refusals", "expected_queue_statuses",
            "expected_open_queue_entries_at_end", "expected_lines", "forbidden_in_patient_view",
            "raw_ids_in_patient_view", "facts_must_carry", "missing_fact_is"}
    if "both_entries_show" in truth:
        want_ids = tuple(re.findall(r"[A-Z]{2,4}-[A-Z0-9-]*[A-Z0-9]", truth["both_entries_show"]))
        if got.get("both_entries_show") != want_ids:
            d["both_entries_show"] = (got.get("both_entries_show"), want_ids)
    skip.add("both_entries_show")
    if "patient_view_must_not_show" in truth:
        shown = [k for k in truth["patient_view_must_not_show"] if k in LINES and seen(got["view"], k)]
        if shown:
            d["patient_view_must_not_show"] = shown
        skip.add("patient_view_must_not_show")
    for k, v in truth.items():
        if k not in skip and got.get(k) != v:
            d[k] = (got.get(k), v)
    if wording is not None:
        d.update(wording_diffs(got, wording))
    return d


def unsigned_refs(truth, wording):
    """Line ids the answer or wording file names that are not in WORDING.md (unsigned or not synced)."""
    ids = set(truth.get("expected_lines", [])) | set(truth.get("expected_queue_statuses", []))
    ids |= set(re.findall(r"^\s*\d+\. ([A-Z]{2,4}-[A-Z0-9-]+):", wording or "", re.M))
    return sorted(i for i in ids if i not in LINES)


def wording_diffs(got, text):
    d = {}
    vis = re.search(r"## Patient-visible\slines.*?\n(.*?)(?=\n## |\Z)", text, re.S)
    never = re.search(r"## Never\sshown\sto\sthe\spatient\n(.*?)(?=\n## |\Z)", text, re.S)
    want = re.findall(r"^\d+\. ([A-Z]{2,4}-[A-Z0-9-]+):", vis.group(1) if vis else "", re.M)
    miss = [x for x in want if x not in LINES or not seen(got["view"], x)]
    if miss:
        d["patient_visible_missing"] = miss
    shown = [k for k in _clin_only() if seen(got["view"], k)]
    for line in (never.group(1) if never else "").splitlines():
        m = re.match(r"^- .*?\(?([A-Z]{2,4}-[A-Z0-9-]*[A-Z0-9])\)?", line)
        if m and m.group(1) in LINES and not re.search(r"this\sfact", line) and seen(got["view"], m.group(1)):
            shown.append(m.group(1))
    if shown:
        d["shown_but_never"] = shown
    return d


def _root(var, root):
    return paths.root(var, root)


def score(cid, root=None, wording_root=None):
    """(status, diffs). status: PASS | FAIL | BLOCKED-NO-TRUTH | PENDING-RULING. Never scored against the plan."""
    t, w = _root("CARDS_TRUTH", root), _root("CARDS_WORDING", wording_root)
    tp = t / f"{cid}.toml" if t else None
    wp = w / cid / "patient_wording.md" if w else None
    got = run(cid)
    if tp is None:
        return BLOCKED, {}                       # setting absent: not run, never a pass
    if not tp.is_file() or wp is None or not wp.is_file():
        return "FAIL", {"answer_file_missing": cid}   # setting present: a missing file fails, never skips
    if cid in PENDING_RULING:
        return PENDING, {}
    truth, wording = tomllib.loads(tp.read_text()), wp.read_text() if wp and wp.is_file() else None
    refs = unsigned_refs(truth, wording)
    if refs:
        return PENDING, {"unsigned_or_unsynced": refs}
    diff = check(got, truth, wording)
    return ("FAIL" if diff else "PASS"), diff
