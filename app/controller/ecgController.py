from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Body, Request
from fastapi.param_functions import Form
from fastapi import Query
from app.utils.logger_config import logger
from app.core.config import settings
from fastapi.responses import JSONResponse, Response
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from ..model.user import User, UserRole
from ..model.audit_log import AuditLogEntry
from ..model.ecg_file import EcgFile
from ..model.patient import Patient
from ..controller.userController import get_current_user, get_admin_user

from ..controller.utils.orthanc import (
    upload_dicom_file, 
    get_instance, 
    get_instance_dicom,
    get_instance_waveform,
    modify_instance_metadata,
    delete_instance,
    get_instance_tags,
    get_patient_instances
)
import os
from pathlib import Path
import pydicom
import tempfile
from bson import ObjectId
import requests
import jwt
from ..core.config import settings

# Create ECG upload directory if it doesn't exist
ECG_UPLOAD_DIR = Path("app/static/uploads/ecg")
ECG_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(
    prefix="/api/ecg",
    tags=["ecg"],
    responses={404: {"description": "Not found"}}
)

class ECGFileResponse(BaseModel):
    file_id: str
    user_id: str
    filename: str
    created_at: datetime
    notes: str = ''
    tags: List[str] = []
    dicom_uid: str
    content: str = ''
    instanceIDs: List[str] = []

class PatientECGListResponse(BaseModel):
    total: int
    items: List[ECGFileResponse]
    tags: List[str]
    dicom_uid: str
    content: str
    instanceIDs: List[str]

    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "path/to/file.dat",
                "user_id": "67ff6f76b79960e20c753ed6",
                "filename": "ecg_record_2025_04_25.dat",
                "created_at": "2025-04-25T17:37:51",
                "notes": "Regular checkup",
                "tags": ["routine", "normal"],
                "dicom_uid": "1.2.3.4.5.6.7.8.9"
            }
        }

class ECGFileUpdate(BaseModel):
    notes: str
    tags: List[str]

class DiagnosisResult(BaseModel):
    original_dnn_model: Optional[Dict[str, float]] = None
    resnet_fine_tuned_model: Optional[Dict[str, float]] = None
    status: Optional[str] = None
    message: Optional[str] = None

class DiagnosisResponse(BaseModel):
    instance_id: str
    diagnosis_result: DiagnosisResult
    created_at: datetime
    status: str = Field(default='completed')

class InterpretationResponse(BaseModel):
    disease: str
    interpretation: List[str]
    example_images: List[Dict[str, str]]
    explanation: str = ''
    references: List[str] = []
    instance_id: str
    
    class Config:
        arbitrary_types_allowed = True

class UploadResponse(BaseModel):
    file_id: str
    user_id: str
    filename: str
    created_at: str
    original_filename: str
    notes: str
    tags: List[str]
    dicom_uid: str

async def check_user_access(user_id: str, current_user: User):
    pass

async def validate_ecg_file(file: UploadFile) -> bool:
    """
    Validate ECG file
    
    Checks:
    1. File size
    """
    # Read file content
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content is empty"
        )
    
    # Check file size (e.g., max 50MB)
    max_size = 50 * 1024 * 1024  # 50MB in bytes
    if len(contents) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds limit (max 50MB)"
        )
    
    # Reset file pointer to start
    await file.seek(0)
    return True

