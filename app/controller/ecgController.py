from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File, Body, Request
from fastapi.responses import JSONResponse
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from ..model.user import User
from ..model.ecg_file import EcgFile
from ..model.patient import Patient
from ..controller.userController import get_current_user, get_admin_user
import os
from pathlib import Path
import pydicom

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
    
    # TODO: Implement database query to get ECG files
    # This is a mock response
    return [
        ECGFileResponse(
            file_id="123",
            user_id=user_id,
            filename="ecg_record_2025_04_25.dat",
            created_at=datetime.now(),
            notes="Regular checkup",
            tags=["routine", "normal"],
            dicom_uid="1.2.3.4.5.6.7.8.9"
        )
    ]

@router.get("/{user_id}/files/{file_id}", response_model=ECGFileResponse)
async def get_ecg_file(
    user_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get details of a specific ECG file.
    
    Requires doctor or admin privileges.
    """
    await check_user_access(user_id, current_user)
    
    # TODO: Implement database query to get specific ECG file
    # This is a mock response
    return ECGFileResponse(
        file_id=file_id,
        user_id=user_id,
        filename="ecg_record_2025_04_25.dat",
        created_at=datetime.now(),
        notes="Regular checkup",
        tags=["routine", "normal"],
        dicom_uid="1.2.3.4.5.6.7.8.9"
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
    await check_user_access(user_id, current_user)
    
    # Convert tags string to list
    tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
    
    # TODO: Implement database update for ECG file metadata
    # This is a mock response
    return ECGFileResponse(
        file_id=file_id,
        user_id=user_id,
        filename="ecg_record_2025_04_25.dat",
        created_at=datetime.now(),
        notes=notes,
        tags=tag_list,
        dicom_uid="1.2.3.4.5.6.7.8.9"
    )

@router.post("/{user_id}/files")
async def upload_ecg_file(
    request: Request,
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    上传文件
    需要医生或管理员权限
    """
    print("Starting file upload...")  # Debug
    await check_user_access(user_id, current_user)
    
    try:
        # 获取表单数据
        form = await request.form()
        print(f"Form data keys: {form.keys()}")  # Debug
        print(f"Complete form data: {dict(form)}")  # Debug
        
        # 获取文件
        if "file" not in form:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="没有找到文件字段"
            )
        
        file = form["file"]
        if not hasattr(file, "filename"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的文件上传"
            )
        
        print(f"File info - filename: {file.filename}, content_type: {getattr(file, 'content_type', 'unknown')}")  # Debug
        
        # 获取其他字段
        notes = form.get("notes", "")
        tags = form.get("tags", "")
        print(f"Additional fields - notes: {notes}, tags: {tags}")  # Debug
        
        # 生成唯一文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_ext = Path(file.filename).suffix if file.filename else ""
        unique_filename = f"{user_id}_{timestamp}{original_ext}"
        file_path = ECG_UPLOAD_DIR / unique_filename
        
        # 保存文件
        contents = await file.read()
        print(f"Read {len(contents)} bytes")  # Debug
        
        with open(file_path, "wb") as f:
            f.write(contents)

        # 获取 DICOM UID
        dicom_uid = ""
        try:
            with open(file_path, "rb") as f:
                ds = pydicom.dcmread(f)
                dicom_uid = str(ds.SOPInstanceUID)
        except Exception as e:
            print(f"Warning: Could not read DICOM UID: {e}")
            dicom_uid = str(file_path)  # 如果不是DICOM文件，使用文件路径作为唯一标识
        
        # 处理标签
        tag_list = []
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
            
        # 创建数据库记录
        patient = Patient.objects(id=user_id).first()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到患者记录"
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
            "filename": unique_filename,
            "created_at": ecg_file.created_at.isoformat(),
            "original_filename": file.filename,
            "notes": notes,
            "tags": tag_list,
            "dicom_uid": dicom_uid
        }
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