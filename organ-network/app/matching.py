"""
The matching engine — the medical heart of the system.

Two rules decide whether a donated organ can go to a waiting patient:

  1. ORGAN TYPE must match what the patient needs.
  2. ABO BLOOD-GROUP COMPATIBILITY (the dominant factor in organ allocation):

        donor  ->  compatible recipients
        --------------------------------
        O      ->  O, A, B, AB   (universal donor)
        A      ->  A, AB
        B      ->  B, AB
        AB     ->  AB            (universal recipient)

When several patients are compatible, they are ranked the way real allocation
systems broadly do: highest medical urgency first, and for ties, the person who
has waited longest (earliest registration) first.

Note: this models ABO groups (O/A/B/AB). Real allocation also weighs HLA tissue
typing, Rh factor, organ size, geography, and ischemic time — deliberately out
of scope for this project, and called out here on purpose.

These are pure functions (no database, no framework), which makes the rules
trivial to unit-test exhaustively.
"""

from __future__ import annotations

from typing import Iterable

BLOOD_GROUPS = ("O", "A", "B", "AB")
ORGAN_TYPES = ("kidney", "liver", "heart", "lung", "pancreas", "cornea", "intestine")

# donor group -> set of recipient groups it can donate to
_DONOR_TO_RECIPIENT = {
    "O": {"O", "A", "B", "AB"},
    "A": {"A", "AB"},
    "B": {"B", "AB"},
    "AB": {"AB"},
}


def abo_compatible(donor_group: str, recipient_group: str) -> bool:
    """True if an organ from `donor_group` may be given to `recipient_group`."""
    return recipient_group in _DONOR_TO_RECIPIENT.get(donor_group, set())


def is_match(*, donor_group: str, organ_type: str,
             patient_group: str, organ_needed: str, patient_status: str) -> bool:
    """All conditions for a single organ->patient pairing to be valid."""
    return (
        patient_status == "waiting"
        and organ_type == organ_needed
        and abo_compatible(donor_group, patient_group)
    )


def rank_candidates(organ: dict, patients: Iterable[dict]) -> list[dict]:
    """
    Given one available `organ` (must include 'organ_type' and 'donor_group')
    and an iterable of patient dicts (with 'blood_type', 'organ_needed',
    'status', 'urgency', 'registered_at'), return the compatible patients
    ordered best-first.

    Sort key: urgency descending, then registration time ascending (longest
    wait first). A stable, deterministic ordering.
    """
    eligible = [
        p for p in patients
        if is_match(
            donor_group=organ["donor_group"],
            organ_type=organ["organ_type"],
            patient_group=p["blood_type"],
            organ_needed=p["organ_needed"],
            patient_status=p["status"],
        )
    ]
    eligible.sort(key=lambda p: (-int(p["urgency"]), str(p.get("registered_at", ""))))
    return eligible
