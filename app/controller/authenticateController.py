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
        raise HTTPException(status_code=401, detail="No token provided")
    
    try:
        # 通常Authorization header的格式是"Bearer <token>"
        token = authorization.split(' ')[1] if ' ' in authorization else authorization
        
        # 验证token
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        
        # 检查token是否过期
        exp = payload.get('exp')
        if exp and datetime.utcnow().timestamp() > exp:
            raise HTTPException(status_code=401, detail="Token has expired")
            
        # token验证成功
        # return JSONResponse(
        #     status_code=200,
        #     content={
        #         "granted": True,  # 必需字段，表示是否授予访问权限
        #         "validity": 3600,  # 缓存有效期，单位为秒
        #         "authorized": True,
        #         "labels": ["all", "view", "upload", "modify"],
        #         "user": "admin"
        #     }
        # )
        payload = {
            "granted": True,
            "validity": 3600,
            "authorized": True,
            "labels": ["all", "view", "upload", "modify"],
            "user": "admin"
        }

        return Response(
            content=json.dumps(payload),
            media_type="application/json",
            headers={"Content-Length": str(len(json.dumps(payload)))}
        )


        
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")