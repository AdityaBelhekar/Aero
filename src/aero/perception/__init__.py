"""Aero's perception layer.

Tier 0 (this module today): near-free OS signals — the foreground window, its
process, and how long since the user last touched the machine. This alone drives
most of the world state (AERO-VIS-002 Tier 0) without any vision or model cost.
Tier 1 (screen frames/OCR) and Tier 2 (multimodal) arrive in Milestone 5.
"""

from aero.perception.tier0 import Tier0Sample, WorldStateProvider, sample_tier0

__all__ = ["Tier0Sample", "WorldStateProvider", "sample_tier0"]
