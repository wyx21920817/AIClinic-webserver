# AIClinic Web Server API 文档

## 基础信息

### 基础 URL
- 开发环境：`http://localhost:8000`
- 测试环境：`http://test.aiclinic.com`
- 生产环境：`https://api.aiclinic.com`

### 请求格式
- Content-Type: `application/json` 或 `multipart/form-data`（用于文件上传）
- 字符编码：UTF-8

### 响应格式
所有响应都是 JSON 格式，包含以下基本结构：
```json
{
  "status": "success/error",
  "message": "描述信息",
  "data": {} // 具体数据
}
```

## 概述
AIClinic Web Server 提供了一系列 API 端点，用于处理 DICOM 文件的上传、转换和查询功能。

## API 端点

### 1. 健康检查
- **URL**: `/health`
- **方法**: GET
- **描述**: 检查服务是否正常运行
- **响应示例**:
  ```json
  {
    "status": "ok",
    "message": "Service is running"
  }
  ```

### 2. 文件上传和转换
- **URL**: `/upload`
- **方法**: POST
- **描述**: 异步上传和转换图像文件为 DICOM 格式
- **请求体**: multipart/form-data
  - `file`: 要上传的文件
- **响应示例**:
  ```json
  {
    "status": "success",
    "message": "文件已上传，正在处理中",
    "task_id": "uuid-string"
  }
  ```

### 3. 转换状态查询
- **URL**: `/status/{task_id}`
- **方法**: GET
- **描述**: 查询文件转换任务的状态
- **参数**:
  - `task_id`: 任务ID（从上传接口返回）
- **响应示例**:
  ```json
  {
    "status": "completed",
    "message": "成功转换 1 个文件",
    "dicom_files": ["file1.dcm"],
    "error": null
  }
  ```

### 4. DICOM 文件下载
- **URL**: `/download/{task_id}/{filename}`
- **方法**: GET
- **描述**: 下载转换后的 DICOM 文件
- **参数**:
  - `task_id`: 任务ID
  - `filename`: DICOM 文件名
- **响应**: DICOM 文件（application/dicom）

### 5. ECG 诊断
- **URL**: `/api/ecg/{user_id}/instances/{instance_id}/diagnose`
- **方法**: POST
- **描述**: 发送ECG实例到AI服务器进行诊断分析
- **参数**:
  - `user_id`: 患者ID
  - `instance_id`: ECG实例的Orthanc ID
- **权限要求**: 需要医生或管理员权限
- **响应示例**:
  ```json
  {
    "instance_id": "e72798cf-ef128120-6f24e3ee-90dbf8df-e89cbb1a",
    "diagnosis_result": {
      "diagnosis": "正常心电图",
      "confidence": 0.95,
      "findings": [
        {
          "type": "心率",
          "value": "72",
          "unit": "bpm",
          "interpretation": "正常范围"
        }
      ]
    },
    "created_at": "2025-08-08T14:45:13+08:00",
    "status": "completed"
  }
  ```

### 6. ECG 解读
- **URL**: `/api/ecg/interpretation/{instance_id}`
- **方法**: POST
- **描述**: 获取特定疾病的ECG解读标准和示例图片
- **参数**:
  - `instance_id`: ECG实例的Orthanc ID
  - `disease`: 疾病名称（在请求体中）
- **权限要求**: 需要医生或管理员权限
- **请求示例**:
  ```json
  {
    "disease": "心房颤动"
  }
  ```
- **响应示例**:
  ```json
  {
    "disease": "心房颤动",
    "interpretation": [
      "不规则的R-R间期",
      "缺失P波",
      "基线呈不规则波动"
    ],
    "example_images": [
      {
        "url": "https://example.com/ecg/af_example1.jpg",
        "description": "典型心房颤动ECG",
        "type": "typical"
      }
    ],
    "explanation": "心房颤动是一种常见的心律失常，其特征为...",
    "references": [
      "ESC 2020心房颤动诊疗指南"
    ],
    "instance_id": "e72798cf-ef128120-6f24e3ee-90dbf8df-e89cbb1a",
    "temp_token": "eyJhbGciOiJIUzI1NiIs..."
  }
  ```

### 7. PACS 查询
- **URL**: `/search_pacs`
- **方法**: GET
- **描述**: 查询 PACS 服务器中的 DICOM 文件
- **参数**:
  - `patient_id`: （可选）患者ID
  - `patient_name`: （可选）患者姓名
- **响应示例**:
  ```json
  {
    "results": [
      {
        "patient_id": "12345",
        "patient_name": "Anonymous",
        "study_description": "Image Study",
        "series_description": "Converted Image",
        "file_path": "path/to/dicom/file.dcm"
      }
    ]
  }
  ```

### 6. ECG 诊断
- **URL**: `/api/ecg/{user_id}/instances/{instance_id}/diagnose`
- **方法**: POST
- **描述**: 发送ECG实例到AI服务器进行诊断分析
- **参数**:
  - `user_id`: 患者ID
  - `instance_id`: ECG实例的Orthanc ID
- **权限要求**: 需要医生或管理员权限
- **响应示例**:
  ```json
  {
    "instance_id": "e72798cf-ef128120-6f24e3ee-90dbf8df-e89cbb1a",
    "diagnosis_result": {
      "diagnosis": "正常心电图",
      "confidence": 0.95,
      "findings": [
        {
          "type": "心率",
          "value": "72",
          "unit": "bpm",
          "interpretation": "正常范围"
        }
      ]
    },
    "created_at": "2025-08-08T14:45:13+08:00",
    "status": "completed"
  }
  ```
- **错误响应**:
  - 404: ECG实例不存在
  - 403: 权限不足
  - 504: AI服务器请求超时
  - 503: AI服务器连接失败

## 错误处理
所有 API 端点在发生错误时都会返回适当的 HTTP 状态码和错误信息：

- 400 Bad Request: 请求参数错误
- 401 Unauthorized: 未登录或token无效
- 403 Forbidden: 权限不足
- 404 Not Found: 资源不存在（如ECG文件不存在）
- 422 Unprocessable Entity: 请求格式正确但无法处理
- 500 Internal Server Error: 服务器内部错误
- 503 Service Unavailable: 外部服务（如AI服务器）不可用
- 504 Gateway Timeout: 外部服务请求超时（如AI诊断请求超时）

错误响应格式：
```json
{
  "detail": "错误描述信息"
}
```

示例错误：
```json
{
  "detail": "ECG诊断请求超时，请稍后重试"
}
```

错误响应格式：
```json
{
  "detail": "错误描述信息"
}
```

## 文件处理流程
1. 客户端通过 `/upload` 端点上传文件
2. 服务器返回任务ID
3. 客户端定期通过 `/status/{task_id}` 查询转换状态
4. 转换完成后，客户端可以通过 `/download/{task_id}/{filename}` 下载转换后的文件
