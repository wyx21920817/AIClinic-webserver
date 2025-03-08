# AIClinic Web Server 安装和配置指南

## 系统要求
- Python 3.8+
- DCMTK（用于 DICOM 文件处理）
- 足够的磁盘空间用于存储上传和转换的文件

## 安装步骤

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 安装 DCMTK
- Windows: 
  1. 下载 DCMTK 安装包
  2. 将 bin 目录添加到系统 PATH 环境变量

### 3. 配置环境变量
创建 `.env` 文件并设置以下变量：
```
UPLOAD_DIR=uploads
DICOM_DIR=dicom_files
PACS_HOST=127.0.0.1
PACS_PORT=8000
```

### 4. 创建必要的目录
```bash
mkdir uploads
mkdir dicom_files
```

## 启动服务器
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 目录结构
```
AIClinic-webserver/
├── app/
│   ├── api/
│   │   └── routes.py      # API 路由
│   ├── core/
│   │   └── config.py      # 配置
│   ├── services/
│   │   ├── dicom_service.py    # DICOM 服务
│   │   └── dicom_converter.py  # 转换器
│   ├── static/
│   │   └── index.html     # 测试页面
│   └── utils/
│       └── logger_config.py    # 日志配置
├── docs/
│   ├── api.md             # API 文档
│   └── setup.md           # 安装指南
├── uploads/               # 上传文件目录
├── dicom_files/          # 转换后的文件目录
├── logs/                 # 日志目录
├── requirements.txt      # Python 依赖
└── .env                  # 环境变量
```

## 日志
- 日志文件位于 `logs` 目录
- 默认日志级别为 INFO
- 包含详细的请求和错误信息

## 故障排除

### 1. 文件上传失败
- 检查 `uploads` 目录权限
- 确保磁盘空间充足
- 查看日志文件中的详细错误信息

### 2. 转换失败
- 确保 DCMTK 正确安装并添加到 PATH
- 检查源文件格式是否支持
- 查看日志中的 img2dcm 命令输出

### 3. PACS 连接失败
- 验证 PACS 服务器地址和端口配置
- 检查网络连接
- 确认 PACS 服务器状态

## 安全注意事项
- 服务器默认只监听本地连接
- 所有上传的文件都会被分配唯一的 UUID
- 临时文件会在处理完成后自动删除
- 建议在生产环境中启用 HTTPS
