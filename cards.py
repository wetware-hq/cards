"""Identity cards for patients and providers. An agent loads one card per session (simulated login) and does
background work for that person. The card is typed TOML: every field has a fixed type and values from fixed lists;
free text is refused. Facts are references to source records, never copies. Synthetic data only."""
import clock
import os, pathlib, re, tempfile, tomllib
from messages import msg

ID = {"card_id": r"SYNTH-CARD-\d{1,6}", "episode_id": r"SYNTH-EP-\d{1,6}", "registration_id": r"SYNTH-REG-\d{1,6}",
      "grant_id": r"SYNTH-GR-\d{1,6}", "agent_id": r"SYNTH-(?:AG-\d{1,6}|PERSON-[A-Z]\d{1,4}[A-Z]?)", "source_record": r"SYNTH-REC-\d{1,6}"}
NAME = r"[A-Z]\.\s[A-Z][a-z]{1,20}"          # initial-style name, e.g. a one-letter initial then a surname
AGENT_NAME = r"[A-Z][a-z]{1,20}"            # display name stored at grant time
DATE = r"193\d-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"
KINDS = {"patient", "provider"}
ROLES = {"patient": {"patient"}, "provider": {"clinician"}}
SCOPES = {"read", "check", "draft"}
DISCIPLINES = {"medicine", "nursing", "pharmacy", "physiotherapy", "psychology"}
TEAMS = {"ward", "clinic", "community"}
SOURCES = {"patient", "clinician", "on_behalf"}
RELS = {"parent", "guardian", "sdm"}
GRANT_EVENTS = ("granted", "revoked", "expired")   # append-only grant history, scenario clock only
CATEGORIES = {"general", "mental_health", "sexual_health"}
VALUES = {"allergies": {"penicillin", "peanut", "latex", "none"},
          "medicines": {"synthmed_a", "synthmed_b", "none"},
          "problems": {"asthma", "diabetes", "low_mood", "self_harm_risk", "none"},
          "preferences": {"home_care", "family_present"}}
SAFETY_FIELDS = ("allergies", "medicines", "problems")
SENSITIVE = {"low_mood": "mental_health", "self_harm_risk": "mental_health"}
ROUTES = ("routine", "before_procedure", "same_day")      # lowest to highest
ROUTE = {"allergies": "before_procedure", "medicines": "before_procedure", "self_harm_risk": "same_day"}
QUESTION_ROUTE = {"allergy_any": "before_procedure"}     # unset question: same_day
ALERT_LINE = {"same_day": "CQ-SAMEDAY-ALERT", "before_procedure": "CQ-BEFORE-PROC"}
ITEM = {"allergies": "allergy_any"}         # question id a flagged field's alert names
PATIENT_ROUTE_LINE = {"same_day": "PV-SAMEDAY", "before_procedure": "PV-BEFORE-PROC"}
LABEL = {"allergies": "ALLERGIES", "medicines": "MEDICINES", "problems": "PROBLEMS", "preferences": "PREFERENCES"}
NONE_ID = {"allergies": "ALLERGY", "medicines": "MEDICINES", "problems": "PROBLEMS"}
HEADER = ("card_id", "kind", "display_name", "role", "scope", "issued", "expires")
SIGN_ONLY = {"approve": "RF-SIGN-APPROVE", "set_route": "RF-SIGN-ROUTE", "close": "RF-SIGN-CLOSE",
             "sign_letter": "RF-SIGN-LETTER"}
ACTOR_ACTIONS = {"agent": {"read", "read_record", "check", "draft", "send", "queue_alert", "answer"},
                 "decision_maker": {"read", "answer"},
                 "patient": {"read", "view", "flag", "decline", "revoke", "answer"},
                 "clinician": {"read", "read_record", "check", "draft", "review", "answer"}}
PROVIDER_AGENT = {"read", "read_record", "check", "draft"}


