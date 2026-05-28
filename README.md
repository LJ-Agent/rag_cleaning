# RAG-CLEANING — 独立文档清洗服务

RAG 系统的统一数据入口，提供多格式文档解析、元素级增强处理、通用清洗和质量校验，输出标准 Markdown + 结构化元数据。

## 架构概览

```
接入层 (HTTP/gRPC/Kafka) → 任务调度路由 → 格式预处理 (PDF/Word/Excel/PPT/MD/TXT)
→ 公用元素引擎 (表格/图片/公式) → 通用清洗 (基础清洗/内容过滤/结构修正/脱敏)
→ 质量校验 → 输出 (Markdown + JSON 元数据) → 下游 RAG 服务
```

## 支持的格式

| 格式 | 预处理方式 | 支持元素 |
|------|-----------|---------|
| PDF | pypdf + pdfplumber | 文本/表格/图片 |
| DOCX | python-docx | 文本/表格/图片/标题层级 |
| XLSX | openpyxl | 单元格数据/多 Sheet |
| PPTX | python-pptx | 文本/形状/表格/图片/备注 |
| Markdown | 正则解析 | 标题/代码块/引用/列表 |
| TXT | 多编码解析 | 纯文本段落 |

## 快速开始

### 安装依赖

```bash
cd RAG-CLEANING
pip install -e .
pip install -e ".[dev]"  # 含开发工具
```

### 配置

编辑 `config/settings.yaml` 或通过环境变量覆盖（`${VAR:default}` 语法）：

```bash
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export MINIO_ENDPOINT=localhost:9000
export LLM_API_KEY=your-api-key
```

### 启动服务

```bash
PYTHONPATH=src python -m src.main
```

### 编译 Proto

```bash
python scripts/compile_proto.py
```

### Docker 部署

```bash
cd docker
docker-compose up -d
```

## 服务端口

| 服务 | 端口 | 协议 |
|------|------|------|
| CleaningService | 50056 | gRPC |

## Kafka 主题

### 消费主题
- `rag-cleaning-task-submit` — 任务提交入口
- `rag-cleaning-{format}-preprocess` — 各格式预处理
- `rag-cleaning-element-{type}` — 元素处理 (table/image/formula)
- `rag-cleaning-general-input` — 通用清洗输入
- `rag-cleaning-retry` — 重试队列

### 生产主题
- `rag-cleaning-unified-input` — 统一 Document 后
- `rag-cleaning-complete` — 清洗完成
- `rag-cleaning-failed` — 清洗失败
- `rag-cleaning-dlq` — 死信队列

## 项目结构

```
RAG-CLEANING/
├── config/settings.yaml       # 服务配置
├── proto/cleaning.proto       # gRPC 接口定义
├── scripts/compile_proto.py   # Proto 编译
├── src/
│   ├── main.py                # 入口点
│   ├── common/                # 共享模块 (配置/模型/异常/工具)
│   ├── infrastructure/        # 基础设施 (MinIO/Redis/LLM)
│   ├── preprocessing/         # 格式预处理层 (6 种格式)
│   ├── elements/              # 公用元素引擎 (表格/图片/公式/缓存)
│   ├── cleaning/              # 通用清洗层 (5 个模块)
│   ├── output/                # 输出层 (Markdown/元数据)
│   ├── scheduling/            # 调度层 (路由/重试/DLQ/状态机)
│   └── communication/         # 通信层 (gRPC/Kafka)
├── tests/                     # 测试
├── docker/                    # Docker 部署
└── pyproject.toml             # 项目元数据
```

## 数据流程

```
文件上传 → 任务提交 (Kafka)
→ 格式路由 (FormatRouter)
→ 预处理 (PDF/Word/Excel/PPT/MD/TXT Preprocessor)
→ 统一 Document 对象
→ 元素处理 (Table/Image/Formula Processor)
→ 通用清洗 (BasicCleaner → ContentFilter → StructureFixer → SensitiveMasker)
→ 质量校验 (QualityValidator, 四维评分)
→ Markdown + JSON 输出 → MinIO 存储
→ 完成通知 (Kafka) → 下游 RAG 分块服务
```

## 开发

```bash
# 代码检查
ruff check src/

# 代码格式化
ruff format src/

# 类型检查
mypy src/

# 运行测试
pytest
```
