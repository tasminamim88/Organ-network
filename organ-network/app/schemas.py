"""Pydantic request/response models — the API contract."""

from __future__ import annotations

from typing import Optional, List, Literal
from pydantic import BaseModel, EmailStr, Field

BloodType = Literal["O", "A", "B", "AB"]
OrganType = Literal["kidney", "liver", "heart", "lung", "pancreas", "cornea", "intestine"]
Role = Literal["donor", "patient", "coordinator", "admin"]


# --- auth -------------------------------------------------------------------
class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    role: Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    created_at: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --- hospitals --------------------------------------------------------------
class HospitalCreate(BaseModel):
    name: str = Field(..., min_length=1)
    city: str = ""


class HospitalOut(BaseModel):
    id: int
    name: str
    city: str


# --- donors -----------------------------------------------------------------
class DonorCreate(BaseModel):
    name: str = Field(..., min_length=1)
    blood_type: BloodType
    age: Optional[int] = Field(None, ge=0, le=120)
    hospital_id: Optional[int] = None
    organs: List[OrganType] = Field(..., min_length=1)


class OrganOut(BaseModel):
    id: int
    donor_id: int
    organ_type: str
    status: str
    created_at: str


class DonorOut(BaseModel):
    id: int
    name: str
    blood_type: str
    age: Optional[int] = None
    hospital_id: Optional[int] = None
    status: str
    created_at: str
    organs: Optional[List[OrganOut]] = None


class AvailableOrganOut(BaseModel):
    id: int
    donor_id: int
    organ_type: str
    status: str
    donor_group: str
    donor_name: str
    created_at: str


# --- patients ---------------------------------------------------------------
class PatientCreate(BaseModel):
    name: str = Field(..., min_length=1)
    blood_type: BloodType
    organ_needed: OrganType
    urgency: int = Field(3, ge=1, le=5)
    hospital_id: Optional[int] = None


class PatientOut(BaseModel):
    id: int
    name: str
    blood_type: str
    organ_needed: str
    urgency: int
    hospital_id: Optional[int] = None
    status: str
    registered_at: str


# --- allocations ------------------------------------------------------------
class AllocateRequest(BaseModel):
    organ_id: int
    patient_id: int


class AllocationOut(BaseModel):
    id: int
    organ_id: int
    patient_id: int
    matched_by: Optional[int] = None
    status: str
    created_at: str
    organ_type: Optional[str] = None
    patient_name: Optional[str] = None
    donor_name: Optional[str] = None


class StatsOut(BaseModel):
    donors: int
    available_organs: int
    waiting_patients: int
    allocations: int
    transplants: int