@router.get("/{user_id}/files", response_model=List[ECGFileResponse])
async def get_ecg_files(
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get list of ECG files for a specific patient.
    
    Requires doctor or admin privileges.
    """
    await check_user_access(user_id, current_user)
    
    # Log data access
    
    # Get files from database for this user
    ecg_files = EcgFile.objects(patient_id=user_id).all()
    responses = []
    for ecg_file in ecg_files:
        # Get instance details from Orthanc
        instance_details = get_instance(ecg_file.dicom_uid, token=current_user.token)
        if instance_details:
            responses.append(ECGFileResponse(
                file_id=str(ecg_file.dicom_uid),  # Use ID as file ID
                user_id=user_id,
                filename=instance_details.get('MainDicomTags', {}).get('FileName', 'unknown.dcm'),
                created_at=ecg_file.created_at,
                notes=ecg_file.notes if ecg_file.notes is not None else '',
                tags=ecg_file.tags if ecg_file.tags is not None else [],
                dicom_uid=ecg_file.dicom_uid,
                content=str(instance_details),  # Convert to string to ensure it can be serialized
                instanceIDs=ecg_file.instanceIDs if ecg_file.instanceIDs is not None else []
            ))
    
    return responses

@router.get("/{user_id}/files/{file_id}", response_model=ECGFileResponse)
async def get_ecg_file(
    user_id: str,
    file_id: str,
    download: bool = False,
    waveform: bool = False,
    current_user: User = Depends(get_current_user)
):
    """
    Get details of a specific ECG file.
    
    Requires doctor or admin privileges.
    
    Parameters:
    - download: If true, returns the raw DICOM file
    - waveform: If true, returns the ECG waveform data
    """
    await check_user_access(user_id, current_user)
    
    try:
        # Get file from database using dicom_uid
        ecg_file = EcgFile.objects(dicom_uid=file_id).first()
        if not ecg_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ECG file not found"
            )
    
        if download:
            # Get raw DICOM data
            dicom_data = get_instance_dicom(ecg_file.dicom_uid, token=current_user.token)
            if not dicom_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="DICOM file not found on server"
                )
            return Response(
                content=dicom_data,
                media_type="application/dicom",
                headers={
                    "Content-Disposition": f'attachment; filename="{ecg_file.dicom_uid}.dcm"'
                }
            )
            
        if waveform:
            # Get waveform data
            waveform_data = get_instance_waveform(ecg_file.dicom_uid, token=current_user.token)
            if not waveform_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No waveform data found in ECG file"
                )
            return JSONResponse(content=waveform_data)
        
        # Get instance details from Orthanc
        instance_details = get_instance(ecg_file.dicom_uid, token=current_user.token)
        if not instance_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File metadata not found on server"
            )
        
        return ECGFileResponse(
            file_id=str(ecg_file.dicom_uid),
            user_id=user_id,
            filename=instance_details.get('MainDicomTags', {}).get('FileName', 'unknown.dcm'),
            created_at=ecg_file.created_at,
            notes=ecg_file.notes,
            tags=ecg_file.tags,
            dicom_uid=ecg_file.dicom_uid,
            content=str(instance_details),
            instanceIDs=ecg_file.instanceIDs
        )
    except Exception as e:
        print(f"Error getting file: {str(e)}")
        import traceback
        print(f"Full error: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get file: {str(e)}"
        )

@router.put("/{user_id}/files/{instance_id}", response_model=ECGFileResponse)
async def update_ecg_file(
    user_id: str,
    instance_id: str,
    notes: str = Form(...),
    tags: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new ECG file record based on an existing one.
    The original ECG file remains unchanged, and a new record is created.
    
    Args:
        user_id: ID of the user who owns the file
        instance_id: Orthanc instance ID of the DICOM file
        notes: Notes about the ECG recording
        tags: Tags for categorization (comma-separated string)
        current_user: Current authenticated user
    
    Requires doctor or admin privileges.
    """
    try:
        await check_user_access(user_id, current_user)
        
        # Log the operation attempt
        logger.info(f"User {current_user.username} (role: {current_user.role}) attempting to create new ECG file based on existing - user_id: {user_id}, instance_id: {instance_id}")
        
        # Find the original ECG file record
        original_ecg_file = EcgFile.objects(dicom_uid=instance_id).first()
        if not original_ecg_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original ECG file not found"
            )

        # Convert tags string to list
        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        print(f"Processed tags: {tag_list}")  # Debug
        
        # Prepare metadata for the new instance
        metadata = {
            "Notes": notes,
            "Tags": ",".join(tag_list)
        }
        print(f"Setting metadata for new instance: {metadata}")  # Debug
        
        # Get instance details from Orthanc to create a new instance
        instance_details = get_instance(instance_id, token=current_user.token)
        if not instance_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Failed to retrieve instance details from server"
            )
        
        # Create a new instance with modified metadata
        result = modify_instance_metadata(instance_id, metadata, token=current_user.token)
        if not result or 'instance_id' not in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create new instance with updated metadata"
            )
        
        new_instance_id = result['instance_id']
        print(f"Created new instance with ID: {new_instance_id}")  # Debug
        
        # Get patient record
        patient = Patient.objects(id=user_id).first()
        if not patient:
            raise HTTPException(
                status_code=404,
                detail="Patient not found"
            )
        
        # Create a new ECG file record
        new_ecg_file = EcgFile(
            patient_id=str(patient.id),
            dicom_uid=new_instance_id,
            instanceIDs=[new_instance_id],  # Start with just the new instance
            notes=notes,
            tags=tag_list,
            uploaded_by=current_user.id
        )
        new_ecg_file.save()
        print(f"Created new ECG file record with ID: {str(new_ecg_file.id)}")  # Debug
        
        # Get updated instance details
        new_instance_details = get_instance(new_instance_id, token=current_user.token)
        print(f"Retrieved new instance details from Orthanc: {new_instance_details}")  # Debug
        
        # Log successful operation
        logger.info(f"Successfully created new ECG file - user_id: {user_id}, original_instance_id: {instance_id}, new_instance_id: {new_instance_id}, tags: {tag_list}")
        
        # Create audit log entry
        audit_log = AuditLogEntry(
            event_type="data_access",
            user_id=str(current_user.id),
            action="create_new_version",
            resource_type="ecg_file",
            resource_id=new_instance_id,
            details=f"Created new ECG file version - Patient: {user_id}, Original instance: {instance_id}, New instance: {new_instance_id}",
            status="success",
            username=current_user.username,
            request_info={"patient_id": user_id, "original_instance_id": instance_id, "new_instance_id": new_instance_id}
        )
        audit_log.save()
        
        return ECGFileResponse(
            id=str(new_ecg_file.id),
            user_id=user_id,
            filename=new_instance_details.get('MainDicomTags', {}).get('FileName', 'unknown.dcm'),
            created_at=new_ecg_file.created_at,
            notes=notes,
            tags=tag_list,
            dicom_uid=new_instance_id,
            content=str(new_instance_details),  # Adding content field to match model
            instanceIDs=[new_instance_id]
        )
    except Exception as e:
        print(f"Error in update_ecg_file: {str(e)}")  # Debug
        import traceback
        print(f"Full error traceback: {traceback.format_exc()}")  # Debug
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create new ECG file: {str(e)}"
        )

