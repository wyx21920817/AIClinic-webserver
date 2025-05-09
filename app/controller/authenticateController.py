from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
import jwt
from datetime import datetime, timedelta
import os
from fastapi.responses import Response
import json

router = APIRouter(
    prefix="/api/auth",
    tags=["authentication"]
)

# 从环境变量获取密钥，实际使用时应该配置在环境变量中
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key')

@router.get('/verify-token')  # 改为 GET 方法
@router.post('/verify-token')  # 保留 POST 方法以保持向后兼容
async def verify_token(authorization: str = Header(None)):
    """
    验证JWT token的端点，供Orthanc回调使用
    支持验证普通token和临时token
    """
    if not authorization:
        return Response(status_code=401)
    
    try:
        # 通常Authorization header的格式是"Bearer <token>"
        token = authorization.split(' ')[1] if ' ' in authorization else authorization
        
        # 验证token
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        
        # 检查token是否过期
        exp = payload.get('exp')
        if exp and datetime.utcnow().timestamp() > exp:
            return Response(status_code=401)
            
        # 检查是否是临时token
        if payload.get('temp', False):
            # 临时token拥有所有权限
            return Response(
                content=json.dumps({
                    "granted": True,
                    "validity": 60,  # 临时token只缓存1分钟
                    "labels": ["view", "upload", "modify", "all"],  # 所有权限
                    "user": "temp_user"
                }),
                media_type="application/json",
                headers={
                    "Content-Type": "application/json",
                    "Connection": "close"
                }
            )
            
        # 普通token的验证逻辑
        role = payload.get('role', '')
        labels = ["view"]  # 基本查看权限
        
        # 医生和管理员都可以上传
        if role in ['doctor', 'admin']:
            labels.append("upload")
        
        # 只有管理员有全部权限
        if role == 'admin':
            labels.extend(["all", "modify"])
            
        # 返回Orthanc期望的响应格式
        return Response(
            content=json.dumps({
                "granted": True,
                "validity": 3600,  # 普通token缓存1小时
                "labels": labels,  # 用户权限标签
                "user": payload.get('sub', 'unknown')  # 用户ID
            }),
            media_type="application/json",
            headers={
                "Content-Type": "application/json",
                "Connection": "close"  # 明确关闭连接，避免连接池问题
            }
        )
    except jwt.ExpiredSignatureError:
        return Response(status_code=401)
    except jwt.InvalidTokenError:
        return Response(status_code=401)
    except Exception as e:
        print(f"Token verification error: {str(e)}")
        return Response(status_code=401)

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
            'sub': 'temp_user',  # 临时用户标识
            'role': 'temp_admin',  # 给予管理员权限
            'temp': True  # 标记为临时token
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