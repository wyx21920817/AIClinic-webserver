# AIClinic Web Server 开发指南

## 架构概述

### 主要组件
1. **API 层** (`app/api/routes.py`)
   - 处理 HTTP 请求
   - 实现 RESTful API 端点
   - 管理异步任务

2. **服务层** (`app/services/`)
   - `dicom_service.py`: 处理 DICOM 文件操作和 PACS 通信
   - `dicom_converter.py`: 实现文件格式转换

3. **配置层** (`app/core/`)
   - 管理环境变量和系统配置
   - 提供全局设置

4. **工具层** (`app/utils/`)
   - 提供日志、错误处理等通用功能

### 数据流
1. 文件上传 → 临时存储
2. 异步转换处理
3. DICOM 文件生成
4. PACS 系统集成
5. 结果返回客户端

## 开发规范

### 代码风格
- 遵循 PEP 8 规范
- 使用类型注解
- 编写清晰的文档字符串

### 错误处理
```python
try:
    # 业务逻辑
    result = process_data()
except SpecificError as e:
    logger.error(f"处理失败: {str(e)}")
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.error(f"未知错误: {str(e)}")
    raise HTTPException(status_code=500, detail="服务器内部错误")
```

### 日志记录
```python
from app.utils.logger_config import logger

logger.info("开始处理任务")
logger.debug("详细信息: %s", details)
logger.error("错误: %s", error_message)
```

## 异步任务处理

### 任务状态管理
```python
conversion_tasks = {
    "task_id": {
        "status": "processing",
        "message": "正在处理中",
        "dicom_files": [],
        "error": None
    }
}
```

### 后台任务
```python
@router.post("/upload")
async def upload_file(
    file: UploadFile,
    background_tasks: BackgroundTasks
):
    background_tasks.add_task(process_image_task, file_id, input_file)
    return {"task_id": file_id}
```

## DICOM 处理

### 文件转换
```python
def convert_to_dicom(input_file: Path, output_file: Path) -> bool:
    """
    将输入文件转换为 DICOM 格式
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        
    Returns:
        bool: 转换是否成功
    """
    try:
        # 检测文件类型
        file_type = detect_file_type(input_file)
        
        # 转换为 BMP（如果需要）
        if file_type != "bmp":
            input_file = convert_to_bmp(input_file)
            
        # 执行 img2dcm 转换
        result = run_img2dcm(input_file, output_file)
        
        return result.success
        
    except Exception as e:
        logger.error(f"转换失败: {str(e)}")
        return False
```

### PACS 集成
```python
async def send_to_pacs(file_path: Path) -> bool:
    """
    发送 DICOM 文件到 PACS 服务器
    
    Args:
        file_path: DICOM 文件路径
        
    Returns:
        bool: 发送是否成功
    """
    try:
        # 建立连接
        association = await establish_association()
        
        # 发送文件
        status = await association.send_file(file_path)
        
        return status.success
        
    except Exception as e:
        logger.error(f"PACS 发送失败: {str(e)}")
        return False
```

## 测试

### 单元测试
```python
def test_convert_to_dicom():
    input_file = Path("test_data/test.png")
    output_file = Path("test_data/output.dcm")
    
    result = convert_to_dicom(input_file, output_file)
    
    assert result is True
    assert output_file.exists()
    assert verify_dicom_format(output_file)
```

### 集成测试
```python
async def test_upload_and_convert():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/upload",
            files={"file": ("test.png", open("test.png", "rb"))}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
```

## 部署

### Docker 部署
```dockerfile
FROM python:3.8-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y dcmtk

# 复制应用代码
COPY . /app
WORKDIR /app

# 安装 Python 依赖
RUN pip install -r requirements.txt

# 创建必要的目录
RUN mkdir uploads dicom_files logs

# 启动应用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 环境配置
```yaml
# docker-compose.yml
version: '3'
services:
  web:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./uploads:/app/uploads
      - ./dicom_files:/app/dicom_files
      - ./logs:/app/logs
    environment:
      - UPLOAD_DIR=uploads
      - DICOM_DIR=dicom_files
      - PACS_HOST=pacs
      - PACS_PORT=8000
```

## 性能优化

### 文件处理
- 使用异步 IO 操作
- 实现文件流式处理
- 优化临时文件管理

### 并发处理
- 使用线程锁保护共享资源
- 实现任务队列
- 控制并发任务数量

### 内存管理
- 及时清理临时文件
- 控制上传文件大小
- 实现文件分块处理

## 安全性

### 文件验证
- 验证文件类型
- 限制文件大小
- 扫描恶意内容

### 访问控制
- 实现身份认证
- 添加请求限流
- 记录访问日志

### 数据保护
- 加密敏感信息
- 安全存储文件
- 实现数据备份