@router.delete("/{user_id}/files/{instance_id}")
async def delete_ecg_file(
    user_id: str,
    instance_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete an ECG file.
    
    Args:
        user_id: ID of the user who owns the file
        instance_id: Orthanc instance ID of the DICOM file
        current_user: Current authenticated user
    
    Requires doctor or admin privileges.
    """
    await check_user_access(user_id, current_user)
    
    try:
        # Log the deletion attempt
        logger.info(f"User {current_user.username} (role: {current_user.role}) attempting to delete ECG file - user_id: {user_id}, instance_id: {instance_id}")

        # Try to delete from database first
        try:
            ecg_file = EcgFile.objects(patient_id=user_id, dicom_uid=instance_id).first()
            if ecg_file:
                ecg_file.delete()
                logger.info(f"Successfully deleted ECG file record from database - user_id: {user_id}, instance_id: {instance_id}")
            else:
                logger.warning(f"No ECG file record found in database - user_id: {user_id}, instance_id: {instance_id}")
        except Exception as e:
            logger.error(f"Failed to delete ECG file record from database - user_id: {user_id}, instance_id: {instance_id}, error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete file record from database: {str(e)}"
            )

        # Then try to delete from Orthanc server
        try:
            success = delete_instance(instance_id, token=current_user.token)
            if not success:
                logger.error(f"Failed to delete instance from Orthanc - user_id: {user_id}, instance_id: {instance_id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to delete instance from Orthanc server"
                )
            logger.info(f"Successfully deleted ECG file from Orthanc - user_id: {user_id}, instance_id: {instance_id}")
        except Exception as e:
            logger.error(f"Failed to delete instance from Orthanc - user_id: {user_id}, instance_id: {instance_id}, error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete instance from Orthanc: {str(e)}"
            )
        
        # Log the successful deletion
        audit_log = AuditLogEntry(
            event_type="data_access",
            user_id=str(current_user.id),
            action="delete",
            resource_type="ecg_file",
            resource_id=instance_id,
            details=f"Deleted ECG file {instance_id} for patient {user_id}",
            status="success",
            username=current_user.username,
            request_info={"patient_id": user_id, "instance_id": instance_id}
        )
        audit_log.save()
        
        return {"message": "File deleted successfully"}
        
    except Exception as e:
        import traceback
        print(f"Full error: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}"
        )

@router.post("/{user_id}/files", response_model=UploadResponse)
async def upload_ecg_file(
    request: Request,
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    upload_ecg_file
    doctor or admin role
    """
    print("Starting file upload...")  # Debug
    await check_user_access(user_id, current_user)
    
    try:
        form = await request.form()
        print(f"Form data keys: {form.keys()}")  # Debug
        print(f"Complete form data: {dict(form)}")  # Debug
        
        if "file" not in form:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )
        
        file = form["file"]
        if not hasattr(file, "filename"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No filename"
            )
        
        print(f"File info - filename: {file.filename}, content_type: {getattr(file, 'content_type', 'unknown')}")  # Debug
        
        # Get other fields
        notes = form.get("notes", "")
        tags = form.get("tags", "")
        print(f"Additional fields - notes: {notes}, tags: {tags}")  # Debug
        
        # Read file content
        contents = await file.read()
        print(f"Read {len(contents)} bytes")  # Debug
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dcm') as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name

        try:
            # Upload to Orthanc server
            orthanc_response = upload_dicom_file(temp_path, token=current_user.token)
            if "error" in orthanc_response:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"File upload failed: {orthanc_response['error']}"
                )
            
            # Get DICOM UID from Orthanc response
            dicom_uid = orthanc_response.get("ID")
            if not dicom_uid:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"File upload failed: Unable to get instance ID"
                )
            
            # Process tags
            tag_list = []
            if tags:
                tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
                
            # Get patient record to get Orthanc patient_id
            patient = Patient.objects(id=user_id).first()
            if not patient:
                raise HTTPException(
                    status_code=404,
                    detail="Patient not found"
                )
            
            if not patient.patient_id:
                raise HTTPException(
                    status_code=400,
                    detail="Patient does not have an Orthanc ID"
                )

            # For new file upload, we only use the new instance ID
            current_instances = [dicom_uid]

            # Create or update ECG file record using MongoDB patient_id
            ecg_file = EcgFile(
                patient_id=str(patient.id),
                dicom_uid=dicom_uid,
                instanceIDs=current_instances,
                notes=notes,
                tags=tag_list,
                uploaded_by=current_user.id
            )
            ecg_file.save()

            audit_log = AuditLogEntry(
                event_type="data_access",
                user_id=str(current_user.id),
                action="upload_success",
                resource_type="ecg_file",
                resource_id=ecg_file.dicom_uid,
                details=f"Upload success - Patient: {user_id}, File: {file.filename}, Tags: {ecg_file.tags}",
                status="success",
                username=current_user.username,
                request_info={"patient_id": user_id, "filename": file.filename}
            )
            audit_log.save()
            
            return {
                "file_id": str(ecg_file.id),
                "user_id": user_id,
                "filename": file.filename,
                "created_at": ecg_file.created_at.isoformat(),
                "original_filename": file.filename,
                "notes": notes,
                "tags": tag_list,
                "dicom_uid": dicom_uid,
                "instanceIDs": current_instances
            }
        finally:
            # Clean up temporary files
            os.unlink(temp_path)
            
    except Exception as e:
        print(f"Error during file upload: {str(e)}")  # Debug
        import traceback
        print(f"Full error: {traceback.format_exc()}")  # Debug
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}"
        )

