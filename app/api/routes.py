from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import shutil
import uuid
from pathlib import Path
from pydicom.dataset import Dataset
from pydicom import dcmread
from app.core.config import settings
from app.services.dicom_service import dicom_service
from app.utils.logger_config import logger
import os
import requests

router = APIRouter()

# 挂载文档目录
router.mount("/docs/static", StaticFiles(directory="docs"), name="docs")

# 存储转换任务的状态
conversion_tasks = {}

def process_image_task(file_id: str, input_file: Path, output_dir: Path):
    """后台任务：处理图片并转换为DICOM"""
    try:
        logger.info(f"开始处理任务 {file_id}")
        dicom_files, success_count = dicom_service.convert_and_send(input_file, output_dir)
        # 获取转换后的文件列表
        converted_files = list(output_dir.glob('*.dcm'))
        conversion_tasks[file_id] = {
            "status": "completed",
            "message": f"成功转换 {success_count} 个文件",
            "dicom_files": [f.name for f in converted_files],  # 使用实际的文件列表
            "error": None
        }
        logger.info(f"任务 {file_id} 完成")
    except Exception as e:
        logger.error(f"任务 {file_id} 失败: {str(e)}")
        conversion_tasks[file_id] = {
            "status": "failed",
            "message": "转换失败",
            "dicom_files": [],
            "error": str(e)
        }

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传DICOM文件到Orthanc服务器"""
    temp_dir = None
    try:
        # 获取临时token
        try:
            # 添加适当的headers，如果需要
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            response = requests.get(
                'http://52.63.231.27:8000/api/auth/temp-token',
                headers=headers,
                verify=False  # 如果是自签名证书可能需要这个
            )
            if response.status_code == 200:
                temp_token = response.json().get('token')
                if not temp_token:
                    raise ValueError("Token not found in response")
                logger.info("Successfully obtained temporary token")
            else:
                logger.error(f"Failed to get temp token. Status: {response.status_code}, Response: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"获取临时令牌失败: {response.text}"
                )
        except Exception as e:
            logger.error(f"获取临时令牌失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"获取临时令牌失败: {str(e)}")
            
        # 生成唯一的文件ID并创建临时目录
        file_id = str(uuid.uuid4())
        temp_dir = settings.UPLOAD_DIR / file_id
        temp_dir.mkdir(exist_ok=True)
        logger.info(f"创建临时目录: {temp_dir}")
        
        # 保存上传的文件
        temp_file = temp_dir / file.filename
        logger.info(f"保存上传文件: {temp_file}")
        with temp_file.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        try:
            # 验证是否为DICOM文件
            dicom_data = dcmread(temp_file)
            logger.info(f"Valid DICOM file detected: {file.filename}")
            
            # 上传到Orthanc服务器
            from app.controller.utils.orthanc import upload_dicom_file
            response = upload_dicom_file(str(temp_file), temp_token)
            
            if isinstance(response, dict) and 'error' in response:
                logger.error(f"Orthanc upload failed: {response['error']}")
                raise HTTPException(status_code=500, detail=response['error'])
                
            # 记录实例元数据
            instance_id = response.get('ID')
            parent_info = {
                'patient_id': response.get('ParentPatient'),
                'study_id': response.get('ParentStudy'),
                'series_id': response.get('ParentSeries')
            }
            
            logger.info(f"Successfully uploaded DICOM instance: {instance_id}")
            logger.debug(f"Parent information: {parent_info}")
            
            # 返回成功响应
            return JSONResponse({
                "status": "success",
                "message": "DICOM文件已上传到Orthanc服务器",
                "instance_id": instance_id,
                "parent_info": parent_info
            })

                
        except Exception as e:
            logger.error(f"文件验证或上传失败: {str(e)}")
            raise HTTPException(status_code=400, detail=f"无效的DICOM文件或上传失败: {str(e)}")
            
    except Exception as e:
        logger.error(f"上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 确保临时目录始终被清理
        if temp_dir is not None and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.error(f"清理临时目录失败: {str(e)}")

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in conversion_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return conversion_tasks[task_id]

@router.get("/download/{task_id}/{filename}")
async def download_file(task_id: str, filename: str):
    """下载转换后的DICOM文件"""
    file_path = settings.DICOM_DIR / task_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        file_path,
        media_type="application/dicom",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.post("/convert")
async def convert_to_dicom(file: UploadFile = File(...)):
    """将上传的CT扫描文件转换为DICOM格式"""
    try:
        logger.info(f"Starting conversion for file: {file.filename}")
        
        # 生成唯一的文件名
        file_id = str(uuid.uuid4())
        temp_dir = settings.UPLOAD_DIR / file_id
        temp_dir.mkdir(exist_ok=True)
        logger.debug(f"Created temporary directory: {temp_dir}")
        
        try:
            # 保存上传的文件
            temp_file = temp_dir / file.filename
            logger.debug(f"Saving uploaded file to: {temp_file}")
            with temp_file.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # 转换并发送到PACS
            output_dir = settings.DICOM_DIR / file_id
            dicom_files, success_count = dicom_service.convert_and_send(temp_file, output_dir)
            
            return {
                "message": f"Successfully converted and sent {success_count} of {len(dicom_files)} files to PACS",
                "file_id": file_id,
                "dicom_count": len(dicom_files)
            }
            
        finally:
            # 清理临时文件
            logger.debug(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)
            
    except Exception as e:
        logger.error(f"Error during conversion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
async def read_root():
    """返回测试页面"""
    logger.info("Returning test page")
    return FileResponse("app/static/index.html")

@router.get("/health")
async def health_check():
    """健康检查端点"""
    logger.info("Health check")
    return {"status": "ok", "message": "Service is running"}

@router.get("/dicom/{file_id}")
async def get_dicom(file_id: str):
    """获取DICOM文件"""
    logger.info(f"Getting DICOM file: {file_id}")
    file_path = next(settings.UPLOAD_DIR.glob(f"{file_id}.*"), None)
    if not file_path:
        logger.error(f"File not found: {file_id}")
        raise HTTPException(status_code=404, detail="File not found")
    logger.info(f"Returning DICOM file: {file_path}")
    return FileResponse(file_path)

@router.get("/pacs/search")
async def search_pacs(patient_id: str = None, patient_name: str = None):
    """搜索PACS服务器中的DICOM文件"""
    logger.info(f"Searching PACS for patient ID: {patient_id}, patient name: {patient_name}")
    
    # Create query dataset
    ds = Dataset()
    ds.QueryRetrieveLevel = 'PATIENT'
    
    if patient_id:
        ds.PatientID = patient_id
    if patient_name:
        ds.PatientName = patient_name
    
    # Add more query fields as needed
    ds.Modality = ''
    ds.StudyDescription = ''
    
    # Query PACS
    try:
        results = dicom_service.query_pacs(ds)
        logger.info(f"Received {len(results)} results from PACS")
        
        return [
            {
                "patient_id": getattr(r, "PatientID", ""),
                "patient_name": str(getattr(r, "PatientName", "")),
                "modality": getattr(r, "Modality", ""),
                "study_description": getattr(r, "StudyDescription", "")
            }
            for r in results
        ]
    except Exception as e:
        logger.error(f"Error querying PACS: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to query PACS: {str(e)}")

@router.get("/files")
async def list_files():
    """列出所有DICOM文件"""
    logger.info("Listing files")
    files = []
    for file_path in settings.UPLOAD_DIR.glob("*"):
        try:
            logger.debug(f"Processing file: {file_path}")
            ds = dcmread(file_path)
            files.append({
                "id": file_path.stem,
                "filename": file_path.name,
                "patient_name": str(getattr(ds, "PatientName", "Unknown")),
                "patient_id": getattr(ds, "PatientID", "Unknown"),
                "modality": getattr(ds, "Modality", "Unknown")
            })
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            continue
    
    logger.info(f"Found {len(files)} files")
    return files

@router.get("/docs")
async def get_docs():
    """返回API文档页面"""
    return FileResponse("docs/api.md")

@router.get("/docs/setup")
async def get_setup_docs():
    """返回安装文档页面"""
    return FileResponse("docs/setup.md")

@router.get("/docs/dev")
async def get_dev_docs():
    """返回开发文档页面"""
    return FileResponse("docs/development.md")
