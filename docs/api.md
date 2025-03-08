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

### 5. PACS 查询
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

## 错误处理
所有 API 端点在发生错误时都会返回适当的 HTTP 状态码和错误信息：

- 400 Bad Request: 请求参数错误
- 404 Not Found: 资源不存在
- 422 Unprocessable Entity: 请求格式正确但无法处理
- 500 Internal Server Error: 服务器内部错误

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
