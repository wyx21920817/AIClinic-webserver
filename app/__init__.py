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
        """Log all requests and responses"""
        start_time = time.time()
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Get response body
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk
            
            # Create an async generator for the response body
            async def body_iterator():
                yield response_body
            
            response.body_iterator = body_iterator()
            
            # Log request and response info - handle binary data
            try:
                decoded_body = response_body.decode('utf-8')
            except UnicodeDecodeError:
                # For binary data, just log the content length
                decoded_body = f"<Binary data of length {len(response_body)} bytes>"
            
            # Log detailed request and response info
            request_info = {
                'method': request.method,
                'path': request.url.path,
                'status_code': response.status_code,
                'process_time': f"{process_time:.2f}s",
                'client': request.client.host if request.client else None,
                'response': decoded_body[:500] if isinstance(decoded_body, str) else str(decoded_body)[:500]  # Limit response length
            }
            logger.info(f"Request: {request.method} {request.url.path}")
            logger.info(f"Status: {response.status_code} - Time: {process_time:.2f}s - Client: {request.client.host if request.client else 'unknown'}")
            logger.info(f"Response: {request_info['response']}")
            
            # Log full details to requests.log
            await log_request_info(request, response.status_code, decoded_body)
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(f"Request failed after {process_time:.2f} seconds")
            logger.error(f"Error details: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            await log_request_info(request, 500)
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
