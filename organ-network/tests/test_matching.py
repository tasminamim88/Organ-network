"""Exhaustive tests for the pure matching engine."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import matching


def test_abo_universal_donor_and_recipient():
    # O donates to everyone
    for r in matching.BLOOD_GROUPS:
        assert matching.abo_compatible("O", r)
    # AB receives from everyone
    for d in matching.BLOOD_GROUPS:
        assert matching.abo_compatible(d, "AB")


def test_abo_incompatible_pairs():
    assert not matching.abo_compatible("A", "B")
    assert not matching.abo_compatible("B", "A")
    assert not matching.abo_compatible("AB", "O")
    assert not matching.abo_compatible("A", "O")


def test_is_match_requires_all_conditions():
    base = dict(donor_group="O", organ_type="kidney",
                patient_group="A", organ_needed="kidney", patient_status="waiting")
    assert matching.is_match(**base)
    assert not matching.is_match(**{**base, "organ_needed": "liver"})   # wrong organ
    assert not matching.is_match(**{**base, "patient_status": "matched"})  # not waiting
    assert not matching.is_match(**{**base, "donor_group": "A", "patient_group": "O"})  # ABO


def test_ranking_urgency_then_wait_time():
    organ = {"organ_type": "kidney", "donor_group": "O"}
    patients = [
        {"id": 1, "blood_type": "A", "organ_needed": "kidney", "status": "waiting",
         "urgency": 3, "registered_at": "2026-01-01"},
        {"id": 2, "blood_type": "AB", "organ_needed": "kidney", "status": "waiting",
         "urgency": 5, "registered_at": "2026-02-01"},
        {"id": 3, "blood_type": "B", "organ_needed": "kidney", "status": "waiting",
         "urgency": 3, "registered_at": "2025-12-01"},  # same urgency, waited longer
    ]
    ranked = [p["id"] for p in matching.rank_candidates(organ, patients)]
    assert ranked == [2, 3, 1]


def test_ranking_excludes_incompatible():
    organ = {"organ_type": "kidney", "donor_group": "A"}
    patients = [
        {"id": 1, "blood_type": "O", "organ_needed": "kidney", "status": "waiting",
         "urgency": 5, "registered_at": "2026-01-01"},  # A cannot donate to O
        {"id": 2, "blood_type": "liver".upper() if False else "AB", "organ_needed": "kidney",
         "status": "waiting", "urgency": 1, "registered_at": "2026-01-01"},
    ]
    ranked = [p["id"] for p in matching.rank_candidates(organ, patients)]
    assert ranked == [2]  # only the AB patient is compatible with an A organ
