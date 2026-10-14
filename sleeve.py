"""Card sleeve for a harness that hands out actor sessions (session(actor, role, patient, discipline, scope) ->
handle with observe/step/call). Each actor is loaded into one card first (simulated login): a patient card for
patient and patient_agent, a provider card for clinician and clinician_agent. The wrapped environment stays the
authority on grants, answers and safety; the sleeve adds identity, one-card-per-session, session end, and the
background-only rule for agents under a provider card. It never changes a call that it lets through."""
import cards
from messages import msg

PATIENT_ROLES = {"patient": "patient", "patient_agent": "agent"}
PROVIDER_ROLES = {"clinician": "clinician", "clinician_agent": "agent"}
STEP_SIGN = {"approve": "approve", "review": "close", "set_alert_route": "set_route", "sign": "sign_letter"}


def toml_card(header, facts=(), grants=()):
    """Write a card from typed values (dicts of str / list of str). load() re-checks every value."""
    def table(d):
        return "\n".join(f"{k} = {_v(v)}" for k, v in d.items())
    parts = ["[header]", table(header)]
    parts += [x for f in facts for x in ("[[fact]]", table(f))]
    parts += [x for g in grants for x in ("[[grant]]", table(g))]
    return "\n".join(parts) + "\n"


def _v(v):
    return "[" + ", ".join(_v(x) for x in v) + "]" if isinstance(v, (list, tuple)) else '"' + str(v) + '"'


class Sleeve:
    """cards_by_actor: actor id -> dict(text=card TOML, grant=grant id or None, agent_id=card agent id or None)."""

    def __init__(self, harness, env, cards_by_actor):
        self.h, self.env, self.cards = harness, env, dict(cards_by_actor)
        self.open_sessions = {}

    def session(self, actor, role, patient, discipline=None, scope=()):
        c = self.cards.get(actor)
        if c is None or actor in self.open_sessions:
            raise cards.Refused("RF-ONE-PROFILE", msg("RF-ONE-PROFILE"))
        card = cards.load(c["text"])
        kinds = PATIENT_ROLES if card["header"]["kind"] == "patient" else PROVIDER_ROLES
        if role not in kinds:
            raise cards.Refused("RF-REG-UNVERIFIED", msg("RF-REG-UNVERIFIED"))
        if card["header"]["kind"] == "provider" and role == "clinician" and discipline != card["header"]["discipline"]:
            raise cards.Refused("RF-REG-UNVERIFIED", msg("RF-REG-UNVERIFIED"))
        s = self.env.session(kinds[role], c.get("agent_id") or actor, c.get("grant"))
        s.open(c["text"])
        inner = self.h.session(actor, role, patient, discipline=discipline, scope=scope)
        self.open_sessions[actor] = s
        return Handle(inner, s, card["header"]["kind"])

    def end(self, actor):
        s = self.open_sessions.pop(actor, None)
        if s is not None:
            s.end()


class Handle:
    def __init__(self, inner, card_session, kind):
        self._inner, self._s, self._kind = inner, card_session, kind
        self.actor, self.role, self.patient = inner.actor, inner.role, inner.patient

    def _gate(self, action_type):
        if self._s.card is None:
            raise cards.Refused("RF-SESSION-ENDED", msg("RF-SESSION-ENDED"))
        if self._kind == "provider" and self._s.actor == "agent" and action_type in STEP_SIGN:
            line = cards.SIGN_ONLY[STEP_SIGN[action_type]]
            raise cards.Refused(line, msg(line))

    def observe(self, episode_id, *a, note=None):
        self._gate(None)
        return self._inner.observe(episode_id, *a, note=note)

    def step(self, episode_id, action, note=None):
        self._gate(action.get("type") if isinstance(action, dict) else None)
        return self._inner.step(episode_id, action, note=note)

    def call(self, episode_id, method, *a):
        self._gate(None)
        return self._inner.call(episode_id, method, *a)


class SleevedHarness:
    """The harness with session() routed through the sleeve; everything else is the harness itself."""

    def __init__(self, harness, sleeve):
        self._h, self._sleeve = harness, sleeve

    def session(self, actor, role, patient, discipline=None, scope=()):
        return self._sleeve.session(actor, role, patient, discipline, scope)

    def __getattr__(self, name):
        return getattr(self._h, name)
