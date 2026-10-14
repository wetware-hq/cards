"""Identity cards for patients and providers. An agent loads one card per session (simulated login) and does
background work for that person. The card is typed TOML: every field has a fixed type and values from fixed lists;
free text is refused. Facts are references to source records, never copies. Synthetic data only."""
import re, tomllib
from messages import msg, code

ID = {"card_id": r"SYNTH-CARD-\d{1,6}", "episode_id": r"SYNTH-EP-\d{1,6}", "registration_id": r"SYNTH-REG-\d{1,6}",
      "grant_id": r"SYNTH-GR-\d{1,6}", "agent_id": r"SYNTH-AG-\d{1,6}", "source_record": r"SYNTH-REC-\d{1,6}"}
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
PATIENT_ROUTE_LINE = {"same_day": "PV-SAMEDAY", "before_procedure": "PV-BEFORE-PROC"}
LABEL = {"allergies": "ALLERGIES", "medicines": "MEDICINES", "problems": "PROBLEMS", "preferences": "PREFERENCES"}
NONE_ID = {"allergies": "ALLERGY", "medicines": "MEDICINES", "problems": "PROBLEMS"}
HEADER = ("card_id", "kind", "display_name", "role", "scope", "issued", "expires")
SIGN_ONLY = {"approve": "RF-SIGN-APPROVE", "set_route": "RF-SIGN-ROUTE", "close": "RF-SIGN-CLOSE",
             "sign_letter": "RF-SIGN-LETTER"}
ACTOR_ACTIONS = {"agent": {"read", "read_record", "check", "draft", "send", "queue_alert", "answer"},
                 "decision_maker": {"read", "answer"},
                 "patient": {"read", "view", "flag", "decline", "revoke", "answer"},
                 "clinician": {"read", "read_record", "check", "draft", "review"}}
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
    _keys("card", raw, ("header",), ("fact", "grant"))
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
        _keys("grant", g, ("grant_id", "agent_id", "agent_name", "categories", "granted"), ("rel", "person_name"))
        _typed("grant_id", g["grant_id"], ID["grant_id"])
        _typed("agent_id", g["agent_id"], ID["agent_id"])
        _typed("agent_name", g["agent_name"], AGENT_NAME)
        _typed("granted", g["granted"], DATE)
        if not isinstance(g["categories"], list) or "general" not in g["categories"]:
            raise _free("categories")
        for c in g["categories"]:
            _typed("categories", c, allowed=CATEGORIES)
        if ("rel" in g) != ("person_name" in g):
            raise _free("rel")
        if "rel" in g:
            _typed("rel", g["rel"], allowed=RELS)
            _typed("person_name", g["person_name"], NAME)
    return {"header": dict(h), "facts": [dict(f) for f in facts], "grants": {g["grant_id"]: dict(g) for g in grants}}


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


