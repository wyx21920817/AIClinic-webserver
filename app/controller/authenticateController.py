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
            
        # 根据用户角色返回不同的权限
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
                "validity": 3600,  # 缓存1小时
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