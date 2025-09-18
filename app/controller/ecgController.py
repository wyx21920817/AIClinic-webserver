from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Body, Request
from fastapi.param_functions import Form
from fastapi import Query
from app.utils.logger_config import logger
from app.core.config import settings
from fastapi.responses import JSONResponse, Response, FileResponse
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
import uuid
import json
from ..core.config import settings

# Import ReportLab for PDF generation
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import io
import urllib.parse

# Create ECG upload directory if it doesn't exist
ECG_UPLOAD_DIR = Path("app/static/uploads/ecg")
ECG_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Create ECG reports directory if it doesn't exist
ECG_REPORTS_DIR = Path("app/static/reports/ecg")
ECG_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(
    prefix="/api/ecg",
    tags=["ecg"],
    responses={404: {"description": "Not found"}}
)


def download_image(image_url, instance_id):
    """
    Download an image from the AI server and save it locally.
    
    Args:
        image_url: The URL of the image on the AI server
        instance_id: The instance ID for creating a local directory
        
    Returns:
        Path to the downloaded image or None if download failed
    """
    try:
        # Create directory for this instance's images if it doesn't exist
        image_dir = ECG_REPORTS_DIR / instance_id
        image_dir.mkdir(parents=True, exist_ok=True)
        
        # Get the image filename from the URL
        image_filename = os.path.basename(image_url)
        local_image_path = image_dir / image_filename
        
        # If image already exists locally, return the path
        if local_image_path.exists():
            return local_image_path
        
        # Construct the full URL to the image on the AI server
        full_url = f"{image_url}"
        
        # Download the image
        response = requests.get(full_url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Save the image locally
        with open(local_image_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return local_image_path
    
    except Exception as e:
        logger.error(f"Error downloading image {image_url}: {str(e)}")
        return None


def generate_ecg_report_pdf(interpretation_data, output_path, notes=None, approved_status=None):
    """
    Generate a PDF report from the ECG interpretation data.
    If a PDF already exists at the output path, it will be deleted first.
    
    Args:
        interpretation_data: The interpretation data from the AI server
        output_path: The path to save the PDF file
        notes: Optional notes from the ECG file
        approved_status: Optional approval status from the ECG file
    """
    # Check if the PDF already exists and delete it if it does
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
            logger.info(f"Deleted existing PDF at {output_path}")
        except Exception as e:
            logger.error(f"Failed to delete existing PDF at {output_path}: {str(e)}")
    # Create a buffer for the PDF
    buffer = io.BytesIO()
    
    # Create the PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    # Get the styles
    styles = getSampleStyleSheet()
    
    # Create custom styles
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=12
    )
    
    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=6
    )
    
    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6
    )
    
    # Create the content elements
    elements = []
    
    # Add the title
    elements.append(Paragraph(f"ECG Interpretation Report", title_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Add the instance ID
    instance_id = interpretation_data.get("instance_id", "Unknown")
    elements.append(Paragraph(f"Instance ID: {instance_id}", normal_style))
    elements.append(Spacer(1, 0.1*inch))
    
    # Add the date
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elements.append(Paragraph(f"Report Date: {current_date}", normal_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Add notes if available
    if notes:
        elements.append(Paragraph("Notes:", heading_style))
        elements.append(Paragraph(notes, normal_style))
        elements.append(Spacer(1, 0.25*inch))
    
    # Add approval status if available
    if approved_status is not None:
        status_text = "Approved" if approved_status else "Not Approved"
        elements.append(Paragraph(f"Approval Status: {status_text}", normal_style))
        elements.append(Spacer(1, 0.25*inch))
    
    # Add the abnormalities section
    abnormalities = interpretation_data.get("abnormalities", [])
    if abnormalities:
        elements.append(Paragraph("Detected Abnormalities:", heading_style))
        for abnormality in abnormalities:
            elements.append(Paragraph(f"• {abnormality}", normal_style))
        elements.append(Spacer(1, 0.25*inch))
    
    # Add the results section
    results = interpretation_data.get("results", [])
    if results:
        elements.append(Paragraph("Analysis Results:", heading_style))
        elements.append(Spacer(1, 0.1*inch))
        
        for result in results:
            status = result.get("status", "Unknown")
            abnormality = result.get("abnormality", "Unknown")
            
            # Add the result header
            elements.append(Paragraph(f"{abnormality} Analysis (Status: {status})", heading_style))
            
            if status == "ok":
                # Add the report details
                report = result.get("report", {})
                if report:
                    # Add the report title
                    title = report.get("title", "")
                    if title:
                        elements.append(Paragraph(f"Title: {title}", normal_style))
                    
                    # Add the report text
                    report_text = report.get("report_text", "")
                    if report_text:
                        # Split the report text by lines and add each line
                        for line in report_text.split("\n"):
                            elements.append(Paragraph(line, normal_style))
                    
                    # Add images if available
                    image_paths = report.get("image_paths", {})
                    if image_paths:
                        elements.append(Spacer(1, 0.1*inch))
                        elements.append(Paragraph("Images:", heading_style))
                        
                        # Download and add each image
                        for image_name, image_url in image_paths.items():
                            # Download the image
                            local_image_path = download_image(image_url, instance_id)
                            
                            if local_image_path and local_image_path.exists():
                                try:
                                    # Add image caption
                                    elements.append(Paragraph(f"{image_name}:", normal_style))
                                    
                                    # Add the image with a reasonable width
                                    img = Image(str(local_image_path), width=5*inch, height=3*inch)
                                    elements.append(img)
                                    elements.append(Spacer(1, 0.1*inch))
                                except Exception as e:
                                    logger.error(f"Error adding image to PDF: {str(e)}")
                                    elements.append(Paragraph(f"Error loading image: {image_name}", normal_style))
                    
                    # Add metrics if available
                    metrics = report.get("metrics", {})
                    if metrics:
                        elements.append(Paragraph("Metrics:", heading_style))
                        
                        # Create a table for the metrics
                        metrics_data = []
                        for key, value in metrics.items():
                            if isinstance(value, dict):
                                # Handle nested dictionaries
                                for sub_key, sub_value in value.items():
                                    metrics_data.append([f"{key}.{sub_key}", str(sub_value)])
                            else:
                                metrics_data.append([key, str(value)])
                        
                        if metrics_data:
                            # Create the table
                            metrics_table = Table(metrics_data, colWidths=[2*inch, 3*inch])
                            metrics_table.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                                ('GRID', (0, 0), (-1, -1), 1, colors.black)
                            ]))
                            elements.append(metrics_table)
                    
                    # Add validation information if available
                    validation = report.get("validation", {})
                    if validation:
                        elements.append(Spacer(1, 0.1*inch))
                        elements.append(Paragraph("Validation:", heading_style))
                        
                        # Add validation status
                        validation_status = validation.get("status", "Unknown")
                        elements.append(Paragraph(f"Status: {validation_status}", normal_style))
                        
                        # Add validation reasons if available
                        reasons = validation.get("reasons", [])
                        if reasons:
                            elements.append(Paragraph("Reasons:", normal_style))
                            for reason in reasons:
                                elements.append(Paragraph(f"• {reason}", normal_style))
            else:
                # Add the reason for skipping
                reason = result.get("reason", "Unknown")
                elements.append(Paragraph(f"Reason: {reason}", normal_style))
            
            elements.append(Spacer(1, 0.25*inch))
    
    # Add the message
    message = interpretation_data.get("message", "")
    if message:
        elements.append(Paragraph("Message:", heading_style))
        elements.append(Paragraph(message, normal_style))
    
    # Build the PDF
    doc.build(elements)
    
    # Get the PDF data from the buffer
    pdf_data = buffer.getvalue()
    buffer.close()
    
    # Write the PDF to the output path
    with open(output_path, "wb") as f:
        f.write(pdf_data)
    
    return output_path

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
    notes: str = Form(""),
    tags: str = Form(""),
    approved_status: bool = Form(False),
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing ECG file record in the database.
    This only updates the database record, not the Orthanc file.
    
    Args:
        user_id: ID of the user who owns the file
        instance_id: Orthanc instance ID of the DICOM file
        notes: Notes about the ECG recording
        tags: Tags for categorization (comma-separated string)
        approved_status: Whether the ECG file is approved
        current_user: Current authenticated user
    
    Requires doctor or admin privileges.
    """
    try:
        await check_user_access(user_id, current_user)
        
        # Log the operation attempt
        logger.info(f"User {current_user.username} (role: {current_user.role}) attempting to update ECG file - user_id: {user_id}, instance_id: {instance_id}")
        
        # Find the ECG file record
        ecg_file = EcgFile.objects(dicom_uid=instance_id).first()
        if not ecg_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ECG file not found"
            )

        # Convert tags string to list, handling empty tags properly
        tag_list = []
        if tags and tags.strip():
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        logger.info(f"Updating ECG file with tags: {tag_list}")
        
        # Get patient record to verify it exists
        patient = Patient.objects(id=user_id).first()
        if not patient:
            raise HTTPException(
                status_code=404,
                detail="Patient not found"
            )
        
        # Update the ECG file record
        ecg_file.notes = notes
        ecg_file.tags = tag_list
        ecg_file.Approved_status = approved_status
        ecg_file.updated_at = datetime.utcnow()
        ecg_file.save()
        
        logger.info(f"Successfully updated ECG file - user_id: {user_id}, instance_id: {instance_id}")
        
        # Create audit log entry
        audit_log = AuditLogEntry(
            event_type="data_access",
            user_id=str(current_user.id),
            action="update",
            resource_type="ecg_file",
            resource_id=instance_id,
            details=f"Updated ECG file - Patient: {user_id}, Instance: {instance_id}",
            status="success",
            username=current_user.username,
            request_info={"patient_id": user_id, "instance_id": instance_id, "notes": notes, "tags": tag_list, "approved_status": approved_status}
        )
        audit_log.save()
        
        # Get instance details for response
        instance_details = get_instance(instance_id, token=current_user.token)
        
        # Return the updated ECG file information
        return ECGFileResponse(
            file_id=str(ecg_file.id),
            user_id=user_id,
            filename=instance_details.get('MainDicomTags', {}).get('FileName', 'unknown.dcm') if instance_details else "unknown.dcm",
            created_at=ecg_file.created_at,
            notes=notes,
            tags=tag_list,
            dicom_uid=instance_id,
            content=str(instance_details) if instance_details else "",
            instanceIDs=ecg_file.instanceIDs
        )
    except Exception as e:
        print(f"Error in update_ecg_file: {str(e)}")  # Debug
        import traceback
        print(f"Full error traceback: {traceback.format_exc()}")  # Debug
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update ECG record: {str(e)}"
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
                    # instance_details = get_instance(ecg_file.dicom_uid, token=current_user.token)
                    # if isinstance(instance_details, dict):
                    #     # Get instance creation time from DICOM tags
                    #     dicom_date = instance_details.get('MainDicomTags', {}).get('InstanceCreationDate')
                    #     dicom_time = instance_details.get('MainDicomTags', {}).get('InstanceCreationTime', '000000')
                    #     if '.' in dicom_time:  # Handle time format that may contain decimal points
                    #         dicom_time = dicom_time.split('.')[0]  # Only take hours, minutes, seconds part
                        
                    #     # Parse DICOM datetime format (YYYYMMDD HHMMSS)
                    #     try:
                    #         if dicom_date:
                    #             created_at = datetime.strptime(f"{dicom_date}{dicom_time}", '%Y%m%d%H%M%S')
                    #         else:
                    #             created_at = datetime.now()
                    #     except ValueError:
                    #         logger.warning(f"Invalid DICOM date/time format: {dicom_date} {dicom_time}. Using current time.")
                    #         created_at = datetime.now()
                            
                    #     ecg_files.append(ECGFileResponse(
                    #         file_id=str(ecg_file.dicom_uid),  # Use MongoDB ID as file_id
                    #         user_id=patient_id,
                    #         filename=instance_details.get('MainDicomTags', {}).get('FileName', 'unknown.dcm'),
                    #         created_at=created_at,
                    #         notes=ecg_file.notes,
                    #         tags=ecg_file.tags,
                    #         dicom_uid=ecg_file.dicom_uid,
                    #         content=str(instance_details),
                    #         instanceIDs=ecg_file.instanceIDs
                    #     ))

                    ecg_files.append(ECGFileResponse(
                        file_id=str(ecg_file.dicom_uid),  # Use MongoDB ID as file_id
                        user_id=patient_id,
                        created_at=created_at,
                        notes=ecg_file.notes,
                        tags=ecg_file.tags,
                        dicom_uid=ecg_file.dicom_uid,
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

from fastapi import Form

@router.post("/interpretation/{instance_id}")
async def get_interpretation(
    instance_id: str,
    disease: List[str] = Form(...),  # 使用List[str]接收多个同名字段，...表示必需参数
    current_user: User = Depends(get_current_user)
):
    """
    Get ECG interpretation and example images for multiple diseases.
    
    Args:
        instance_id: The Orthanc instance ID of the ECG file
        disease: List of diseases to get interpretations for
        current_user: Current authenticated user
    
    Form Data:
        disease: One or more disease values to get interpretations for. 
                To request multiple diseases, include multiple 'disease' fields in the form data.
                Available options: AF, 1dAVB, LBBB, RBBB, ST
                Default: AF
    
    Returns:
        JSON response with analysis reports and image URLs for each disease.
        Response format:
        {
            "instance_id": "3725559d-2c4dd6c0-a3d79d14-e9d8f0ed-84bdb597",
            "abnormalities": ["LBBB", "AF", "ST"],
            "status": "success",
            "results": [
                {
                    "status": "ok",
                    "abnormality": "LBBB",
                    "record_identifier": "3725559d-2c4dd6c0-a3d79d14-e9d8f0ed-84bdb597",
                    "task_output_dir": "...",
                    "report_path": "...",
                    "report": { ... }
                },
                ...
            ],
            "message": "XAI interpretation completed."
        }
    """
    # Log interpretation request
    audit_log = AuditLogEntry(
        event_type="data_access",
        user_id=str(current_user.id),
        action="interpretation",
        resource_type="ecg_instance",
        resource_id=instance_id,
        details=f"Requested interpretation for ECG instance {instance_id}",
        status="success",
        username=current_user.username,
        request_info={"diseases": disease}
    )
    audit_log.save()
    
    try:
        # Prepare the request to the AI server
        ai_server_url = f"{settings.AISERVER_URI}/interprete/{instance_id}"
        
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
        logger.info("Successfully generated temporary token for interpretation request")
        
        # Prepare the form data
        form_data = {}
        
        # Add each disease as a separate form field with the same name
        # For multiple values with the same key in form data, we need to use a list of tuples
        form_data_tuples = []
        for d in disease:
            form_data_tuples.append(("disease", d))
        
        # Add the temporary token for authentication
        form_data_tuples.append(("temp_token", temp_token))
        
        logger.info(f"Sending interpretation request to AI server for instance {instance_id} with diseases: {disease}")
        
        # Make the request to the AI server
        try:
            response = requests.post(
                ai_server_url,
                data=form_data_tuples,  # Use the list of tuples for multiple values with same key
                timeout=60  # Set a reasonable timeout
            )
            
            # Check if the request was successful
            response.raise_for_status()
            
            # Parse the JSON response
            ai_response = response.json()
            logger.info(f"Received interpretation response from AI server for instance {instance_id}")
            
            # Find ECG file record in database that contains this instance ID
            ecg_file =  EcgFile.objects(dicom_uid=instance_id).first()
            
            # Add ECG file information to the response
            if ecg_file:
                ai_response["ecg_file"] = {
                    "file_id": str(ecg_file.id),
                    "patient_id": str(ecg_file.patient_id.id),
                    "dicom_uid": ecg_file.dicom_uid,
                    "tags": ecg_file.tags,
                    "notes": ecg_file.notes,
                    "created_at": ecg_file.created_at.isoformat(),
                    "updated_at": ecg_file.updated_at.isoformat(),
                    "approved_status": ecg_file.Approved_status
                }
            
            # Return the enhanced AI server response
            return ai_response
            
        except requests.Timeout:
            logger.error(f"Interpretation request timed out for instance {instance_id}")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Interpretation request timed out, please try again later"
            )
        except requests.HTTPError as e:
            logger.error(f"AI server returned error for instance {instance_id}: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"AI server error: {e.response.text}"
            )
        except requests.RequestException as e:
            logger.error(f"Network error during interpretation request for instance {instance_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to connect to AI server, please check network connection"
            )
        except ValueError as e:
            logger.error(f"Invalid JSON response from AI server for instance {instance_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid response from AI server"
            )
            
    except Exception as e:
        import traceback
        logger.error(f"Error getting interpretation: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get interpretation: {str(e)}"
        )

@router.post("/interpretation-pdf/{instance_id}")
async def get_interpretation_pdf(
    instance_id: str,
    disease: List[str] = Form(...),  # 使用List[str]接收多个同名字段，...表示必需参数
    current_user: User = Depends(get_current_user)
):
    """
    Generate a PDF report from the ECG interpretation data and provide a download link.
    
    Args:
        instance_id: The Orthanc instance ID of the ECG file
        disease: List of diseases to get interpretations for
        current_user: Current authenticated user
    

    Returns:
        JSON response with the PDF download URL.
        Response format:
        {
            "instance_id": "3725559d-2c4dd6c0-a3d79d14-e9d8f0ed-84bdb597",
            "pdf_url": "/static/reports/ecg/3725559d-2c4dd6c0-a3d79d14-e9d8f0ed-84bdb597.pdf",
            "status": "success"
        }
    """
    # Log interpretation request
    audit_log = AuditLogEntry(
        event_type="data_access",
        user_id=str(current_user.id),
        action="interpretation_pdf",
        resource_type="ecg_instance",
        resource_id=instance_id,
        details=f"Requested PDF interpretation report for ECG instance {instance_id}",
        status="success",
        username=current_user.username,
        request_info={"diseases": disease}
    )
    audit_log.save()
    
    try:
        # First, get the interpretation data from the AI server
        ai_server_url = f"{settings.AISERVER_URI}/interprete/{instance_id}"
        
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
        logger.info("Successfully generated temporary token for interpretation request")
        
        # Prepare the form data
        form_data_tuples = []
        for d in disease:
            form_data_tuples.append(("disease", d))
        
        # Add the temporary token for authentication
        form_data_tuples.append(("temp_token", temp_token))
        
        logger.info(f"Sending interpretation request to AI server for instance {instance_id} with diseases: {disease}")
        
        # Make the request to the AI server
        try:
            response = requests.post(
                ai_server_url,
                data=form_data_tuples,
                timeout=60
            )
            
            # Check if the request was successful
            response.raise_for_status()
            
            # Parse the JSON response
            ai_response = response.json()
            logger.info(f"Received interpretation response from AI server for instance {instance_id}")
            
            # Generate a PDF report from the interpretation data
            pdf_filename = f"{instance_id}.pdf"
            pdf_path = ECG_REPORTS_DIR / pdf_filename
            
            # Try to find the ECG file with this instance ID
            ecg_file = None
            try:
                ecg_file = EcgFile.objects(instanceIDs__contains=instance_id).first()
                logger.info(f"Found ECG file for instance {instance_id}: {ecg_file.id if ecg_file else 'None'}")
            except Exception as e:
                logger.warning(f"Error finding ECG file for instance {instance_id}: {str(e)}")
            
            # Get notes and approval status if ECG file exists
            notes = None
            approved_status = None
            if ecg_file:
                notes = ecg_file.notes
                approved_status = ecg_file.Approved_status
            
            # Always generate a new PDF
            logger.info(f"Generating PDF report for instance {instance_id}")
            generate_ecg_report_pdf(ai_response, pdf_path, notes, approved_status)
            
            # Create the PDF download URL with base URL from settings
            relative_path = f"/static/reports/ecg/{pdf_filename}"
            pdf_url = f"{settings.WEBSERVER_URI}{relative_path}"
            
            # Return the PDF download URL
            return {
                "instance_id": instance_id,
                "pdf_url": pdf_url,
                "status": "success"
            }
            
        except requests.Timeout:
            logger.error(f"Interpretation request timed out for instance {instance_id}")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Interpretation request timed out, please try again later"
            )
        except requests.HTTPError as e:
            logger.error(f"AI server returned error for instance {instance_id}: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"AI server error: {e.response.text}"
            )
        except requests.RequestException as e:
            logger.error(f"Network error during interpretation request for instance {instance_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to connect to AI server, please check network connection"
            )
        except ValueError as e:
            logger.error(f"Invalid JSON response from AI server for instance {instance_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid response from AI server"
            )
            
    except Exception as e:
        import traceback
        logger.error(f"Error generating PDF report: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF report: {str(e)}"
        )


@router.post("/reports/{instance_id}/regenerate")
async def regenerate_ecg_report_pdf(
    instance_id: str,
    disease: List[str] = Form(...),
    current_user: User = Depends(get_current_user)
):
    """
    Regenerate a PDF report for a specific ECG instance.
    
    Args:
        instance_id: The Orthanc instance ID of the ECG file
        disease: List of diseases to get interpretations for
        current_user: Current authenticated user
    
    Returns:
        JSON response with the PDF download URL.
    """
    # Log regeneration request
    audit_log = AuditLogEntry(
        event_type="data_access",
        user_id=str(current_user.id),
        action="regenerate_pdf",
        resource_type="ecg_report",
        resource_id=instance_id,
        details=f"Regenerated PDF report for ECG instance {instance_id}",
        status="success",
        username=current_user.username,
        request_info={"diseases": disease}
    )
    audit_log.save()
    
    try:
        # Check if the PDF exists and delete it
        pdf_filename = f"{instance_id}.pdf"
        pdf_path = ECG_REPORTS_DIR / pdf_filename
        
        if pdf_path.exists():
            pdf_path.unlink()
            logger.info(f"Deleted existing PDF report for instance {instance_id}")
        
        # Call the interpretation-pdf endpoint to regenerate the PDF
        return await get_interpretation_pdf(instance_id, disease, current_user)
        
    except Exception as e:
        logger.error(f"Error regenerating PDF report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate PDF report: {str(e)}"
        )


@router.get("/reports/{instance_id}")
async def get_ecg_report_pdf(
    instance_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get the PDF report for a specific ECG instance.
    
    Args:
        instance_id: The Orthanc instance ID of the ECG file
        current_user: Current authenticated user
    
    Returns:
        The PDF file as a download.
        
    Note:
        This endpoint returns the actual PDF file for download.
        For just the URL, use the interpretation-pdf endpoint.
    """
    # Log report access
    audit_log = AuditLogEntry(
        event_type="data_access",
        user_id=str(current_user.id),
        action="download_report",
        resource_type="ecg_report",
        resource_id=instance_id,
        details=f"Downloaded PDF report for ECG instance {instance_id}",
        status="success",
        username=current_user.username
    )
    audit_log.save()
    
    try:
        # Check if the PDF exists
        pdf_filename = f"{instance_id}.pdf"
        pdf_path = ECG_REPORTS_DIR / pdf_filename
        
        if not pdf_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PDF report not found"
            )
        
        # Return the PDF file
        return FileResponse(
            path=str(pdf_path),
            media_type="application/pdf",
            filename=pdf_filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting PDF report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get PDF report: {str(e)}"
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