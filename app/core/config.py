import os
from pathlib import Path
from typing import ClassVar
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra='allow',  # Allow extra fields
        env_file='.env',  # Specify environment variable file
        case_sensitive=True  # Case sensitive
    )

    # Server settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Project paths
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parent.parent.parent
    UPLOAD_DIR: ClassVar[Path] = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
    DICOM_DIR: ClassVar[Path] = Path(os.getenv("DICOM_DIR", BASE_DIR / "dicom_files"))
    
    # AI Server settings
    aiserver_uri: str = os.getenv("AISERVER_URI", "http://localhost:9000")
    
    # MongoDB configuration
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017/aiclinic")
    
    # JWT settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-secret-key")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60000"))  # JWT token expiration time (minutes)
    MFA_EXPIRE_MINUTES: int = int(os.getenv("MFA_EXPIRE_MINUTES", "50000"))   # MFA verification code expiration time (minutes)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    
    # SMTP settings
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "your-email")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "your-email-password")

    # Orthanc settings
    ORTHANC_SERVER_URL: str = os.getenv('ORTHANC_SERVER_URL', 'http://127.0.0.1:8042')
    
    # Web server settings
    WEBSERVER_URI: str = os.getenv('WEBSERVER_URI', 'http://localhost:8000')
    
    # Auth server settings
    AUTH_SERVER_URL: str = os.getenv('AUTH_SERVER_URL', 'http://webserverauth:8001')

    # Logging settings
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
    LOG_DATE_FORMAT: str = '%Y-%m-%d %H:%M:%S'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create necessary directories
        self.UPLOAD_DIR.mkdir(exist_ok=True)
        self.DICOM_DIR.mkdir(exist_ok=True)

settings = Settings()
