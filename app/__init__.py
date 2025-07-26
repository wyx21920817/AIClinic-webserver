from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from mongoengine import connect, disconnect
from app.utils.logger_config import logger, log_request_info
from .core.config import settings
import time
import traceback

def create_app():
    app = FastAPI(
        title="AIClinic DICOM Server",
        description="A FastAPI server for processing and managing DICOM files",
        version="1.0.0"
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """记录所有请求和响应"""
        start_time = time.time()
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # 记录请求信息
            log_request_info(logger, request, response.status_code)
            
            # 记录处理时间
            logger.info(f"Request processed in {process_time:.2f} seconds")
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(f"Request failed after {process_time:.2f} seconds")
            logger.error(f"Error details: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            log_request_info(logger, request, 500, error=str(e))
            raise

    # Enable CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins
        allow_credentials=True,
        allow_methods=["*"],  # Allow all methods
        allow_headers=["*"],  # Allow all headers
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Connect to MongoDB
    disconnect()  # Disconnect any existing connections
    connect(host=settings.MONGODB_URI)

    # Import and register routers
    from app.api.routes import router as api_router
    app.include_router(api_router)

    # Import and register controllers
    from app.controller.userController import router as user_router
    app.include_router(user_router)

    from app.controller.patientsController import router as patients_router
    app.include_router(patients_router)

    from app.controller.ecgController import router as ecg_router
    app.include_router(ecg_router)

    from app.controller.authenticateController import router as authenticate_router
    app.include_router(authenticate_router)

    from app.controller.auditController import router as audit_router
    app.include_router(audit_router)

    return app
