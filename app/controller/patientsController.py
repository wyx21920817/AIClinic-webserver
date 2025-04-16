from fastapi import APIRouter, Depends, HTTPException, status, Form
from typing import List, Optional
from datetime import datetime
from ..model.user import User, UserRole
from ..model.patient import Patient, Gender
from .userController import get_current_user, get_admin_user
from pydantic import BaseModel

# Router
router = APIRouter(
    prefix="/api",
    tags=["patients"],
    responses={404: {"description": "Not found"}}
)

class PatientCreate(BaseModel):
    patient_id: str
    name: str
    gender: Gender
    birth_date: datetime
    contact_info: dict = {}

class PatientUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[Gender] = None
    birth_date: Optional[datetime] = None
    contact_info: Optional[dict] = None

class PatientResponse(BaseModel):
    id: str
    patient_id: str
    name: str
    gender: Gender
    birth_date: datetime
    contact_info: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "patient_id": "P001",
                "name": "John Doe",
                "gender": "M",
                "birth_date": "1990-01-01T00:00:00",
                "contact_info": {
                    "phone": "1234567890",
                    "email": "john@example.com",
                    "address": "123 Main St"
                },
                "created_at": "2025-04-16T08:41:07",
                "updated_at": "2025-04-16T08:41:07"
            }
        }

@router.get("/patients", response_model=List[PatientResponse],
    summary="Get patient list",
    description="Get a list of all patients. Requires doctor or admin role.")
async def get_patients(current_user: User = Depends(get_current_user)):
    """
    Retrieve a list of all patients.

    This endpoint requires doctor or admin privileges.
    Returns a list of patients with their details.
    """
    if current_user.role not in [UserRole.DOCTOR, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Permission denied")

    patients = Patient.objects().all()
    return [
        PatientResponse(
            id=str(patient.id),
            patient_id=patient.patient_id,
            name=patient.name,
            gender=patient.gender,
            birth_date=patient.birth_date,
            contact_info=patient.contact_info,
            created_at=patient.created_at,
            updated_at=patient.updated_at
        ) for patient in patients
    ]

@router.get("/patients/{patient_id}", response_model=PatientResponse,
    summary="Get single patient details",
    description="Get details of a specific patient. Requires doctor or admin role.")
async def get_patient(patient_id: str, current_user: User = Depends(get_current_user)):
    """
    Retrieve details of a specific patient.

    This endpoint requires doctor or admin privileges.
    """
    if current_user.role not in [UserRole.DOCTOR, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Permission denied")

    patient = Patient.objects(patient_id=patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    return PatientResponse(
        id=str(patient.id),
        patient_id=patient.patient_id,
        name=patient.name,
        gender=patient.gender,
        birth_date=patient.birth_date,
        contact_info=patient.contact_info,
        created_at=patient.created_at,
        updated_at=patient.updated_at
    )

@router.post("/patients", response_model=PatientResponse,
    summary="Add patient information",
    description="Add new patient information. Requires doctor or admin role.")
async def create_patient(
    patient_id: str = Form(..., description="Unique patient ID"),
    name: str = Form(..., description="Patient name"),
    gender: Gender = Form(..., description="Patient gender (M/F/Other)"),
    birth_date: datetime = Form(..., description="Patient birth date"),
    contact_info: dict = Form({}, description="Patient contact information"),
    current_user: User = Depends(get_current_user)
):
    """
    Create new patient with the following information:

    - **patient_id**: Unique patient ID
    - **name**: Patient name
    - **gender**: Patient gender (M/F/Other)
    - **birth_date**: Patient birth date
    - **contact_info**: Patient contact information (optional)

    This endpoint requires doctor or admin privileges.
    """
    if current_user.role not in [UserRole.DOCTOR, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Permission denied")

    if Patient.objects(patient_id=patient_id).first():
        raise HTTPException(status_code=400, detail="Patient ID already exists")

    patient = Patient(
        patient_id=patient_id,
        name=name,
        gender=gender,
        birth_date=birth_date,
        contact_info=contact_info
    )
    patient.save()

    return PatientResponse(
        id=str(patient.id),
        patient_id=patient.patient_id,
        name=patient.name,
        gender=patient.gender,
        birth_date=patient.birth_date,
        contact_info=patient.contact_info,
        created_at=patient.created_at,
        updated_at=patient.updated_at
    )

@router.put("/patients/{patient_id}", response_model=PatientResponse,
    summary="Edit patient information",
    description="Edit patient information. Requires doctor or admin role.")
async def update_patient(
    patient_id: str,
    name: Optional[str] = Form(None, description="Patient name"),
    gender: Optional[Gender] = Form(None, description="Patient gender (M/F/Other)"),
    birth_date: Optional[datetime] = Form(None, description="Patient birth date"),
    contact_info: Optional[dict] = Form(None, description="Patient contact information"),
    current_user: User = Depends(get_current_user)
):
    """
    Update patient information. Can update:

    - **name**: Patient name
    - **gender**: Patient gender (M/F/Other)
    - **birth_date**: Patient birth date
    - **contact_info**: Patient contact information

    This endpoint requires doctor or admin privileges.
    """
    if current_user.role not in [UserRole.DOCTOR, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Permission denied")

    patient = Patient.objects(patient_id=patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if name is not None:
        patient.name = name
    if gender is not None:
        patient.gender = gender
    if birth_date is not None:
        patient.birth_date = birth_date
    if contact_info is not None:
        patient.contact_info = contact_info

    patient.save()

    return PatientResponse(
        id=str(patient.id),
        patient_id=patient.patient_id,
        name=patient.name,
        gender=patient.gender,
        birth_date=patient.birth_date,
        contact_info=patient.contact_info,
        created_at=patient.created_at,
        updated_at=patient.updated_at
    )

@router.delete("/patients/{patient_id}",
    summary="Delete patient",
    description="Delete a patient. Requires admin role.")
async def delete_patient(patient_id: str, current_user: User = Depends(get_admin_user)):
    """
    Delete a patient.

    This endpoint requires admin privileges.
    """
    patient = Patient.objects(patient_id=patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient.delete()
    return {"message": "Patient deleted successfully"}