@router.get("/{user_id}/diagnosis", response_model=List[DiagnosisResponse])
async def get_diagnosis(
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get AI diagnosis results for a patient's ECG records.
    
    Requires doctor or admin privileges.
    """
    await check_user_access(user_id, current_user)
    
    # Log diagnosis API access
    audit_log = AuditLogEntry(
        event_type="data_access",
        user_id=str(current_user.id),
        action="get_diagnosis",
        resource_type="ecg_file",
        resource_id=user_id,
        details=f"Get diagnosis for patient: {user_id}",
        status="success",
        username=current_user.username,
        request_info={"patient_id": user_id}
    )
    audit_log.save()
    
    # TODO: Implement database query to get AI diagnosis results
    # This is a mock response
    return [
        DiagnosisResponse(
            diagnosis_id="456",
            file_id="123",
            user_id=user_id,
            diagnosis_result={
                "condition": "normal",
                "confidence": 0.95,
                "findings": []
            },
            created_at=datetime.now()
        )
    ]

@router.get("/patient/{patient_id}/files", response_model=List[ECGFileResponse])
async def get_patient_ecg_files(
    patient_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get all ECG files for a specific patient.
    
    This endpoint requires user authentication.
    """
    try:
        # Log data access attempt
        
        # Verify patient exists and has Orthanc ID
        try:
            from bson import ObjectId
            patient = Patient.objects(id=ObjectId(patient_id)).first()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid patient_id format"
            )
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found"
            )
        if not patient.patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient does not have an Orthanc ID"
            )

        # Get ECG files from database using MongoDB patient_id
        try:
            ecg_files_db = EcgFile.objects(patient_id=str(patient.id)).all()
            ecg_files = []
            for ecg_file in ecg_files_db:
                try:
                    instance_details = get_instance(ecg_file.dicom_uid, token=current_user.token)
                    if isinstance(instance_details, dict):
                        # Get instance creation time from DICOM tags
                        dicom_date = instance_details.get('MainDicomTags', {}).get('InstanceCreationDate')
                        dicom_time = instance_details.get('MainDicomTags', {}).get('InstanceCreationTime', '000000')
                        if '.' in dicom_time:  # Handle time format that may contain decimal points
                            dicom_time = dicom_time.split('.')[0]  # Only take hours, minutes, seconds part
                        
                        # Parse DICOM datetime format (YYYYMMDD HHMMSS)
                        try:
                            if dicom_date:
                                created_at = datetime.strptime(f"{dicom_date}{dicom_time}", '%Y%m%d%H%M%S')
                            else:
                                created_at = datetime.now()
                        except ValueError:
                            logger.warning(f"Invalid DICOM date/time format: {dicom_date} {dicom_time}. Using current time.")
                            created_at = datetime.now()
                            
                        ecg_files.append(ECGFileResponse(
                            file_id=str(ecg_file.dicom_uid),  # Use MongoDB ID as file_id
                            user_id=patient_id,
                            filename=instance_details.get('MainDicomTags', {}).get('FileName', 'unknown.dcm'),
                            created_at=created_at,
                            notes=ecg_file.notes,
                            tags=ecg_file.tags,
                            dicom_uid=ecg_file.dicom_uid,
                            content=str(instance_details),
                            instanceIDs=ecg_file.instanceIDs
                        ))
                except Exception as e:
                    logger.error(f"Error getting instance details for ECG file {ecg_file.dicom_uid}: {str(e)}")
                    continue
        except Exception as e:
            logger.error(f"Error getting ECG files from database: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get ECG files: {str(e)}"
            )

        return ecg_files

    except Exception as e:
        print(f"Error getting patient ECG files: {str(e)}")
        import traceback
        print(f"Full error: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get patient ECG files: {str(e)}"
        )



