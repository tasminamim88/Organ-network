"""
Business logic — framework-independent.

Knows nothing about HTTP. Enforces the domain rules (roles, valid organ/blood
types, the matching constraints, no double-allocation) and raises typed domain
errors. The exact same logic is unit-tested directly against an in-memory
database, without a web server.
"""

from __future__ import annotations

from . import db, matching, security


# --- domain errors ----------------------------------------------------------
class DomainError(Exception):
    status = 400


class EmailTaken(DomainError):
    status = 409

    def __init__(self):
        super().__init__("An account with that email already exists.")


class InvalidCredentials(DomainError):
    status = 401

    def __init__(self):
        super().__init__("Incorrect email or password.")


class NotFound(DomainError):
    status = 404

    def __init__(self, what="Resource"):
        super().__init__(f"{what} not found.")


class PermissionDenied(DomainError):
    status = 403


class Conflict(DomainError):
    status = 409


ROLES = {"donor", "patient", "coordinator", "admin"}
STAFF = {"coordinator", "admin"}


def _public_user(u: dict) -> dict:
    return {k: v for k, v in u.items() if k != "password_hash"}


def _require(actor: dict, roles: set, msg: str):
    if actor["role"] not in roles:
        raise PermissionDenied(msg)


# --- auth -------------------------------------------------------------------
def register(conn, *, name, email, password, role) -> dict:
    if role not in ROLES:
        raise DomainError("Invalid role.")
    if len(password) < 6:
        raise DomainError("Password must be at least 6 characters.")
    if db.get_user_by_email(conn, email):
        raise EmailTaken()
    user = db.create_user(conn, name.strip(), email, security.hash_password(password), role)
    return _public_user(user)


def authenticate(conn, *, email, password) -> dict:
    user = db.get_user_by_email(conn, email)
    if not user or not security.verify_password(password, user["password_hash"]):
        raise InvalidCredentials()
    return _public_user(user)


# --- hospitals --------------------------------------------------------------
def add_hospital(conn, *, actor, name, city=""):
    _require(actor, STAFF, "Only staff can add hospitals.")
    if not name.strip():
        raise DomainError("Hospital name is required.")
    return db.create_hospital(conn, name.strip(), city.strip())


def list_hospitals(conn):
    return db.list_hospitals(conn)


# --- donors -----------------------------------------------------------------
def register_donor(conn, *, actor, name, blood_type, age, hospital_id, organs) -> dict:
    """A donor (or staff on their behalf) registers with pledged organs."""
    if blood_type not in matching.BLOOD_GROUPS:
        raise DomainError(f"Blood type must be one of {matching.BLOOD_GROUPS}.")
    bad = [o for o in organs if o not in matching.ORGAN_TYPES]
    if bad:
        raise DomainError(f"Unknown organ(s): {bad}. Allowed: {matching.ORGAN_TYPES}.")
    if not organs:
        raise DomainError("Pledge at least one organ.")

    user_id = actor["id"] if actor["role"] == "donor" else None
    donor = db.create_donor(
        conn, name=name.strip(), blood_type=blood_type, age=age,
        hospital_id=hospital_id, user_id=user_id,
    )
    for organ_type in organs:
        db.create_organ(conn, donor["id"], organ_type, status="pledged")
    return get_donor_detail(conn, donor["id"])


def make_donor_available(conn, *, actor, donor_id) -> dict:
    """
    Mark a donor's pledged organs as available for allocation. In the real
    world this corresponds to the point of donation/procurement, so only staff
    may do it.
    """
    _require(actor, STAFF, "Only staff can release organs into the pool.")
    donor = db.get_donor(conn, donor_id)
    if not donor:
        raise NotFound("Donor")
    db.set_donor_status(conn, donor_id, "available")
    db.set_organs_status_for_donor(conn, donor_id, "pledged", "available")
    return get_donor_detail(conn, donor_id)


def get_donor_detail(conn, donor_id) -> dict:
    donor = db.get_donor(conn, donor_id)
    if not donor:
        raise NotFound("Donor")
    organs = [
        dict(o)
        for o in conn.execute(
            "SELECT * FROM organs WHERE donor_id=? ORDER BY id", (donor_id,)
        ).fetchall()
    ]
    donor["organs"] = organs
    return donor


