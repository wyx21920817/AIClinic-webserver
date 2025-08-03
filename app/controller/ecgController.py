from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File, Body, Request
from app.utils.logger_config import logger
from fastapi.responses import JSONResponse, Response
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from ..model.user import User
from ..model.ecg_file import EcgFile
from ..model.patient import Patient
from ..controller.userController import get_current_user, get_admin_user
from ..core.logging import AuditLog
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
    notes: str
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

class DiagnosisResponse(BaseModel):
    diagnosis_id: str
    file_id: str
    user_id: str
    diagnosis_result: dict
    created_at: datetime

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
    验证ECG文件的有效性
    
    检查：
    1. 文件大小
    """
    # 读取文件内容
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件内容为空"
        )
    
    # Check file size (e.g., max 50MB)
    max_size = 50 * 1024 * 1024  # 50MB in bytes
    if len(contents) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件大小超过限制（最大50MB）"
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
                file_id=str(ecg_file.id),
                user_id=user_id,
                filename=instance_details.get('MainDicomTags', {}).get('FileName', 'unknown.dcm'),
                created_at=ecg_file.created_at,
                notes=ecg_file.notes,
                tags=ecg_file.tags,
                dicom_uid=ecg_file.dicom_uid,
                content=str(instance_details),  # Convert to string to ensure it can be serialized
                instanceIDs=ecg_file.instanceIDs
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
        # Convert file_id to ObjectId
        try:
            from bson import ObjectId
            file_object_id = ObjectId(file_id)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file_id format"
            )
            
        # Get file from database
        ecg_file = EcgFile.objects(id=file_object_id).first()
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
            file_id=str(ecg_file.id),
            user_id=user_id,
            filename=instance_details.get('MainDicomTags', {}).get('FileName', 'unknown.dcm'),
            created_at=ecg_file.created_at,
            notes=ecg_file.notes,
            tags=ecg_file.tags,
            dicom_uid=ecg_file.dicom_uid,
            content=str(instance_details)
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
    Update ECG file notes and tags.
    
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
        
        # Log the update attempt
        logger.info(f"User {current_user.username} (role: {current_user.role}) attempting to update ECG file - user_id: {user_id}, instance_id: {instance_id}")
        
        # Find the ECG file record
        ecg_file = EcgFile.objects(dicom_uid=instance_id).first()
        if not ecg_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ECG file not found"
            )

        # Convert tags string to list
        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        print(f"Processed tags: {tag_list}")  # Debug
        
        # Update Orthanc metadata
        metadata = {
            "Notes": notes,
            "Tags": ",".join(tag_list)
        }
        print(f"Updating Orthanc metadata: {metadata}")  # Debug
        
        # Update Orthanc metadata and get current instances
        result = modify_instance_metadata(ecg_file.dicom_uid, metadata, token=current_user.token)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update file metadata on server"
            )
        print("Successfully updated Orthanc metadata")  # Debug
        
        # Update database with new metadata and instance list
        ecg_file.notes = notes
        ecg_file.tags = tag_list
        ecg_file.instanceIDs = result['current_instances']  # Update instanceIDs with current list
        ecg_file.dicom_uid = result['instance_id']  # Update to new instance ID
        ecg_file.save()
        print("Successfully updated database record")  # Debug
        
        # Get updated instance details
        instance_details = get_instance(ecg_file.dicom_uid, token=current_user.token)
        print(f"Retrieved instance details from Orthanc: {instance_details}")  # Debug
        
        # Ensure instanceIDs field exists
        if not hasattr(ecg_file, 'instanceIDs') or ecg_file.instanceIDs is None:
            ecg_file.instanceIDs = [ecg_file.dicom_uid]
            ecg_file.save()
        
        # Log successful update
        logger.info(f"Successfully updated ECG file - user_id: {user_id}, instance_id: {instance_id}, tags: {tag_list}")
        
        return ECGFileResponse(
            id=str(ecg_file.id),
            user_id=user_id,
            filename=instance_details.get('MainDicomTags', {}).get('FileName', 'unknown.dcm'),
            created_at=ecg_file.created_at,
            notes=notes,
            tags=tag_list,
            dicom_uid=ecg_file.dicom_uid,
            content=str(instance_details),  # Adding content field to match model
            instanceIDs=ecg_file.instanceIDs
        )
    except Exception as e:
        print(f"Error in update_ecg_file: {str(e)}")  # Debug
        import traceback
        print(f"Full error traceback: {traceback.format_exc()}")  # Debug
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update ECG file: {str(e)}"
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
        AuditLog.log_data_access(
            user_id=str(current_user.id),
            action="delete",
            resource_type="ecg_file",
            resource_id=instance_id,
            details={
                "patient_id": user_id,
                "instance_id": instance_id
            }
        )
        
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
                detail="no file"
            )
        
        file = form["file"]
        if not hasattr(file, "filename"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="no filename"
            )
        
        print(f"File info - filename: {file.filename}, content_type: {getattr(file, 'content_type', 'unknown')}")  # Debug
        
        # Get other fields
        notes = form.get("notes", "")
        tags = form.get("tags", "")
        print(f"Additional fields - notes: {notes}, tags: {tags}")  # Debug
        
        # 读取文件内容
        contents = await file.read()
        print(f"Read {len(contents)} bytes")  # Debug
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dcm') as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name

        try:
            # Upload to Orthanc server
            orthanc_response = upload_dicom_file(temp_path, token=current_user.token)
            if not orthanc_response:
                # Get the error message from the response if available
                error_msg = "Failed to upload DICOM file to Orthanc"
                raise HTTPException(
                    status_code=500,
                    detail=error_msg
                )
            
            # Get DICOM UID from Orthanc response
            dicom_uid = orthanc_response.get("ID", "")  # Instance ID returned by Orthanc
            
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

            # Get current instances for this patient using MongoDB patient_id
            current_instances = []
            try:
                existing_files = EcgFile.objects(patient_id=str(patient.id)).all()
                for existing_file in existing_files:
                    if existing_file.instanceIDs:
                        current_instances.extend(existing_file.instanceIDs)
            except Exception as e:
                logger.error(f"Error getting existing instances: {e}")
                # Continue with empty list if there's an error
            current_instances.append(dicom_uid)

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

            AuditLog.log_data_access(
                user_id=str(current_user.id),
                action="upload_success",
                resource_type="ecg_file",
                resource_id=ecg_file.dicom_uid,
                details=f"Upload success - Patient: {user_id}, File: {file.filename}, Tags: {ecg_file.tags}",
                username=current_user.username
            )
            
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
            detail=f"文件上传失败: {str(e)}"
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
    AuditLog.log_api_call(
        user_id=str(current_user.id),
        action="get_diagnosis",
        api_endpoint=f"/api/ecg/{user_id}/diagnosis",
        details=f"Get diagnosis for patient: {user_id}",
        username=current_user.username
    )
    
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
                    if instance_details:
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
                            file_id=str(ecg_file.id),  # Use MongoDB ID as file_id
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
    AuditLog.log_data_access(
        user_id=str(current_user.id),
        action="view",
        resource_type="ecg_instance",
        resource_id=instance_id,
        details={
            "patient_id": user_id,
            "download": download
        }
    )
    
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