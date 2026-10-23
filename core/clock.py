"""
core/clock.py -- The single source of "today" for all calculations.

Why this file exists:
  If each calculation asks the computer clock "what time is it?", the same
  data gives different answers on different days (coverage days shrink as
  the real date moves forward). That breaks the rule "same input, same output".

  Instead, every calculation receives ONE "as of" date. We use the day the
  disruption was detected -- that date is stored in the database, so the
  analysis of an event is the same today, tomorrow, or next year.
"""

from datetime import datetime


def as_of_for_event(event) -> datetime:
    """
    The reference date for analysing a disruption event:
    the event's detection date, at midnight.
    """
    return event.detected_at.replace(hour=0, minute=0, second=0, microsecond=0)