class Env:
    """The environment: verified registrations, source records, the clinician queue, the outbox and the log.
    The log is the activity record; cards only link to it by episode id."""

    def __init__(self, registry=None, records=None, now="1937-03-01"):
        self.registry = dict(registry or {})
        self.records = dict(records or {})
        self.now = now
        self.queue, self.sent, self.log, self.notices = [], [], [], []
        self.revoked = {}

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

    # ---------------------------------------------------------------- open
    def open(self, text):
        if self.ended:
            raise Refused("RF-SESSION-ENDED", msg("RF-SESSION-ENDED"))
        if self.card is not None:
            raise Refused("RF-ONE-PROFILE", msg("RF-ONE-PROFILE"))
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
                raise Refused("RF-NOT-YOURS", code("not_yours"))
            if self.actor in ("agent", "decision_maker"):
                g = card["grants"].get(self.grant_id)
                if g is None or g["agent_id"] != self.actor_id or ("rel" in g) != (self.actor == "decision_maker"):
                    raise Refused("RF-REVOKED", msg("RF-REVOKED", date=self.env.now))
                if self.grant_id in self.env.revoked:
                    raise Refused("RF-REVOKED", msg("RF-REVOKED", date=self.env.revoked[self.grant_id]))
                self.grant = g
        self.card = card
        self.env.emit(h["episode_id"], "opened", actor=self.actor)
        return header(card)

    # ---------------------------------------------------------------- gate
    def _gate(self, action):
        if self.ended:
            raise Refused("RF-SESSION-ENDED", msg("RF-SESSION-ENDED"))
        if self.card is None:
            raise Refused("RF-SESSION-ENDED", msg("RF-SESSION-ENDED"))
        ep = self.card["header"]["episode_id"]
        if self.grant is not None and self.grant_id in self.env.revoked:
            self._discard()
            self.env.emit(ep, "CL-REFUSED", actor=self.actor, action=action)
            raise Refused("RF-REVOKED", msg("RF-REVOKED", date=self.env.revoked[self.grant_id]))
        if action in SIGN_ONLY and self.actor != "clinician":
            self.env.emit(ep, "CL-REFUSED", actor=self.actor, action=action)
            raise Refused(SIGN_ONLY[action], msg(SIGN_ONLY[action]))
        if self.card["header"]["kind"] == "provider" and self.actor == "agent" and action not in PROVIDER_AGENT:
            self.env.emit(ep, "CL-REFUSED", actor=self.actor, action=action)
            raise Refused("RF-NOT-YOURS", code("not_yours"))
        if action not in ACTOR_ACTIONS[self.actor] and action not in SIGN_ONLY:
            self.env.emit(ep, "CL-REFUSED", actor=self.actor, action=action)
            raise Refused("RF-NOT-YOURS", code("not_yours"))
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
            raise Refused("RF-NOT-YOURS", code("not_yours"))
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
        facts = [f for f in self.card["facts"] if f["field"] == field] or [{"field": field, "value": "none"}]
        e = {"id": len(self.env.queue) + 1, "episode": ep, "route": route(facts[0]), "kind": "alert",
             "status": "open", "at": self.env.now}
        self.env.queue.append(e)
        self.env.emit(ep, "queued", entry=e["id"])
        return e["id"]

    def _answer(self, ep, question, value):
        if not isinstance(value, bool):
            raise _free("answer")
        for e in self.env.queue:
            if e.get("question") == question and e["episode"] == ep and e["status"] != "declined":
                if self.actor != "patient":
                    return e["id"]
        status = "confirmed" if self.actor == "patient" else "unconfirmed"
        e = {"id": len(self.env.queue) + 1, "episode": ep, "route": QUESTION_ROUTE.get(question, "same_day"),
             "kind": "answer", "question": question, "value": value, "by": self.actor, "status": status,
             "line": msg(f"ST-{status.upper()}"), "at": self.env.now}
        self.env.queue.append(e)
        self.env.emit(ep, "answered", question=question, by=self.actor)
        return e["id"]

    def _decline(self, ep, question):
        """The patient's own decline overrides any answer given for them."""
        hit = [e for e in self.env.queue if e.get("question") == question and e["episode"] == ep]
        for e in hit:
            e["status"], e["line"] = "declined", msg("ST-DECLINED")
        if not hit:
            self.env.queue.append({"id": len(self.env.queue) + 1, "episode": ep,
                                   "route": QUESTION_ROUTE.get(question, "same_day"),
                                   "kind": "answer", "question": question, "by": "patient", "status": "declined",
                                   "line": msg("ST-DECLINED"), "at": self.env.now})
        self.env.emit(ep, "CL-DECLINED", question=question)
        return True

    def _flag(self, ep, field, value=None):
        """Patient flags a fact as wrong (or says one is missing). Goes to the item's own alert_route."""
        same = [f for f in self.card["facts"] if f["field"] == field]
        facts = [f for f in same if value is None or f["value"] == value]
        if facts:
            f = facts[0]
            f["flag"] = "patient"
            st, val = None, f["value"]
        else:
            _typed(LABEL[field].lower(), value, allowed=VALUES[field])
            for x in same:
                x["flag"] = "patient"
            f = {"field": field, "value": value}
            st, val = msg("ST-CHANGED"), value
        label = msg(f"FD-{LABEL[field]}-CLIN")
        e = {"id": len(self.env.queue) + 1, "episode": ep, "route": route(f), "kind": "flag", "field": field,
             "status": "open", "line": msg("CQ-FACT-FLAGGED", label=label, value=val), "st": st, "at": self.env.now}
        self.env.queue.append(e)
        self.env.emit(ep, "flagged", entry=e["id"])
        return msg("FL-WRONG-DONE-PT")

    def _review(self, ep, entry):
        for e in self.env.queue:
            if e["id"] == entry:
                e["reviewed"] = True
        return True

    def _revoke(self, ep, grant_id):
        if grant_id not in self.card["grants"]:
            raise Refused("RF-NOT-YOURS", code("not_yours"))
        self.env.revoked[grant_id] = self.env.now
        self.env.notices.append(("PV-REVOKE-LIST", msg("PV-REVOKE-LIST", agent_name=self.card["grants"][grant_id]["agent_name"],
                                                       date=self.env.now)))
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
                if f["source"] == "on_behalf":
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
        for g in self.card["grants"].values():
            if "rel" in g:
                out += [msg("FD-ACTS-FOR-PT"), msg(f"REL-{g['rel'].upper()}-PT"), g["person_name"]]
        ep_ = self.card["header"]["episode_id"]
        for e in self.env.queue:
            alert = e["kind"] == "flag" or e.get("value") is True or e["status"] == "declined"
            if e["episode"] == ep_ and alert and e["route"] in PATIENT_ROUTE_LINE:
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