class Refused(Exception):
    def __init__(self, line_id, text):
        super().__init__(line_id)
        self.line_id, self.text = line_id, text


def _free(label):
    return Refused("RF-FREE-TEXT", msg("RF-FREE-TEXT", label=label))


def _typed(label, v, pattern=None, allowed=None):
    """One typed value: a string matching pattern fully, or a member of allowed. Anything else is free text."""
    if not isinstance(v, str):
        raise _free(label)
    if allowed is not None and v not in allowed:
        raise _free(label)
    if pattern is not None and not re.fullmatch(pattern, v):
        raise _free(label)
    return v


def _keys(label, d, need, opt=()):
    if not isinstance(d, dict) or not set(need) <= set(d) or set(d) - set(need) - set(opt):
        raise _free(label)


def load(text):
    """Parse and type-check a card. Returns a plain dict. Free text anywhere refuses the whole card (RF-FREE-TEXT)."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise _free("card")
    _keys("card", raw, ("header",), ("fact", "grant", "grant_event"))
    h = raw["header"]
    kind = h.get("kind") if isinstance(h, dict) else None
    _typed("kind", kind, allowed=KINDS)
    prov = ("discipline", "team", "registration_id")
    _keys("header", h, HEADER + ("episode_id", "person_name") + (prov if kind == "provider" else ()))
    _typed("card_id", h["card_id"], ID["card_id"])
    _typed("display_name", h["display_name"], NAME)
    _typed("person_name", h["person_name"], NAME)
    _typed("role", h["role"], allowed=ROLES[kind])
    _typed("episode_id", h["episode_id"], ID["episode_id"])
    for k in ("issued", "expires"):
        _typed(k, h[k], DATE)
    if not isinstance(h["scope"], list) or not h["scope"]:
        raise _free("scope")
    for s in h["scope"]:
        _typed("scope", s, allowed=SCOPES)
    if kind == "provider":
        _typed("discipline", h["discipline"], allowed=DISCIPLINES)
        _typed("team", h["team"], allowed=TEAMS)
        _typed("registration_id", h["registration_id"], ID["registration_id"])
    facts = raw.get("fact", [])
    grants = raw.get("grant", [])
    if kind == "provider" and (facts or grants):
        raise _free("card")
    for f in facts:
        _keys("fact", f, ("field", "value", "source", "source_record", "recorded"), ("rel",))
        _typed("field", f["field"], allowed=set(VALUES))
        _typed(LABEL[f["field"]].lower(), f["value"], allowed=VALUES[f["field"]])
        _typed("source", f["source"], allowed=SOURCES)
        _typed("source_record", f["source_record"], ID["source_record"])
        _typed("recorded", f["recorded"], DATE)
        if (f["source"] == "on_behalf") != ("rel" in f):
            raise _free("rel")
        if "rel" in f:
            _typed("rel", f["rel"], allowed=RELS)
    for g in grants:
        _keys("grant", g, ("grant_id", "agent_id", "agent_name", "categories", "granted"), ("rel", "person_name", "expires_at"))
        _typed("grant_id", g["grant_id"], ID["grant_id"])
        _typed("agent_id", g["agent_id"], ID["agent_id"])
        _typed("agent_name", g["agent_name"], AGENT_NAME)
        _typed("granted", g["granted"], DATE)
        if "expires_at" in g:
            _typed("expires_at", g["expires_at"], DATE)
            if g["expires_at"] <= g["granted"]:
                raise _free("expires_at")
        if not isinstance(g["categories"], list) or "general" not in g["categories"]:
            raise _free("categories")
        for c in g["categories"]:
            _typed("categories", c, allowed=CATEGORIES)
        if ("rel" in g) != ("person_name" in g):
            raise _free("rel")
        if "rel" in g:
            _typed("rel", g["rel"], allowed=RELS)
            _typed("person_name", g["person_name"], NAME)
    events = raw.get("grant_event", [])
    ids, state, last = {g["grant_id"]: g for g in grants}, {}, None
    for ev in events:                                    # append-only: in scenario-time order, granted first, nothing after an end
        _keys("grant_event", ev, ("grant_id", "event", "at"))
        _typed("grant_id", ev["grant_id"], ID["grant_id"])
        _typed("event", ev["event"], allowed=set(GRANT_EVENTS))
        _typed("at", ev["at"], DATE)
        g, prev = ids.get(ev["grant_id"]), state.get(ev["grant_id"])
        if g is None or (last is not None and ev["at"] < last) or (ev["event"] == "granted") != (prev is None) \
                or prev in ("revoked", "expired") or (ev["event"] == "granted" and ev["at"] != g["granted"]):
            raise _free("grant_event")
        state[ev["grant_id"]], last = ev["event"], ev["at"]
    if set(state) != set(ids):
        raise _free("grant_event")
    return {"header": dict(h), "facts": [dict(f) for f in facts], "grants": {g["grant_id"]: dict(g) for g in grants},
            "grant_events": [dict(e) for e in events]}


def grant_state(card, grant_id, now, revoked=None):
    """The one read path for a grant: current | revoked | expired | unknown at scenario time `now` (never the wall
    clock). An end at or before `now` counts; a later grant to the same person never revives an ended grant."""
    if grant_id not in card.get("grants", {}):
        return "unknown"
    if revoked and grant_id in revoked and revoked[grant_id] <= now:
        return "revoked"
    st = "unknown"
    for e in card.get("grant_events", []):
        if e["grant_id"] == grant_id and e["at"] <= now:
            st = "current" if e["event"] == "granted" else e["event"]
    exp = card["grants"][grant_id].get("expires_at")
    return "expired" if st == "current" and exp is not None and exp <= now else st


def header(card):
    """Agent header: assembled only from typed header values, in a fixed order. Never the card text as written."""
    h = card["header"]
    return ";".join(f"{k}={','.join(h[k]) if k == 'scope' else h[k]}" for k in HEADER)


def category(fact):
    return SENSITIVE.get(fact["value"], "general")


def route(fact):
    """An item's own alert_route: the higher of its field's route and its value's route."""
    a, b = ROUTE.get(fact["field"], "routine"), ROUTE.get(fact["value"], "routine")
    return max(a, b, key=ROUTES.index)