@router.post("/{user_id}/instances/{instance_id}/diagnose", response_model=DiagnosisResponse)
async def diagnose_ecg(
    user_id: str,
    instance_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Send ECG instance to AI server for diagnosis.
    
    Args:
        user_id: ID of the user who owns the ECG
        instance_id: Orthanc instance ID of the DICOM ECG file
        current_user: Current authenticated user
        
    Returns:
        DiagnosisResponse containing the AI diagnosis results
    """
    # Verify user access
    await check_user_access(user_id, current_user)
    
    # Log diagnosis request
    audit_log = AuditLogEntry(
        event_type="data_access",
        user_id=str(current_user.id),
        action="diagnose",
        resource_type="ecg_instance",
        resource_id=instance_id,
        details=f"Requested AI diagnosis for ECG instance {instance_id}, patient {user_id}",
        status="success",
        username=current_user.username,
        request_info={"patient_id": user_id}
    )
    audit_log.save()
    
    try:
        # Generate temporary token locally
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        # Generate JWT token with 5 minute expiry
        payload = {
            'exp': datetime.utcnow() + timedelta(minutes=5),
            'iat': datetime.utcnow(),
            'sub': str(current_user.id)
        }
        temp_token = jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
        logger.info("Successfully generated temporary token")
        
        # Send instance ID and token to AI server for diagnosis
        try:
            response = requests.post(
                f"{settings.aiserver_uri}/diagnose/{instance_id}",
                headers=headers,
                json={
                    'instance_id': instance_id,
                    'temp_token': temp_token
                },
                verify=False,
                timeout=30.0
            )
            response.raise_for_status()
            ai_response = response.json()
            
            # Extract data from AI response
            modified_instance_id = ai_response.get('modified_instance_id')
            predictions = ai_response.get('predictions', {})
            
            logger.info(f"Received AI diagnosis response with modified_instance_id: {modified_instance_id}")
            
            # Find the original ECG file record
            try:
                original_ecg_file = EcgFile.objects(dicom_uid=instance_id).first()
                if not original_ecg_file:
                    logger.error(f"ECG file not found for instance_id: {instance_id}")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="ECG file not found"
                    )
                
                # Create a new ECG file record with the modified instance ID
                if modified_instance_id:
                    # Create a new ECG file record
                    new_ecg_file = EcgFile(
                        patient_id=original_ecg_file.patient_id,
                        dicom_uid=modified_instance_id,
                        instanceIDs=[modified_instance_id],
                        notes=original_ecg_file.notes,
                        tags=original_ecg_file.tags,
                        uploaded_by=current_user.id,
                        diagnosis_result=predictions  # Store predictions as diagnosis result
                    )
                    new_ecg_file.save()
                    
                    logger.info(f"Created new ECG file record with modified_instance_id: {modified_instance_id}")
                    
                    # Create audit log entry for the new record
                    audit_log = AuditLogEntry(
                        event_type="data_access",
                        user_id=str(current_user.id),
                        action="create_diagnosis_version",
                        resource_type="ecg_file",
                        resource_id=modified_instance_id,
                        details=f"Created new ECG file with diagnosis - Patient: {user_id}, Original instance: {instance_id}, New instance: {modified_instance_id}",
                        status="success",
                        username=current_user.username,
                        request_info={"patient_id": user_id, "original_instance_id": instance_id, "new_instance_id": modified_instance_id}
                    )
                    audit_log.save()
                    
                    # Use the new ECG file for the response
                    ecg_file = new_ecg_file
                else:
                    # If no modified_instance_id is provided, update the original record
                    original_ecg_file.diagnosis_result = predictions
                    original_ecg_file.save()
                    ecg_file = original_ecg_file
                    
                    logger.info(f"Updated original ECG file {instance_id} with diagnosis result")
                
                # Return the diagnosis result from the appropriate ECG file
                # Use the AI server's predictions directly
                diagnosis_result = DiagnosisResult(
                    original_dnn_model=ecg_file.diagnosis_result.get('original_dnn_model'),
                    resnet_fine_tuned_model=ecg_file.diagnosis_result.get('resnet_fine_tuned_model'),
                    status="success",
                    message=f"Successfully diagnosed ECG instance: {instance_id}"
                )
            except Exception as e:
                logger.error(f"Failed to update ECG file with diagnosis result: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to save diagnosis result: {str(e)}"
                )
            
            return DiagnosisResponse(
                instance_id=modified_instance_id,
                diagnosis_result=diagnosis_result,
                created_at=datetime.now(),
                status='completed'
            )
            
        except requests.Timeout:
            logger.error("Diagnosis request timed out")
            raise HTTPException(status_code=504, detail="Diagnosis request timed out, please try again later")
        except requests.HTTPError as e:
            logger.error(f"Failed to get diagnosis. Status: {e.response.status_code}, Response: {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to diagnose: {e.response.text}"
            )
        except requests.RequestException as e:
            logger.error(f"Network error during diagnosis: {str(e)}")
            raise HTTPException(status_code=503, detail="Unable to connect to AI server, please check network connection")
            
    except Exception as e:
        logger.error(f"Error during ECG diagnosis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to diagnose: {str(e)}"
        )

@router.post("/interpretation/{instance_id}")
async def get_interpretation(
    instance_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get ECG interpretation and example images for multiple diseases.
    
    Args:
        instance_id: The Orthanc instance ID of the ECG file
        request: The request object containing form data with disease values
        current_user: Current authenticated user
    
    Form Data:
        disease: One or more disease values to get interpretations for. 
                To request multiple diseases, include multiple 'disease' fields in the form data.
                Available options: AF, 1dAVB, LBBB, RBBB, ST
                Default: AF
    
    Returns:
        List of JSON responses with analysis reports and image URLs for each disease.
        Each response contains:
        - analysis_report: Diagnostic criteria and interpretation
        - image_paths: URLs to example ECG images
        - instance_id: The original instance ID
        - disease: The disease name for this interpretation
    """
    # Verify user is a doctor or admin
    if current_user.role not in [UserRole.DOCTOR, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors and admins can access diagnostic criteria"
        )
    
    try:
        # Get form data
        form_data = await request.form()
        logger.info(f"Form data received: {dict(form_data)}")
        
        # Map disease abbreviations to directory names in ecg_analysis_results
        disease_map = {
            "AF": ["00001_lr_AF", "00234_lr_AF", "00279_lr_AF", "16731_hr_AF"],
            "1dAVB": ["00234_lr_1dAVB", "01484_hr_1dAVB"],
            "LBBB": ["03016_hr_LBBB", "15592_hr_LBBB"],
            "RBBB": ["03041_hr_RBBB"],
            "ST": ["04408_hr_ST"]
        }
        
        import random
        import json
        from pathlib import Path
        
        # Initialize list to store results for each disease
        results = []
        
        # Extract disease values from form data
        # When multiple form fields have the same name, we need to handle them specially
        # First, check if the form data contains multiple disease values
        disease_values = []
        for key, value in form_data.items():
            if key == 'disease':
                disease_values.append(value)
        
        # If no diseases were found, use the default
        if not disease_values:
            disease_values = ['AF']
        
        logger.info(f"Processing diseases: {disease_values}")
        
        # Process each disease
        for disease_name in disease_values:
            print('disease_name:',disease_name)
            # Use AF as default if the requested disease is not available
            if disease_name not in disease_map:
                disease_name = "AF"
            
            # Select a random directory for the disease (for variety)
            result_dirs = disease_map[disease_name]
            selected_dir = random.choice(result_dirs)
            
            # Path to the analysis report JSON file
            base_path = Path("app/static/ecg_analysis_results")
            report_path = base_path / selected_dir / "analysis_report.json"
            
            # Read the analysis report
            with open(report_path, "r") as f:
                report_data = json.load(f)
            
            # Update image paths to be full URLs with WEBSERVER_URI
            image_paths = []
            for img_path in report_data.get("image_paths", []):
                image_paths.append(f"{settings.WEBSERVER_URI}/static/ecg_analysis_results/{selected_dir}/{img_path}")
            
            # Update the report data with the full image paths
            report_data["image_paths"] = image_paths
            
            # Add instance_id and disease name to the response
            report_data["instance_id"] = instance_id
            report_data["disease"] = disease_name
            
            # Add this disease's report to the results list
            results.append(report_data)
        
        # Return the list of report data
        return results
            
    except Exception as e:
        import traceback
        logger.error(f"Error getting interpretation: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get interpretation: {str(e)}"
        )

@router.get("/{user_id}/instances/{instance_id}", response_model=ECGFileResponse)
async def get_ecg_instances_file(
    user_id: str,
    instance_id: str,
    download: bool = True,
    current_user: User = Depends(get_current_user)
):
    """
    Get details of a specific ECG file.
    
    Requires doctor or admin privileges.
    
    Parameters:
    - download: If true, returns the raw DICOM file
    - waveform: If true, returns the ECG waveform data
    """
    await check_user_access(user_id, current_user)
    
    # Log instance access
    audit_log = AuditLogEntry(
        event_type="data_access",
        user_id=str(current_user.id),
        action="view",
        resource_type="ecg_instance",
        resource_id=instance_id,
        details=f"Viewed ECG instance {instance_id} for patient {user_id}, download={download}",
        status="success",
        username=current_user.username,
        request_info={"download": download}
    )
    audit_log.save()
    
    try:
        if download:
            # Get raw DICOM data
            dicom_data = get_instance_dicom(instance_id, token=current_user.token)
            if not dicom_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="DICOM file not found on server"
                )
            return Response(
                content=dicom_data,
                media_type="application/dicom",
                headers={
                    "Content-Disposition": f'attachment; filename="{instance_id}.dcm"'
                }
            )
            

       
    except Exception as e:
        print(f"Error getting file: {str(e)}")
        import traceback
        print(f"Full error: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get file: {str(e)}"
        )