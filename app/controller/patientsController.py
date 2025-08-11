import requests
from fastapi import APIRouter, Depends, HTTPException, status, Form, Query
from typing import List, Optional, Union
from datetime import datetime
from typing import Optional, List
from app.controller.utils.orthanc import get_headers
from app.core.config import settings
from app.utils.logger_config import logger

ORTHANC_SERVER_URL = settings.ORTHANC_SERVER_URL
from ..model.user import User, UserRole
from ..model.patient import Patient
from ..model.doctor_patient import DoctorPatient
from ..model.ecg_file import EcgFile
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
    description="Get a paginated list of patients. Admins see all patients, doctors see only their patients.")
async def get_patients(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve a paginated list of patients.

    This endpoint requires doctor or admin privileges.
    - Admins see all patients in the system
    - Doctors see only patients associated with them in the DoctorPatient table
    Returns a paginated list of patients with their details.
    """
    if current_user.role not in [UserRole.DOCTOR, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Permission denied")

    # Different behavior based on user role
    if current_user.role == UserRole.ADMIN:
        # Admins see all patients
        total = Patient.objects().count()
        skip = (page - 1) * page_size
        patients = Patient.objects().skip(skip).limit(page_size)
    else:
        # Doctors only see their patients
        # First get all doctor-patient relationships for this doctor
        doctor_patients = DoctorPatient.objects(doctor=current_user.id)
        
        # Get the patient IDs from these relationships
        patient_ids = [dp.patient.id for dp in doctor_patients]
        
        # Get total count of doctor's patients
        total = len(patient_ids)
        
        # Apply pagination
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_ids = patient_ids[start_idx:end_idx] if start_idx < total else []
        
        # Get the actual patient objects
        if paginated_ids:
            patients = Patient.objects(id__in=paginated_ids)
        else:
            patients = []

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

    # Check if patient already exists
    existing_patient = Patient.objects(patient_id=patient_id).first()
    is_new_patient = False
    
    if existing_patient:
        patient = existing_patient
        logger.info(f"Patient with ID {patient_id} already exists, checking doctor-patient relationship")
    else:
        is_new_patient = True
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
        # Only process ECG files if this is a new patient
        if is_new_patient:
            # Check for existing ECG files in Orthanc
            from app.controller.utils.orthanc import get_patient_instances
            logger.info(f"[Patient Creation] Checking Orthanc for ECG files for patient ID: {patient_id}")
            
            instances = get_patient_instances(patient_id, current_user.token)
            logger.info(f"[Patient Creation] Found {len(instances) if instances else 0} instances in Orthanc")
            
            if instances:
                from ..model.ecg_file import EcgFile
                logger.info(f"[Patient Creation] Processing {len(instances)} instances from Orthanc")
                
                # Create ECG file records for each instance
                for instance in instances:
                    instance_id = instance.get('ID')
                    logger.info(f"[Patient Creation] Processing instance ID: {instance_id}")
                    
                    if instance_id:
                        # Check if ECG file record already exists
                        existing_ecg = EcgFile.objects(dicom_uid=instance_id).first()
                        if existing_ecg:
                            logger.info(f"[Patient Creation] ECG file record already exists for instance {instance_id}")
                        else:
                            logger.info(f"[Patient Creation] Creating new ECG file record for instance {instance_id}")
                            ecg_file = EcgFile(
                                patient_id=patient.id,
                                dicom_uid=instance_id,
                                uploaded_by=current_user.id,
                                instanceIDs=[instance_id]  # Store the instance ID
                            )
                            ecg_file.save()
                            logger.info(f"[Patient Creation] Successfully created ECG file record with ID: {str(ecg_file.id)}")
                            
                            # Log ECG file creation
                            AuditLog.log_data_access(
                                user_id=str(current_user.id),
                                action="create",
                                resource_type="ecg_file",
                                resource_id=str(ecg_file.id),
                                details=f"Created ECG file record for patient: {patient.name}",
                                username=current_user.username
                            )
                    else:
                        logger.warning(f"[Patient Creation] Instance missing ID: {instance}")
            else:
                logger.info(f"[Patient Creation] No ECG instances found in Orthanc for patient {patient_id}")
            
        # Always check and create doctor-patient relationship if needed
        if current_user.role == UserRole.DOCTOR:
            # Check if relationship already exists
            existing_relation = DoctorPatient.objects(doctor=current_user.id, patient=patient.id).first()
            if not existing_relation:
                logger.info(f"[Patient Creation] Creating doctor-patient relationship for doctor {current_user.username} and patient {patient.name}")
                doctor_patient = DoctorPatient(doctor=current_user.id, patient=patient.id)
                doctor_patient.save()
                
                # Log relationship creation
                AuditLog.log_data_access(
                    user_id=str(current_user.id),
                    action="create",
                    resource_type="doctor_patient",
                    resource_id=str(doctor_patient.id),
                    details=f"Added patient {patient.name} to doctor {current_user.username}'s list during import",
                    username=current_user.username
                )
            else:
                logger.info(f"[Patient Creation] Doctor-patient relationship already exists for doctor {current_user.username} and patient {patient.name}")
    except Exception as e:
        logger.error(f"[Patient Creation] Error handling ECG files for patient {patient_id}: {str(e)}")
        logger.error(f"[Patient Creation] Full error traceback:", exc_info=True)
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
    summary="Delete patient or doctor-patient relationship",
    description="For doctors: Remove doctor-patient relationship. For admins: Delete patient if no other doctor relationships exist.")
async def delete_patient(patient_id: str, current_user: User = Depends(get_current_user)):
    """
    Delete a patient or doctor-patient relationship.

    Different behavior based on role:
    - For doctors: Only removes the doctor-patient relationship, not the patient record
    - For admins: Can delete the patient record, but only if no other doctors have a relationship with this patient
    """
    if current_user.role not in [UserRole.DOCTOR, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Permission denied")

    patient = Patient.objects(patient_id=patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_name = patient.name
    
    # Different behavior based on user role
    if current_user.role == UserRole.DOCTOR:
        # For doctors: Only delete the relationship, not the patient
        doctor_patient = DoctorPatient.objects(doctor=current_user.id, patient=patient.id).first()
        if not doctor_patient:
            raise HTTPException(status_code=404, detail="This patient is not in your list")
        
        # Delete only this doctor's relationship with the patient
        doctor_patient.delete()
        
        AuditLog.log_data_access(
            user_id=str(current_user.id),
            action="delete",
            resource_type="doctor_patient",
            resource_id=str(doctor_patient.id),
            details=f"Removed patient {patient_name} from doctor {current_user.username}'s list",
            username=current_user.username
        )
        
        return {"message": f"Patient {patient_name} removed from your list successfully"}
    
    else:  # Admin role
        # Check if any doctor has a relationship with this patient
        doctor_patient_count = DoctorPatient.objects(patient=patient.id).count()
        if doctor_patient_count > 0:
            # Get the list of doctors who have a relationship with this patient
            doctor_relations = DoctorPatient.objects(patient=patient.id)
            doctor_usernames = []
            for relation in doctor_relations:
                doctor = User.objects(id=relation.doctor.id).first()
                if doctor:
                    doctor_usernames.append(doctor.username)
            
            doctors_list = ", ".join(doctor_usernames)
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot delete patient: {doctor_patient_count} doctors still have a relationship with this patient: {doctors_list}"
            )
        
        # If no doctor relationships exist, proceed with deletion
        # Delete associated ECG files
        ecg_files = EcgFile.objects(patient_id=patient)
        for ecg_file in ecg_files:
            try:
                # Delete ECG record from database only
                ecg_file.delete()
            except Exception as e:
                logger.error(f"Error deleting ECG file {ecg_file.dicom_uid} for patient {patient_id}: {str(e)}")
                # Continue with other deletions even if one fails
                continue
        
        # Delete patient record
        patient.delete()

        AuditLog.log_data_access(
            user_id=str(current_user.id),
            action="delete",
            resource_type="patient",
            resource_id=patient_id,
            details=f"Delete patient: {patient_name} with {ecg_files.count()} ECG records",
            username=current_user.username
        )

        return {"message": "Patient and associated records deleted successfully"}

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