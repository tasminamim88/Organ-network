"""End-to-end tests of the business logic against an in-memory database."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import db, service


@pytest.fixture()
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    service.seed_demo(c)
    yield c
    c.close()


@pytest.fixture()
def staff(conn):
    return service.register(conn, name="Coord", email="c@x.com",
                            password="pass12", role="coordinator")


@pytest.fixture()
def hospital(conn):
    return service.list_hospitals(conn)[0]


def _donor_with_kidney(conn, staff, hospital, blood="O"):
    return service.register_donor(conn, actor=staff, name="Donor", blood_type=blood,
                                  age=40, hospital_id=hospital["id"], organs=["kidney"])


# --- auth / seeding ---------------------------------------------------------
def test_seed_creates_admin_and_hospitals(conn):
    assert service.list_hospitals(conn)
    admin = service.authenticate(conn, email="admin@organnet.local", password="admin123")
    assert admin["role"] == "admin"


def test_duplicate_email_rejected(conn, staff):
    with pytest.raises(service.EmailTaken):
        service.register(conn, name="X", email="c@x.com", password="pass12", role="donor")


# --- donor registration -----------------------------------------------------
def test_register_donor_with_organs(conn, staff, hospital):
    d = service.register_donor(conn, actor=staff, name="Rahim", blood_type="A", age=30,
                               hospital_id=hospital["id"], organs=["kidney", "liver"])
    assert d["status"] == "registered"
    assert {o["organ_type"] for o in d["organs"]} == {"kidney", "liver"}
    assert all(o["status"] == "pledged" for o in d["organs"])


def test_invalid_blood_or_organ_rejected(conn, staff, hospital):
    with pytest.raises(service.DomainError):
        service.register_donor(conn, actor=staff, name="X", blood_type="Z", age=1,
                               hospital_id=hospital["id"], organs=["kidney"])
    with pytest.raises(service.DomainError):
        service.register_donor(conn, actor=staff, name="X", blood_type="O", age=1,
                               hospital_id=hospital["id"], organs=["spleen"])


def test_only_staff_can_release_organs(conn, staff, hospital):
    donor_user = service.register(conn, name="D", email="d@x.com", password="pass12", role="donor")
    d = _donor_with_kidney(conn, staff, hospital)
    with pytest.raises(service.PermissionDenied):
        service.make_donor_available(conn, actor=donor_user, donor_id=d["id"])
    service.make_donor_available(conn, actor=staff, donor_id=d["id"])
    assert len(service.available_organs(conn)) == 1


# --- matching + allocation --------------------------------------------------
def test_matching_preview_ranks_compatible_patients(conn, staff, hospital):
    d = _donor_with_kidney(conn, staff, hospital, blood="O")
    service.make_donor_available(conn, actor=staff, donor_id=d["id"])
    organ = service.available_organs(conn)[0]
    # two compatible patients, different urgency
    p_low = service.register_patient(conn, actor=staff, name="Low", blood_type="A",
                                     organ_needed="kidney", urgency=2, hospital_id=hospital["id"])
    p_high = service.register_patient(conn, actor=staff, name="High", blood_type="AB",
                                      organ_needed="kidney", urgency=5, hospital_id=hospital["id"])
    # incompatible: needs a different organ
    service.register_patient(conn, actor=staff, name="Other", blood_type="O",
                             organ_needed="liver", urgency=5, hospital_id=hospital["id"])
    ranked = service.candidates_for_organ(conn, actor=staff, organ_id=organ["id"])
    assert [c["id"] for c in ranked] == [p_high["id"], p_low["id"]]


def test_allocate_and_transplant_flow(conn, staff, hospital):
    d = _donor_with_kidney(conn, staff, hospital, blood="O")
    service.make_donor_available(conn, actor=staff, donor_id=d["id"])
    organ = service.available_organs(conn)[0]
    patient = service.register_patient(conn, actor=staff, name="P", blood_type="A",
                                       organ_needed="kidney", urgency=4, hospital_id=hospital["id"])
    alloc = service.allocate(conn, actor=staff, organ_id=organ["id"], patient_id=patient["id"])
    assert alloc["status"] == "allocated"
    # patient off the waiting list, organ no longer available
    assert patient["id"] not in [p["id"] for p in service.waitlist(conn)]
    assert not service.available_organs(conn)
    done = service.complete_transplant(conn, actor=staff, allocation_id=alloc["id"])
    assert done["status"] == "transplanted"
    assert service.dashboard_stats(conn)["transplants"] == 1


def test_incompatible_allocation_blocked(conn, staff, hospital):
    d = _donor_with_kidney(conn, staff, hospital, blood="A")  # A organ
    service.make_donor_available(conn, actor=staff, donor_id=d["id"])
    organ = service.available_organs(conn)[0]
    patient = service.register_patient(conn, actor=staff, name="P", blood_type="O",  # A->O invalid
                                       organ_needed="kidney", urgency=5, hospital_id=hospital["id"])
    with pytest.raises(service.Conflict):
        service.allocate(conn, actor=staff, organ_id=organ["id"], patient_id=patient["id"])


def test_double_allocation_blocked(conn, staff, hospital):
    d = _donor_with_kidney(conn, staff, hospital, blood="O")
    service.make_donor_available(conn, actor=staff, donor_id=d["id"])
    organ = service.available_organs(conn)[0]
    p1 = service.register_patient(conn, actor=staff, name="P1", blood_type="A",
                                  organ_needed="kidney", urgency=4, hospital_id=hospital["id"])
    p2 = service.register_patient(conn, actor=staff, name="P2", blood_type="A",
                                  organ_needed="kidney", urgency=4, hospital_id=hospital["id"])
    service.allocate(conn, actor=staff, organ_id=organ["id"], patient_id=p1["id"])
    with pytest.raises(service.Conflict):
        service.allocate(conn, actor=staff, organ_id=organ["id"], patient_id=p2["id"])


def test_patient_cannot_allocate(conn, staff, hospital):
    patient_user = service.register(conn, name="Pt", email="pt@x.com", password="pass12", role="patient")
    d = _donor_with_kidney(conn, staff, hospital, blood="O")
    service.make_donor_available(conn, actor=staff, donor_id=d["id"])
    organ = service.available_organs(conn)[0]
    patient = service.register_patient(conn, actor=staff, name="P", blood_type="A",
                                       organ_needed="kidney", urgency=4, hospital_id=hospital["id"])
    with pytest.raises(service.PermissionDenied):
        service.allocate(conn, actor=patient_user, organ_id=organ["id"], patient_id=patient["id"])
