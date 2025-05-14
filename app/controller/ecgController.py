from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File, Body, Request
from fastapi.responses import JSONResponse, Response
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from ..model.user import User
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
    search_instances,
    get_instance_tags
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
    tags: List[str]
    dicom_uid: str
    content:str

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
    
    # 检查文件大小（例如：最大50MB）
    max_size = 50 * 1024 * 1024  # 50MB in bytes
    if len(contents) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件大小超过限制（最大50MB）"
        )
    
    # 将文件指针重置到开始位置
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
                content=str(instance_details)  # Convert to string to ensure it can be serialized
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

@router.put("/{user_id}/files/{file_id}", response_model=ECGFileResponse)
async def update_ecg_file(
    user_id: str,
    file_id: str,
    notes: str = Form(...),
    tags: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """
    Update ECG file notes and tags.
    
    Requires doctor or admin privileges.
    - **notes**: Notes about the ECG recording
    - **tags**: Tags for categorization (comma-separated string)
    """
    try:
        print(f"Updating ECG file - user_id: {user_id}, file_id: {file_id}")  # Debug
        
        await check_user_access(user_id, current_user)
        
        # Get file from database
        print(f"Searching for ECG file in database...")  # Debug
        ecg_file = EcgFile.objects(id=file_id, patient_id=user_id).first()
        if not ecg_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ECG file not found"
            )
        print(f"Found ECG file with dicom_uid: {ecg_file.dicom_uid}")  # Debug
        
        # Convert tags string to list
        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        print(f"Processed tags: {tag_list}")  # Debug
        
        # Update Orthanc metadata
        metadata = {
            "Notes": notes,
            "Tags": ",".join(tag_list)
        }
        print(f"Updating Orthanc metadata: {metadata}")  # Debug
        
        if not modify_instance_metadata(ecg_file.dicom_uid, metadata, token=current_user.token):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update file metadata on server"
            )
        print("Successfully updated Orthanc metadata")  # Debug
        
        # Update database
        ecg_file.notes = notes
        ecg_file.tags = tag_list
        ecg_file.save()
        print("Successfully updated database record")  # Debug
        
        # Get updated instance details
        instance_details = get_instance(ecg_file.dicom_uid, token=current_user.token)
        print(f"Retrieved instance details from Orthanc: {instance_details}")  # Debug
        
        return ECGFileResponse(
            file_id=str(ecg_file.id),
            user_id=user_id,
            filename=instance_details.get('MainDicomTags', {}).get('FileName', 'unknown.dcm'),
            created_at=ecg_file.created_at,
            notes=notes,
            tags=tag_list,
            dicom_uid=ecg_file.dicom_uid,
            content=str(instance_details)  # Adding content field to match model
        )
    except Exception as e:
        print(f"Error in update_ecg_file: {str(e)}")  # Debug
        import traceback
        print(f"Full error traceback: {traceback.format_exc()}")  # Debug
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update ECG file: {str(e)}"
        )

@router.delete("/{user_id}/files/{file_id}")
async def delete_ecg_file(
    user_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete an ECG file.
    
    Requires doctor or admin privileges.
    """
    await check_user_access(user_id, current_user)
    
    try:
        # Convert file_id to ObjectId
        try:
            file_object_id = ObjectId(file_id)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file_id format"
            )
        
        # Get file from database using only file_id
        ecg_file = EcgFile.objects(id=file_object_id).first()
        if not ecg_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ECG file not found"
            )
        
        # Store dicom_uid before deletion
        dicom_uid = ecg_file.dicom_uid
        
        # Delete from database first
        ecg_file.delete()
        
        # Then try to delete from Orthanc server
        # Even if this fails, we don't rollback the database deletion
        try:
            delete_instance(dicom_uid, token=current_user.token)
        except Exception as e:
            print(f"Warning: Failed to delete from Orthanc server: {str(e)}")
            # Don't raise exception here, as the file is already deleted from database
        
        return {"message": "File deleted successfully"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error deleting file: {str(e)}")
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
        
        # 获取其他字段
        notes = form.get("notes", "")
        tags = form.get("tags", "")
        print(f"Additional fields - notes: {notes}, tags: {tags}")  # Debug
        
        # 读取文件内容
        contents = await file.read()
        print(f"Read {len(contents)} bytes")  # Debug
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dcm') as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name

        try:
            # 上传到Orthanc服务器
            orthanc_response = upload_dicom_file(temp_path, token=current_user.token)
            if not orthanc_response:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to upload file to Orthanc server"
                )
            
            # 从Orthanc响应中获取DICOM UID
            dicom_uid = orthanc_response.get("ID", "")  # Orthanc返回的实例ID
            
            # 处理标签
            tag_list = []
            if tags:
                tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
                
            # 创建数据库记录
            patient = Patient.objects(id=user_id).first()
            if not patient:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="patient _NOT_FOUND"
                )
                
            ecg_file = EcgFile(
                patient_id=patient,
                dicom_uid=dicom_uid,
                uploaded_by=current_user,
                tags=tag_list,
                notes=notes
            )
            ecg_file.save()
            
            return {
                "file_id": str(ecg_file.id),
                "user_id": user_id,
                "filename": file.filename,
                "created_at": ecg_file.created_at.isoformat(),
                "original_filename": file.filename,
                "notes": notes,
                "tags": tag_list,
                "dicom_uid": dicom_uid
            }
        finally:
            # 清理临时文件
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