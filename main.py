import uvicorn
from app import create_app
from app.core.config import settings
import logging

# Configure logging filter
class StatusEndpointFilter(logging.Filter):
    def filter(self, record):
        return "GET /status/" not in record.getMessage()

# Configure uvicorn access log
logging.getLogger("uvicorn.access").addFilter(StatusEndpointFilter())

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        workers=4,  # Increase number of worker processes
        log_level="info"
    )
