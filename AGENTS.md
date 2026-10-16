---
schema: wetware.agent.v1
resource: cards
version: 0.1.0
capabilities: [identity-card, session, sleeve]
inputs:
  card: {type: toml, constraint: "typed fields from fixed lists; free text refused; facts reference SYNTH-REC- source records"}
  grant: {type: object, fields: [grant_id, agent_id, agent_name, categories], constraint: "append-only history: granted, revoked, expired"}
  session: {type: object, fields: [actor, actor_id, grant_id], actors: [agent, decision_maker, patient, clinician]}
outputs:
  header: {type: text, constraint: "built from typed fields only"}
  outbox: {type: list, constraint: "unfinished drafts are discarded, never sent"}
  log: {type: list, constraint: "episode log, scenario clock"}
---

# Agent contract

Normative rules for agents that operate or modify cards. Wording uses RFC 2119: **MUST**, **MUST NOT**, **SHOULD**. Not approved for real patient data.

## Data handling

1. All data **MUST** be synthetic: `SYNTH-` ids, 1930s dates, initial-style invented names.
2. If real patient data appears, the agent **MUST** stop, **MUST NOT** repeat or process it, and **MUST** tell the user to report a privacy incident.
3. A card **MUST NOT** copy a fact; it **MUST** reference the source record.

## Operating the environment

1. An agent **MUST** load exactly one card per session and act only through `Session.step(action, ...)`, or through a harness wrapped by `sleeve.py`.
2. An agent **MUST** see only the categories its grant names; `mental_health` and `sexual_health` items **MUST** stay hidden without an explicit grant.
3. A refused step is final. The agent **MUST NOT** retry it with another card, grant or wording.
4. When a session ends or a grant ends, unfinished drafts **MUST** be dropped, not sent.
5. Traces C01-C14 **MUST** be scored only against `$CARDS_TRUTH/<id>/truth.toml`; without one the result is `BLOCKED-NO-TRUTH`.

## Changing code

- `python3 -m pytest -q` and `python3 scripts/rulecheck.py` **MUST** exit 0 before every commit; `scripts/prepush.py` runs as the pre-push hook.
- Every string a person sees **MUST** come from `WORDING.md`, regenerated only by `scripts/sync_wording.py` from the signed tables. `messages.py` **MUST NOT** hold wording.
- Changes to functions in `safety_functions.toml` **MUST** be followed by `python3 scripts/mutate.py`, which **MUST** kill every mutant.
- Standard library only.

## Out of scope

- Real patient data, hosted logins, clinical advice
- Signing wording or writing answer files
