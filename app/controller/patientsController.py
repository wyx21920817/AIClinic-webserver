import requests
from fastapi import APIRouter, Depends, HTTPException, status, Form, Query
from typing import List, Optional
from datetime import datetime
from typing import Optional, List
from app.controller.utils.orthanc import get_headers
from app.core.config import settings
from app.utils.logger_config import logger

ORTHANC_SERVER_URL = settings.ORTHANC_SERVER_URL
from ..model.user import User, UserRole
from ..model.patient import Patient
from ..model.doctor_patient import DoctorPatient
from ..core.logging import AuditLog
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
    gender: str
    birth_date: datetime
    contact_info: dict = {}

class PatientUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[datetime] = None
    contact_info: Optional[dict] = None

class PatientResponse(BaseModel):
    id: str
    patient_id: str
    name: str
    gender: str
    birth_date: datetime
    contact_info: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
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

class PaginatedPatientResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[PatientResponse]

@router.get("/patients", response_model=PaginatedPatientResponse,
    summary="Get paginated patient list",
    description="Get a paginated list of all patients. Requires doctor or admin role.")
async def get_patients(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve a paginated list of all patients.

    This endpoint requires doctor or admin privileges.
    Returns a paginated list of patients with their details.
    """
    if current_user.role not in [UserRole.DOCTOR, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Permission denied")

    # Get total count
    total = Patient.objects().count()

    # Get paginated patients
    skip = (page - 1) * page_size
    patients = Patient.objects().skip(skip).limit(page_size)

    return PaginatedPatientResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[
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
    )

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
    gender: str = Form(..., description="Patient gender"),
    birth_date: datetime = Form(..., description="Patient birth date"),
    contact_info: dict = Form({}, description="Patient contact information"),
    current_user: User = Depends(get_current_user)
):
    """
    Create new patient with the following information:

    - **patient_id**: Unique patient ID
    - **name**: Patient name
    - **gender**: Patient gender
    - **birth_date**: Patient birth date
    - **contact_info**: Patient contact information (optional)

    This endpoint requires doctor or admin privileges.
    """
    if current_user.role not in [UserRole.DOCTOR, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Permission denied")

    if Patient.objects(patient_id=patient_id).first():
        raise HTTPException(status_code=400, detail="Patient ID already exists")

    # Create the patient record
    patient = Patient(
        patient_id=patient_id,
        name=name,
        gender=gender,
        birth_date=birth_date,
        contact_info=contact_info
    )
    patient.save()

    # Log patient creation
    AuditLog.log_data_access(
        user_id=str(current_user.id),
        action="create",
        resource_type="patient",
        resource_id=str(patient.id),
        details=f"Create new patient: {patient.name}",
        username=current_user.username
    )

    try:
        # Check for existing ECG files in Orthanc
        from app.controller.utils.orthanc import get_patient_instances
        instances = get_patient_instances(patient_id, current_user.token)
        
        if instances:
            from ..model.ecg_file import EcgFile
            # Create ECG file records for each instance
            for instance in instances:
                instance_id = instance.get('ID')
                if instance_id:
                    # Check if ECG file record already exists
                    existing_ecg = EcgFile.objects(dicom_uid=instance_id).first()
                    if not existing_ecg:
                        ecg_file = EcgFile(
                            patient_id=patient.id,
                            dicom_uid=instance_id,
                            uploaded_by=current_user.id,
                            instanceIDs=[instance_id]  # Store the instance ID
                        )
                        ecg_file.save()
                        
                        # Log ECG file creation
                        AuditLog.log_data_access(
                            user_id=str(current_user.id),
                            action="create",
                            resource_type="ecg_file",
                            resource_id=str(ecg_file.id),
                            details=f"Created ECG file record for patient: {patient.name}",
                            username=current_user.username
                        )
    except Exception as e:
        logger.error(f"Error handling ECG files for patient {patient_id}: {str(e)}")
        # Don't fail patient creation if ECG handling fails
        pass

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
    gender: Optional[str] = Form(None, description="Patient gender"),
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

    AuditLog.log_data_access(
        user_id=str(current_user.id),
        action="update",
        resource_type="patient",
        resource_id=patient_id,
        details=f"Update patient: {patient.name}",
        username=current_user.username
    )

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

    patient_name = patient.name
    patient.delete()

    AuditLog.log_data_access(
        user_id=str(current_user.id),
        action="delete",
        resource_type="patient",
        resource_id=patient_id,
        details=f"Delete patient: {patient_name}",
        username=current_user.username
    )

    return {"message": "Patient deleted successfully"}

@router.get("/orthanc/patients/search",
    summary="Search patients in Orthanc",
    description="Search patients in Orthanc PACS server by ID or name.")
async def search_orthanc_patients(
    query: str = Query(None, description="Patient ID or name to search for"),
    current_user: User = Depends(get_current_user)
):
    """
    Search for patients in Orthanc PACS server.
    Supports fuzzy search by patient ID or name.
    """
    from app.controller.utils.orthanc import search_patients
    
    try:
        results = search_patients(query, current_user.token)
        if not results and isinstance(results, list):
            return {"patients": [], "total": 0}
            
        return {"patients": results, "total": len(results)}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error searching patients in Orthanc: {str(e)}"
        )

@router.post("/doctors/patients/{patient_id}",
    summary="Add patient to doctor's list",
    description="Add a patient to the current doctor's patient list. Requires doctor role.")
async def add_patient_to_doctor(
    patient_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Add a patient to the doctor's patient list.

    This endpoint requires doctor privileges.
    """
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Only doctors can add patients to their list")

    # Check if patient exists
    patient = Patient.objects(patient_id=patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Check if relationship already exists
    existing_relation = DoctorPatient.objects(doctor=current_user.id, patient=patient.id).first()
    if existing_relation:
        raise HTTPException(status_code=400, detail="Patient is already in your list")

    # Create new relationship
    doctor_patient = DoctorPatient(doctor=current_user.id, patient=patient.id)
    doctor_patient.save()

    return {"message": "Patient added to your list successfully"}

@router.get("/doctors/patients",
    response_model=PaginatedPatientResponse,
    summary="Get doctor's patient list",
    description="Get the current doctor's patient list with pagination. Requires doctor role.")
async def get_doctor_patients(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve a paginated list of doctor's patients.

    This endpoint requires doctor privileges.
    """
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Only doctors can view their patient list")

    # Get total count
    total = DoctorPatient.objects(doctor=current_user.id).count()

    # Get paginated relationships
    skip = (page - 1) * page_size
    doctor_patients = DoctorPatient.objects(doctor=current_user.id).skip(skip).limit(page_size)

    # Get patient details
    patients = []
    for dp in doctor_patients:
        patient = Patient.objects(id=dp.patient.id).first()
        if patient:
            patients.append(PatientResponse(
                id=str(patient.id),
                patient_id=patient.patient_id,
                name=patient.name,
                gender=patient.gender,
                birth_date=patient.birth_date,
                contact_info=patient.contact_info,
                created_at=patient.created_at,
                updated_at=patient.updated_at
            ))

    return PaginatedPatientResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=patients
    )