def save_card(path, text):
    """Write a card file atomically: a temp file in the same folder, fsync, then os.replace. On any failure the old
    file is left exactly as it was and the error is raised."""
    path = pathlib.Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".card-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    d = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(d)
    finally:
        os.close(d)


def allergies_in_effect(card):
    """The allergies an allergy check must use: every recorded allergy, a patient's own report counting at once.
    An explicit "none" never clears an allergy and never removes one. None when nothing is recorded (unknown)."""
    facts = [f for f in card["facts"] if f["field"] == "allergies"]
    if not facts:
        return None
    return sorted({f["value"] for f in facts if f["value"] != "none"})


class Env:
    """The environment: verified registrations, source records, the clinician queue, the outbox and the log.
    The log is the activity record; cards only link to it by episode id."""

    def __init__(self, registry=None, records=None, now="1937-03-01"):
        self.registry = dict(registry or {})
        self.records = dict(records or {})
        self.scenario = now                              # the scenario date; read only through the approved clock
        self.queue, self.sent, self.log, self.notices = [], [], [], []
        self.revoked = {}

    @property
    def now(self):
        return clock.today(self.scenario)                # test: scenario clock; real: real clock; unset: refuses

    @now.setter
    def now(self, value):
        self.scenario = value

    def emit(self, episode, event, **f):
        self.log.append(dict(episode=episode, event=event, at=self.now, **f))

    def session(self, actor, actor_id, grant_id=None):
        return Session(self, actor, actor_id, grant_id)

    def episode_log(self, episode_id):
        return [r for r in self.log if r["episode"] == episode_id]


