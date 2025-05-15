import uvicorn
from app import create_app
from app.core.config import settings
import logging

# 配置日志过滤器
class StatusEndpointFilter(logging.Filter):
    def filter(self, record):
        return "GET /status/" not in record.getMessage()

# 配置uvicorn的访问日志
logging.getLogger("uvicorn.access").addFilter(StatusEndpointFilter())

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        workers=4,  # 增加工作进程数
        log_level="info"
    )
