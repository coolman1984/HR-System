"""The date "today" for every rule of the registry (the line between history and the plan), and the one way to move it.

Normally it is the computer's date. A simulation (the scenario engine that plays a company through months in minutes,
`complete-company/scenario`) needs a controlled date, so it may be set, but only when the server was started with
HR_SIMULATION=1: an installed program never has the switch, so its "today" can never be put back. The locked attendance
engine is not touched: it receives its dates as data.
Standard library only.
"""

import os
from datetime import date, datetime

_override = None


class ClockError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def enabled():
    return os.environ.get("HR_SIMULATION") == "1"


def today():
    """The simulated date when one was set, else the date on this computer."""
    return _override or datetime.now().date().isoformat()


def set_today(day):
    """Move today (simulation only). The date must be a real YYYY-MM-DD."""
    global _override
    if not enabled():
        raise ClockError("clock.not_simulation", "the date can be moved only when the server runs in simulation (HR_SIMULATION=1)")
    try:
        date.fromisoformat(str(day))
    except ValueError:
        raise ClockError("clock.date", "today is a date YYYY-MM-DD") from None
    _override = str(day)
    return _override


def reset():
    """Back to the computer's date (tests)."""
    global _override
    _override = None
