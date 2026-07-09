"""Versioned prompt/schema library (implementation plan W-4).

Consolidation quality depends on these prompts more than on code, so they live
in one place, are versioned, and are exercised by the spikes/tests. Bump the
``*_VERSION`` when a prompt changes so we can correlate memory quality with it.
"""

from aero.prompts.tagging import TAGGING_PROMPT, TAGGING_VERSION, tagging_messages

__all__ = ["TAGGING_PROMPT", "TAGGING_VERSION", "tagging_messages"]