class Session:
    """One actor, one card. actor: agent | decision_maker | patient | clinician."""

    def __init__(self, env, actor, actor_id, grant_id=None):
        self.env, self.actor, self.actor_id, self.grant_id = env, actor, actor_id, grant_id
        self.card, self.grant, self.verified, self.ended = None, None, None, False
        self.drafts, self.fresh = [], {}
        self.path, self.text = None, None

    # ---------------------------------------------------------------- open
    def open(self, text=None, path=None):
        """Open a card from its text, or from its file (then a revoke is saved back to that file)."""
        if self.ended:
            raise Refused("RF-SESSION-ENDED", msg("RF-SESSION-ENDED"))
        if self.card is not None:
            raise Refused("RF-ONE-PROFILE", msg("RF-ONE-PROFILE"))
        if path is not None:
            text = pathlib.Path(path).read_text(encoding="utf-8")
        card = load(text)
        h = card["header"]
        if h["kind"] == "provider":
            reg = self.env.registry.get(h["registration_id"])
            if reg is None or reg["status"] != "current" or reg["discipline"] != h["discipline"] \
                    or not set(h["scope"]) <= set(reg["scope"]):
                raise Refused("RF-REG-UNVERIFIED", msg("RF-REG-UNVERIFIED"))
            if self.actor not in ("agent", "clinician"):
                raise Refused("RF-REG-UNVERIFIED", msg("RF-REG-UNVERIFIED"))
            self.verified = reg
        else:
            if self.actor == "clinician":
                raise Refused("RF-NOT-YOURS", msg("RF-NOT-YOURS"))
            if self.actor in ("agent", "decision_maker"):
                g = card["grants"].get(self.grant_id)
                if g is None or g["agent_id"] != self.actor_id or ("rel" in g) != (self.actor == "decision_maker"):
                    raise Refused("RF-NOT-YOURS", msg("RF-NOT-YOURS"))       # not this actor's grant: no grant ended
                st = grant_state(card, self.grant_id, self.env.now, self.env.revoked)
                if st != "current":
                    raise self._ended(card, st)
                self.grant = g
        self.card, self.path, self.text = card, path, text
        self.env.emit(h["episode_id"], "opened", actor=self.actor)
        return header(card)

    def _ended(self, card, state):
        """RF-REVOKED only for an assistant the patient stopped; revoked or expired otherwise RF-GRANT-ENDED; else RF-NOT-YOURS."""
        if self.actor == "agent" and state == "revoked":
            ends = [e["at"] for e in card["grant_events"] if e["grant_id"] == self.grant_id and e["event"] == "revoked"]
            return Refused("RF-REVOKED", msg("RF-REVOKED", date=self.env.revoked.get(self.grant_id, (ends or [self.env.now])[0])))
        if state in ("revoked", "expired"):
            return Refused("RF-GRANT-ENDED", msg("RF-GRANT-ENDED"))
        return Refused("RF-NOT-YOURS", msg("RF-NOT-YOURS"))              # no live grant of this actor's: not an ended one

    # ---------------------------------------------------------------- gate
    def _gate(self, action):
        if self.ended:
            raise Refused("RF-SESSION-ENDED", msg("RF-SESSION-ENDED"))
        if self.card is None:
            raise Refused("RF-SESSION-ENDED", msg("RF-SESSION-ENDED"))
        ep = self.card["header"]["episode_id"]
        st = "current" if self.grant is None else grant_state(self.card, self.grant_id, self.env.now, self.env.revoked)
        if st != "current":                              # revoked or expired on the scenario clock, mid-session
            card = self.card
            self._discard()
            self.env.emit(ep, "CL-REFUSED", actor=self.actor, action=action)
            raise self._ended(card, st)
        if action in SIGN_ONLY and self.actor != "clinician":
            self.env.emit(ep, "CL-REFUSED", actor=self.actor, action=action)
            raise Refused(SIGN_ONLY[action], msg(SIGN_ONLY[action]))
        if self.card["header"]["kind"] == "provider" and self.actor == "agent" and action not in PROVIDER_AGENT:
            self.env.emit(ep, "CL-REFUSED", actor=self.actor, action=action)
            raise Refused("RF-NOT-YOURS", msg("RF-NOT-YOURS"))
        if action not in ACTOR_ACTIONS[self.actor] and action not in SIGN_ONLY:
            self.env.emit(ep, "CL-REFUSED", actor=self.actor, action=action)
            raise Refused("RF-NOT-YOURS", msg("RF-NOT-YOURS"))
        return ep

    def _discard(self):
        """Unfinished items are dropped, never sent; the patient is told once by name from the grant."""
        if self.drafts:
            self.env.notices.append(("PV-DRAFT-NOT-SENT", msg("PV-DRAFT-NOT-SENT", agent_name=self.grant["agent_name"])))
        self.drafts = []

    def step(self, action, **kw):
        ep = self._gate(action)
        if action in SIGN_ONLY:
            self.env.emit(ep, action, actor=self.actor)
            return True
        return getattr(self, "_" + action)(ep, **kw)

    def end(self):
        if self.card is not None and not self.ended:
            self.env.emit(self.card["header"]["episode_id"], "ended", actor=self.actor)
        self._discard() if self.grant is not None else None
        self.card, self.grant, self.verified, self.ended = None, None, None, True
        self.drafts, self.fresh = [], {}

    # ---------------------------------------------------------------- reads
    def _visible(self, fact):
        if self.grant is None:
            return True
        return category(fact) in self.grant["categories"]

    def _stale(self, fact):
        rec = self.env.records.get(fact["source_record"])
        return rec is None or rec["recorded"] > fact["recorded"]

    def _read(self, ep, field):
        """Agent read of one field. Returns dict(status, line, values). status: known | none | unknown | stale |
        hidden. Unknown always asks; stale never returns the card value; hidden never names category or value."""
        facts = [f for f in self.card["facts"] if f["field"] == field]
        label = msg(f"FD-{LABEL[field]}-CLIN")
        hidden = [f for f in facts if not self._visible(f)]
        facts = [f for f in facts if self._visible(f)]
        if hidden:
            self.env.notices.append(("PV-FACT-HIDDEN", msg("PV-FACT-HIDDEN")))
        stale = [f for f in facts if self._stale(f) and f["source_record"] not in self.fresh]
        if stale:
            f = stale[0]
            rec = self.env.records.get(f["source_record"], {"recorded": f["recorded"]})
            return {"status": "stale", "line": msg("CQ-FACT-STALE", label=label, date=rec["recorded"]),
                    "values": [], "reread": [x["source_record"] for x in stale]}
        values = [self.fresh.get(f["source_record"], f["value"]) for f in facts]
        if not facts:
            line = msg("CQ-FACT-HIDDEN") if hidden else msg("VAL-UNKNOWN-CLIN")
            return {"status": "hidden" if hidden else "unknown", "line": line, "values": [],
                    "ask": field in SAFETY_FIELDS}
        if values == ["none"]:
            f = facts[0]
            src = msg("SRC-CLINICIAN-CLIN", discipline=self.env.records[f["source_record"]].get("discipline", ""),
                      date=f["recorded"]) if f["source"] == "clinician" else msg("SRC-PATIENT-CLIN")
            return {"status": "none", "line": msg(f"VAL-NONE-{NONE_ID[field]}-CLIN", source=src, date=f["recorded"]),
                    "values": ["none"]}
        values = [v for v in values if v != "none"]
        return {"status": "known", "line": label, "values": values,
                "sources": [f["source"] for f in facts], "hidden": bool(hidden)}

    def _read_record(self, ep, source_record):
        """Re-read the source record (the only way past a stale fact)."""
        if source_record not in {f["source_record"] for f in self.card["facts"]}:
            raise Refused("RF-NOT-YOURS", msg("RF-NOT-YOURS"))
        rec = self.env.records[source_record]
        self.fresh[source_record] = rec["value"]
        self.env.emit(ep, "reread", record=source_record)
        return rec["value"]

    def _check(self, ep):
        return {f: self._read(ep, f)["status"] for f in SAFETY_FIELDS}

    # ---------------------------------------------------------------- work
    def _draft(self, ep, item):
        self.drafts.append(item)
        return len(self.drafts)

    def _send(self, ep):
        out, self.drafts = self.drafts, []
        self.env.sent.extend((ep, x) for x in out)
        self.env.emit(ep, "sent", n=len(out))
        return len(out)

    def _queue_alert(self, ep, field):
        """An agent raises a fact for a clinician. A missing fact is raised as unknown (VAL-UNKNOWN-CLIN)."""
        facts = [f for f in self.card["facts"] if f["field"] == field] or [{"field": field, "value": "none"}]
        e = self._new_entry(ep, route=route(facts[0]), kind="alert", field=field, item=ITEM.get(field, field),
                            record=facts[0].get("source_record"), st="ST-UNCONFIRMED")
        self.env.emit(ep, "queued", entry=e["id"])
        return e["id"]

    def _entry_line(self, e):
        """Clinician line for a queue entry. A safety answer's route picks CQ-SAMEDAY-ALERT or CQ-BEFORE-PROC; a flagged
        or agent-raised fact always uses CQ-FACT-FLAGGED (label and record id only) and keeps its route."""
        if e["kind"] == "answer" and e["route"] in ALERT_LINE:
            return msg(ALERT_LINE[e["route"]], item_id=e["item"], event_id=f"{e['episode']}#{e['id']}",
                       status=msg(e["st"]))
        if e["kind"] == "conflict":
            return msg("CQ-RECORD-CONFLICT", label=msg(f"FD-{LABEL[e['field']]}-CLIN"), new_record_id=e["record"],
                       old_record_id=e["old_record"])
        if e["record"] is None:
            return msg("VAL-UNKNOWN-CLIN")
        return msg("CQ-FACT-FLAGGED", label=msg(f"FD-{LABEL[e['field']]}-CLIN"), record_id=e["record"])

    def _new_entry(self, ep, **f):
        e = dict(id=len(self.env.queue) + 1, episode=ep, status="open", at=self.env.now, **f)
        e["line"] = self._entry_line(e)
        self.env.queue.append(e)
        return e

    def _answer(self, ep, question, value, rel=None):
        """An answer for the patient. A clinician records a decision-maker's answer in their own session
        (rel from the signed list); an agent's or decision-maker's answer stays unconfirmed."""
        if not isinstance(value, bool):
            raise _free("answer")
        if self.actor == "clinician":
            _typed("rel", rel, allowed=RELS)
        elif self.actor == "decision_maker":
            rel = self.grant["rel"]
        elif rel is not None:
            raise _free("rel")
        for e in self.env.queue:
            if e.get("question") == question and e["episode"] == ep and not e.get("declined"):
                if self.actor != "patient":
                    return e["id"]
        st = "ST-CONFIRMED" if self.actor == "patient" else "ST-UNCONFIRMED"
        e = self._new_entry(ep, route=QUESTION_ROUTE.get(question, "same_day"), kind="answer", question=question,
                            item=question, value=value, by=self.actor, rel=rel, st=st, grant=self.grant_id)
        self.env.emit(ep, "answered", question=question, by=self.actor)
        return e["id"]

    def _decline(self, ep, question):
        """The patient's own decline overrides any answer given for them. The entry stays open for review."""
        hit = [e for e in self.env.queue if e.get("question") == question and e["episode"] == ep]
        for e in hit:
            e["declined"], e["st"] = True, "ST-DECLINED"
            e["line"] = self._entry_line(e)
        if not hit:
            self._new_entry(ep, route=QUESTION_ROUTE.get(question, "same_day"), kind="answer", question=question,
                            item=question, by="patient", rel=None, declined=True, st="ST-DECLINED")
        self.env.emit(ep, "CL-DECLINED", question=question)
        return True

    def _flag(self, ep, field, value=None):
        """Patient flags a fact as wrong (or says one is missing): one queue entry per flagged fact, on the item's
        own alert_route. The line names the field label and record id only, never the value."""
        same = [f for f in self.card["facts"] if f["field"] == field]
        facts = [f for f in same if value is None or f["value"] == value]
        if facts:
            f = facts[0]
            f["flag"] = "patient"
            st = "ST-FLAGGED"
        else:
            old = [x for x in same if x["value"] == "none" and x["source"] == "clinician"]
            f = self._report(field, value)
            st = "ST-CHANGED"
            if old:                                  # C15: a new answer against an earlier checked "none"
                old[0]["conflict"] = f["source_record"]          # stays marked until a clinician reviews it
                e = self._new_entry(ep, route=route(f), kind="conflict", field=field, item=ITEM.get(field, field),
                                    record=f["source_record"], old_record=old[0]["source_record"], st="ST-FLAGGED")
                self.env.emit(ep, "flagged", entry=e["id"])
                self.env.notices.append(("FL-WRONG-DONE-PT", msg("FL-WRONG-DONE-PT")))
                return msg("FL-WRONG-DONE-PT")
        e = self._new_entry(ep, route=route(f), kind="flag", field=field, item=ITEM.get(field, field),
                            record=f["source_record"], st=st)
        self.env.emit(ep, "flagged", entry=e["id"])
        self.env.notices.append(("FL-WRONG-DONE-PT", msg("FL-WRONG-DONE-PT")))
        return msg("FL-WRONG-DONE-PT")

    def _report(self, field, value):
        """A fact the patient says is missing becomes a new patient-reported fact: the environment gives it its own
        new record id and the session time."""
        _typed(LABEL[field].lower(), value, allowed=VALUES[field])
        if value == "none":
            raise _free(LABEL[field].lower())
        n = 1 + max([int(k.rsplit("-", 1)[1]) for k in self.env.records] + [0])
        rid = f"SYNTH-REC-{n:04d}"
        self.env.records[rid] = {"recorded": self.env.now, "value": value}
        f = {"field": field, "value": value, "source": "patient", "source_record": rid, "recorded": self.env.now}
        self.card["facts"].append(f)
        return f

    def _review(self, ep, entry):
        for e in self.env.queue:
            if e["id"] == entry:
                e["reviewed"] = True
        return True

    def _revoke(self, ep, grant_id):
        if grant_id not in self.card["grants"]:
            raise Refused("RF-NOT-YOURS", msg("RF-NOT-YOURS"))
        ev = {"grant_id": grant_id, "event": "revoked", "at": self.env.now}
        if grant_state(self.card, grant_id, self.env.now) == "current":     # appended to the card's history
            if self.path is not None:                                        # saved first; nothing changes if not
                text = self.text.rstrip("\n") + "\n\n[[grant_event]]\n" + "".join(
                    f'{k} = "{v}"\n' for k, v in ev.items())
                try:
                    load(text)
                    save_card(self.path, text)
                except (OSError, Refused):
                    raise Refused("PV-TRY-AGAIN", msg("PV-TRY-AGAIN"))
                self.text = text
            self.card["grant_events"].append(ev)
        self.env.revoked[grant_id] = self.env.now
        self.env.notices.append(("PV-REVOKE", msg("PV-REVOKE", date=self.env.now)))
        self.env.emit(ep, "CL-REVOKED", grant=grant_id)
        return True

    def upgrade_source(self, field):
        """Only a clinician can mark a fact as checked; an agent can never upgrade a source."""
        self._gate("read")
        if self.actor != "clinician":
            raise Refused("RF-SOURCE-UPGRADE", msg("RF-SOURCE-UPGRADE"))
        return True

    # ---------------------------------------------------------------- views
    def _view(self, ep):
        """Patient view: every fact in plain words with its source; display names only, never raw ids."""
        out = []
        for field in LABEL:
            every = [f for f in self.card["facts"] if f["field"] == field]
            if any(f["value"] != "none" for f in every):
                every = [f for f in every if f["value"] != "none"]
            facts = [f for f in every if self._visible(f)]
            out.append(msg(f"FD-{LABEL[field]}-PT"))
            if len(facts) < len(every):
                out.append(msg("PV-FACT-HIDDEN"))
            elif not facts:
                out.append(msg("VAL-UNKNOWN-PT"))
            for f in facts:
                if f["value"] == "none" and field in NONE_ID:
                    out.append(msg(f"VAL-NONE-{NONE_ID[field]}-PT"))
                else:
                    out.append(f["value"].replace("_", " "))
                if f.get("flag"):
                    pass
                elif f["source"] == "on_behalf":
                    out.append(msg("SRC-ONBEHALF-PT", rel=msg(f"REL-{f['rel'].upper()}-PT")))
                else:
                    out.append(msg("SRC-PATIENT-PT" if f["source"] == "patient" else "SRC-CLINICIAN-PT"))
                if self._stale(f):
                    out.append(msg("PV-FACT-OLD"))
                out.append(msg("FL-WRONG-ACTION-PT"))
                if f.get("flag") == "patient":
                    out.append(msg("FL-WRONG-MARK-PT"))
                if f.get("flag") == "clinician":
                    out.append(msg("FL-WRONG-MARK-CLIN-PT"))
        for gid, g in self.card["grants"].items():           # who acts for the patient now; never grant history
            if "rel" in g and grant_state(self.card, gid, self.env.now, self.env.revoked) == "current":
                out += [msg("FD-ACTS-FOR-PT"), msg(f"REL-{g['rel'].upper()}-PT"), g["person_name"]]
        ep_ = self.card["header"]["episode_id"]
        for e in self.env.queue:
            if e["episode"] != ep_:
                continue
            if e["kind"] == "answer" and e["by"] == "agent" and e["st"] == "ST-UNCONFIRMED":
                out.append(msg("PV-ANS-AGENT"))
                if e.get("grant") in self.env.revoked:
                    out.append(msg("PV-CHECK-PENDING"))
            if e["kind"] == "answer" and e.get("rel") is not None:
                out.append(msg("PV-ANS-SDM", relationship=msg(f"REL-{e['rel'].upper()}-PT"), date=e["at"]))
            if e.get("declined"):
                out.append(msg("PV-DECLINED"))
            settled = e["kind"] in ("flag", "conflict") or e.get("declined") or (e.get("st") == "ST-CONFIRMED" and e.get("value") is True)
            if settled and e["route"] in PATIENT_ROUTE_LINE:
                out.append(msg(PATIENT_ROUTE_LINE[e["route"]]))
        out += [t for k, t in self.env.notices if k != "PV-FACT-HIDDEN"]
        return out

    def patient_view(self):
        """The patient view as rendered by this session (an agent shows only what its grant covers)."""
        if self.ended or self.card is None:
            raise Refused("RF-SESSION-ENDED", msg("RF-SESSION-ENDED"))
        return self._view(self.card["header"]["episode_id"])

    def provider_view(self):
        """What a patient sees about the provider card loaded in this session."""
        h = self.card["header"]
        out = [h["display_name"], msg("FD-DISCIPLINE-PT"), h["discipline"], msg("FD-TEAM-PT"), h["team"]]
        if self.verified is not None and self.verified["status"] == "current":
            out.append(msg("FD-REGISTRATION-PT"))
        return out
