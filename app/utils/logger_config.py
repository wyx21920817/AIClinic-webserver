import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime

def setup_logger(name='AIClinic', log_file='server.log'):
    """设置日志记录器"""
    # 创建logs目录
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / log_file

    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 创建格式化器
    detailed_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    )

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(detailed_formatter)

    # 创建文件处理器
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

def log_request_info(logger, request, response_status=None, error=None):
    """记录详细的请求信息"""
    try:
        info = {
            'timestamp': datetime.now().isoformat(),
            'method': request.method,
            'url': str(request.url),
            'client_host': request.client.host,
            'client_port': request.client.port,
            'headers': dict(request.headers),
            'path_params': request.path_params,
            'query_params': str(request.query_params),
            'status_code': response_status
        }
        
        if error:
            info['error'] = str(error)
            logger.error(f"Request failed: {json.dumps(info, indent=2)}")
        else:
            logger.info(f"Request processed: {json.dumps(info, indent=2)}")
            
    except Exception as e:
        logger.error(f"Error logging request: {str(e)}")

# 创建全局日志记录器
logger = setup_logger()
