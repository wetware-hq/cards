# cards

Identity cards for patients and providers. An agent loads one card per session (a simulated login) to do
background work for that person. Synthetic data only (`SYNTH-` ids, 1930s dates, invented people). Not a medical
device and not approved for real patient data.

- `cards.py`: typed TOML cards, the environment (verified registrations, source records, clinician queue, outbox,
  episode log) and sessions. Free text is refused; facts are references to source records; the agent header is
  built from typed fields only.
- `sleeve.py`: wraps any harness that hands out `session(actor, role, patient, discipline, scope)` handles so each
  actor is loaded into a card first. Calls it lets through are unchanged.
- `traces.py`: scripted traces C01-C14. Scored only against frozen answer files in `$CARDS_TRUTH/<id>/truth.toml`
  (`[expect]` table); without one a trace is `BLOCKED-NO-TRUTH`.
- `messages.py` reads `WORDING.md`, generated from the signed tables by `scripts/sync_wording.py`.

```bash
python3 -m pytest -q                        # unit tests (TEST_SEED=n shuffles order)
python3 scripts/rulecheck.py                # every rule has a test; no prose outside WORDING.md
python3 scripts/mutate.py cards.py FUNCS sleeve.py FUNCS   # mutation testing, no exclusions
python3 scripts/sync_wording.py CARDS_SIGNED.md REUSED_SIGNED.md
python3 scripts/prepush.py CARDS_SIGNED.md REUSED_SIGNED.md # also the pre-push hook
```
