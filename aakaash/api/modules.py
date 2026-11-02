# SOURCE: NOT IN PAPERS. Stage names and the module-to-stage assignment are as stated by the user
# (read from the team's architecture diagram; the image itself was not available to this code's
# author). This file is the single source of truth for the module list: the web app fetches it
# from /api/status and must not duplicate names or stages.
"""Modules that are not built. They appear as "coming soon" and carry no data."""
from __future__ import annotations

from dataclasses import dataclass

STAGE_NAMES = {
    1: "Input Understanding",
    2: "Information Extraction",
    3: "User Context Analysis",
    4: "AI Risk and Safety Engine",
    5: "Recommendation Engine",
    6: "Explanation Generator",
}
# Stages this web app covers (from the project brief: "restricted to my stages"). Not the whole design.
IN_SCOPE_STAGES = (2, 4, 5, 6)


@dataclass(frozen=True)
class ComingSoonModule:
    id: str
    label: str
    stages: tuple[int, ...]


COMING_SOON: tuple[ComingSoonModule, ...] = (
    ComingSoonModule("allergy_check", "Allergy Check", (4,)),
    ComingSoonModule("contraindication_check", "Contraindication Check", (4,)),
    ComingSoonModule("duplicate_therapy_check", "Duplicate Therapy Check", (3,)),
    ComingSoonModule("disease_precautions", "Disease Precautions", (4,)),
    ComingSoonModule("deep_learning_encoder", "Deep-learning encoder", (2, 5)),
)
