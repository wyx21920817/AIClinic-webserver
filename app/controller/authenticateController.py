from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
import jwt
from datetime import datetime, timedelta
import os
from fastapi.responses import Response
import json
import logging

router = APIRouter(
    prefix="/api/auth",
    tags=["authentication"],
    dependencies=[]
)

# 配置日志记录器
logger = logging.getLogger(__name__)

# 从环境变量获取密钥
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key')

@router.get('/verify-token')
@router.post('/verify-token')
async def verify_token(authorization: str = Header(None)):
    """
    验证JWT token的端点，供Orthanc回调使用
    支持验证普通token和临时token
    """
    logger.info(f"Received token verification request")
    
    if not authorization:
        logger.warning("No authorization header provided")
        return JSONResponse(
            status_code=401,
            content={"detail": "No authorization header"}
        )
    
    try:
        # 解析token
        token = authorization.split(' ')[1] if ' ' in authorization else authorization
        logger.debug(f"Processing token verification")
        
        # 验证token
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        
        # 检查token是否过期
        exp = payload.get('exp')
        if exp and datetime.utcnow().timestamp() > exp:
            logger.warning("Token has expired")
            return JSONResponse(
                status_code=401,
                content={"detail": "Token has expired"}
            )
        
        # 构建基本响应
        response_data = {
            "granted": True,
            "validity": 3600,  # 默认缓存1小时
            "labels": ["view"],  # 基本查看权限
            "user": payload.get('sub', 'unknown'),
            "is_temp": False
        }
        
        # 处理临时token
        if payload.get('temp', False) and payload.get('orthanc_access', False):
            response_data.update({
                "validity": 60,  # 临时token只缓存1分钟
                "labels": ["view", "upload", "modify", "all"],
                "user": "orthanc_temp_access",
                "is_temp": True
            })
            logger.info("Processed temporary token")
            return JSONResponse(content=response_data)
        
        # 处理普通token
        sub = payload.get('sub')
        if not sub:
            logger.warning("Token missing subject claim")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token structure"}
            )
        
        # 设置权限
        role = payload.get('role', '')
        if role in ['doctor', 'admin']:
            response_data['labels'].append("upload")
        if role == 'admin':
            response_data['labels'].extend(["all", "modify"])
        
        logger.info(f"Successful token verification for user {sub} with role {role}")
        return JSONResponse(content=response_data)
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token signature has expired")
        return JSONResponse(
            status_code=401,
            content={"detail": "Token has expired"}
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {str(e)}")
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid token"}
        )
    except Exception as e:
        logger.error(f"Unexpected error in token verification: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

@router.get('/temp-token')
async def get_temp_token():
    """
    生成一个有效期为1分钟的临时token，具有查询和修改Orthanc文件的权限
    """
    try:
        # 创建token payload
        payload = {
            'exp': datetime.utcnow() + timedelta(minutes=1),  # 1分钟后过期
            'iat': datetime.utcnow(),
            'temp': True,  # 标记为临时token
            'orthanc_access': True  # 标记这是用于Orthanc访问的token
        }
        
        # 生成token
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')
        
        return JSONResponse(
            content={
                "token": token,
                "expires_in": 60,  # 60秒
                "token_type": "Bearer"
            },
            status_code=200
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))