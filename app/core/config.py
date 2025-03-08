import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    # Server settings
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))
    
    # Project paths
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
    DICOM_DIR = Path(os.getenv("DICOM_DIR", BASE_DIR / "dicom_files"))
    
    # PACS configuration
    PACS_HOST = os.getenv("PACS_HOST", "127.0.0.1")
    PACS_PORT = int(os.getenv("PACS_PORT", "8000"))
    AE_TITLE = os.getenv("AE_TITLE", "AICLINIC")
    PACS_AE_TITLE = os.getenv("PACS_AE_TITLE", "PACS")
    
    # Create necessary directories
    UPLOAD_DIR.mkdir(exist_ok=True)
    DICOM_DIR.mkdir(exist_ok=True)

settings = Settings()
