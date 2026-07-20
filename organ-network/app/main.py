"""
Organ Donation & Procurement Network Management System — REST API (FastAPI).

Thin HTTP layer: validate input (Pydantic) -> resolve the current user from a
Bearer token -> delegate to the tested `service` layer -> map domain errors to
HTTP status codes. All real logic lives in `service` and `matching`.

Endpoints
    POST /auth/register | /auth/login | GET /auth/me
    GET/POST /hospitals
    GET/POST /donors,  POST /donors/{id}/release,  GET /donors/{id}
    GET/POST /patients        (GET = waiting list)
    GET  /organs/available
    GET  /organs/{id}/candidates      (matching preview)
    POST /allocations                 (allocate organ -> patient)
    POST /allocations/{id}/transplant
    GET  /allocations
    GET  /stats
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, security, service
from .schemas import (
    AllocateRequest, AllocationOut, AvailableOrganOut, DonorCreate, DonorOut,
    HospitalCreate, HospitalOut, LoginRequest, PatientCreate, PatientOut,
    RegisterRequest, StatsOut, TokenOut, UserOut,
)

app = FastAPI(
    title="Organ Donation & Procurement Network Management System",
    version="1.0.0",
    description="Register donors and patients, match organs by medical "
                "compatibility, and track allocation and transplantation.",
)

_conn = db.connect(config.DATABASE_PATH)
db.init_db(_conn)
if config.SEED_DEMO:
    service.seed_demo(_conn)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _raise(err: service.DomainError):
    raise HTTPException(status_code=err.status, detail=str(err))


def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = security.decode_access_token(token, config.SECRET_KEY)
    except security.TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    user = db.get_user_by_id(_conn, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists.")
    return user


def _issue_token(user: dict) -> TokenOut:
    token = security.create_access_token(
        str(user["id"]), config.SECRET_KEY, role=user["role"],
        expires_minutes=config.ACCESS_TOKEN_MINUTES,
    )
    public = {k: v for k, v in user.items() if k != "password_hash"}
    return TokenOut(access_token=token, user=UserOut(**public))


# --- auth -------------------------------------------------------------------
@app.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterRequest):
    try:
        user = service.register(_conn, name=body.name, email=body.email,
                                 password=body.password, role=body.role)
    except service.DomainError as exc:
        _raise(exc)
    return _issue_token(db.get_user_by_id(_conn, user["id"]))


@app.post("/auth/login", response_model=TokenOut)
def login(body: LoginRequest):
    try:
        user = service.authenticate(_conn, email=body.email, password=body.password)
    except service.DomainError as exc:
        _raise(exc)
    return _issue_token(db.get_user_by_id(_conn, user["id"]))


@app.get("/auth/me", response_model=UserOut)
def me(user=Depends(current_user)):
    return UserOut(**{k: v for k, v in user.items() if k != "password_hash"})


# --- hospitals --------------------------------------------------------------
@app.get("/hospitals", response_model=List[HospitalOut])
def hospitals():
    return service.list_hospitals(_conn)


@app.post("/hospitals", response_model=HospitalOut, status_code=201)
def add_hospital(body: HospitalCreate, user=Depends(current_user)):
    try:
        return service.add_hospital(_conn, actor=user, name=body.name, city=body.city)
    except service.DomainError as exc:
        _raise(exc)


# --- donors -----------------------------------------------------------------
@app.get("/donors", response_model=List[DonorOut])
def list_donors():
    return service.list_donors(_conn)


@app.post("/donors", response_model=DonorOut, status_code=201)
def create_donor(body: DonorCreate, user=Depends(current_user)):
    try:
        return service.register_donor(
            _conn, actor=user, name=body.name, blood_type=body.blood_type,
            age=body.age, hospital_id=body.hospital_id, organs=body.organs,
        )
    except service.DomainError as exc:
        _raise(exc)


@app.get("/donors/{donor_id}", response_model=DonorOut)
def donor_detail(donor_id: int):
    try:
        return service.get_donor_detail(_conn, donor_id)
    except service.DomainError as exc:
        _raise(exc)


@app.post("/donors/{donor_id}/release", response_model=DonorOut)
def release_donor(donor_id: int, user=Depends(current_user)):
    try:
        return service.make_donor_available(_conn, actor=user, donor_id=donor_id)
    except service.DomainError as exc:
        _raise(exc)


# --- patients ---------------------------------------------------------------
@app.get("/patients", response_model=List[PatientOut])
def waitlist():
    return service.waitlist(_conn)


@app.post("/patients", response_model=PatientOut, status_code=201)
def create_patient(body: PatientCreate, user=Depends(current_user)):
    try:
        return service.register_patient(
            _conn, actor=user, name=body.name, blood_type=body.blood_type,
            organ_needed=body.organ_needed, urgency=body.urgency,
            hospital_id=body.hospital_id,
        )
    except service.DomainError as exc:
        _raise(exc)


# --- matching + allocation --------------------------------------------------
@app.get("/organs/available", response_model=List[AvailableOrganOut])
def available_organs():
    return service.available_organs(_conn)


@app.get("/organs/{organ_id}/candidates", response_model=List[PatientOut])
def candidates(organ_id: int, user=Depends(current_user)):
    try:
        return service.candidates_for_organ(_conn, actor=user, organ_id=organ_id)
    except service.DomainError as exc:
        _raise(exc)


@app.post("/allocations", response_model=AllocationOut, status_code=201)
def allocate(body: AllocateRequest, user=Depends(current_user)):
    try:
        return service.allocate(_conn, actor=user, organ_id=body.organ_id,
                                patient_id=body.patient_id)
    except service.DomainError as exc:
        _raise(exc)


@app.post("/allocations/{allocation_id}/transplant", response_model=AllocationOut)
def transplant(allocation_id: int, user=Depends(current_user)):
    try:
        return service.complete_transplant(_conn, actor=user, allocation_id=allocation_id)
    except service.DomainError as exc:
        _raise(exc)


@app.get("/allocations", response_model=List[AllocationOut])
def allocations():
    return service.list_allocations(_conn)


@app.get("/stats", response_model=StatsOut)
def stats():
    return service.dashboard_stats(_conn)


# --- frontend ---------------------------------------------------------------
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(STATIC_DIR / "index.html"))