def list_donors(conn):
    return db.list_donors(conn)


# --- patients ---------------------------------------------------------------
def register_patient(conn, *, actor, name, blood_type, organ_needed, urgency, hospital_id) -> dict:
    if blood_type not in matching.BLOOD_GROUPS:
        raise DomainError(f"Blood type must be one of {matching.BLOOD_GROUPS}.")
    if organ_needed not in matching.ORGAN_TYPES:
        raise DomainError(f"Organ must be one of {matching.ORGAN_TYPES}.")
    if not (1 <= int(urgency) <= 5):
        raise DomainError("Urgency must be between 1 (low) and 5 (critical).")
    user_id = actor["id"] if actor["role"] == "patient" else None
    return db.create_patient(
        conn, name=name.strip(), blood_type=blood_type, organ_needed=organ_needed,
        urgency=int(urgency), hospital_id=hospital_id, user_id=user_id,
    )


def waitlist(conn):
    return db.list_patients(conn, status="waiting")


def available_organs(conn):
    return db.list_available_organs(conn)


# --- matching + allocation --------------------------------------------------
def candidates_for_organ(conn, *, actor, organ_id) -> list[dict]:
    """Preview the ranked compatible patients for an available organ."""
    _require(actor, STAFF, "Only staff can run matching.")
    organ = db.get_organ(conn, organ_id)
    if not organ:
        raise NotFound("Organ")
    if organ["status"] != "available":
        raise Conflict("Organ is not available for matching.")
    return matching.rank_candidates(organ, db.list_patients(conn, status="waiting"))


def allocate(conn, *, actor, organ_id, patient_id) -> dict:
    """Assign an available organ to a compatible waiting patient."""
    _require(actor, STAFF, "Only staff can allocate organs.")
    organ = db.get_organ(conn, organ_id)
    if not organ:
        raise NotFound("Organ")
    if organ["status"] != "available":
        raise Conflict("Organ is not available.")
    patient = db.get_patient(conn, patient_id)
    if not patient:
        raise NotFound("Patient")
    if patient["status"] != "waiting":
        raise Conflict("Patient is not on the waiting list.")
    if not matching.is_match(
        donor_group=organ["donor_group"], organ_type=organ["organ_type"],
        patient_group=patient["blood_type"], organ_needed=patient["organ_needed"],
        patient_status=patient["status"],
    ):
        raise Conflict("Organ and patient are not compatible (organ type or blood group).")

    alloc = db.create_allocation(conn, organ_id, patient_id, actor["id"])
    db.set_organ_status(conn, organ_id, "allocated")
    db.set_patient_status(conn, patient_id, "matched")
    return alloc


def complete_transplant(conn, *, actor, allocation_id) -> dict:
    _require(actor, STAFF, "Only staff can complete a transplant.")
    alloc = db.get_allocation(conn, allocation_id)
    if not alloc:
        raise NotFound("Allocation")
    if alloc["status"] != "allocated":
        raise Conflict("Allocation is not in an allocated state.")
    db.set_allocation_status(conn, allocation_id, "transplanted")
    db.set_organ_status(conn, alloc["organ_id"], "transplanted")
    db.set_patient_status(conn, alloc["patient_id"], "transplanted")
    return db.get_allocation(conn, allocation_id)


def list_allocations(conn):
    return db.list_allocations(conn)


def dashboard_stats(conn):
    return db.stats(conn)


# --- seeding ----------------------------------------------------------------
def seed_demo(conn):
    """Create demo hospitals + an admin account if the DB is empty."""
    if db.list_hospitals(conn):
        return
    for name, city in [
        ("Dhaka Medical College Hospital", "Dhaka"),
        ("Square Hospital", "Dhaka"),
        ("Chittagong Medical College", "Chattogram"),
    ]:
        db.create_hospital(conn, name, city)
    if not db.get_user_by_email(conn, "admin@organnet.local"):
        db.create_user(conn, "System Admin", "admin@organnet.local",
                       security.hash_password("admin123"), "admin")
