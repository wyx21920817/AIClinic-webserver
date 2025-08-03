import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime
from typing import Optional

def setup_logger(name='AIClinic', log_file='server.log'):
    """Setup logger with console and file handlers"""
    # Create logs directory
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / log_file

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Create formatter
    detailed_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    )

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(detailed_formatter)

    # Create file handler with rotation
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # 添加处理器
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # 添加一个专门用于请求日志的文件处理器
    requests_log = log_dir / 'requests.log'
    request_handler = RotatingFileHandler(
        requests_log,
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    request_handler.setLevel(logging.INFO)
    request_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(message)s'
    ))
    logger.addHandler(request_handler)

    return logger

async def log_request_info(request, response_status: Optional[int] = None, response_body: Optional[str] = None):
    """Log detailed request and response information"""
    # Get request information
    request_info = {
        'method': request.method,
        'url': str(request.url),
        'client_host': request.client.host if request.client else None,
        'headers': dict(request.headers),
        'path_params': request.path_params,
        'query_params': dict(request.query_params),
        'timestamp': datetime.utcnow().isoformat(),
    }

    # Log form data type if available
    content_type = request.headers.get('content-type', '')
    request_info['content_type'] = content_type

    # Add response information if available
    if response_status is not None:
        request_info['response_status'] = response_status
    if response_body is not None:
        request_info['response_body'] = response_body

    # Log the information
    logger = logging.getLogger('AIClinic')
    logger.info(
        'Request/Response Info: %s',
        json.dumps(request_info, ensure_ascii=False, indent=2)
    )

# Create a global logger
logger = setup_logger()
