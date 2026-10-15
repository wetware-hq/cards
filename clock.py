"""The one approved clock (same pattern as figures 4112225). Mode is set explicitly by the environment:
CARDS_CLOCK=test -> the scenario clock (the date the scenario supplies, else CARDS_SCENARIO_CLOCK);
CARDS_CLOCK=real -> the real clock. Anything else refuses with RF-CLOCK-UNSET (staff-only; signed text)."""
import os
from datetime import date


class ClockUnset(Exception):
    def __init__(self):
        from messages import msg
        self.line_id, self.text = "RF-CLOCK-UNSET", msg("RF-CLOCK-UNSET")
        super().__init__(self.line_id)


def today(scenario=None):
    mode = os.environ.get("CARDS_CLOCK")
    if mode == "real":
        return date.today().isoformat()
    scenario = scenario or os.environ.get("CARDS_SCENARIO_CLOCK")
    if mode == "test" and scenario:
        return scenario
    raise ClockUnset()
