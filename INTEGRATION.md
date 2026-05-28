# RAG 系统集成说明

## 集成架构

```
RAG-BACKEND (Java)                     RAG-CLEANING                     RAG-PYTHON
      │                                      │                               │
      │  Kafka: rag-file-process             │                               │
      ├─────────────────────────────────────►│                               │
      │                                      │  多格式清洗                    │
      │                                      │  ├─ 格式预处理                │
      │                                      │  ├─ 元素处理                  │
      │                                      │  ├─ 通用清洗                  │
      │                                      │  └─ 质量校验                  │
      │                                      │                               │
      │  Kafka: rag-cleaning-complete        │                               │
      │◄─────────────────────────────────────┤                               │
      │                                      │                               │
      │  Kafka: rag-chunk-process            │                               │
      ├──────────────────────────────────────┼──────────────────────────────►│
      │                                      │                               │
      │                                      │      Kafka: rag-task-complete │
      │◄─────────────────────────────────────┼──────────────────────────────┤
```

## 集成清单

### 1. RAG-CLEANING (本服务)
- [x] 项目脚手架与基础设施
- [x] 统一数据模型与状态机
- [x] 格式分支预处理层 (PDF/Word/Excel/PPT/MD/TXT)
- [x] 公用元素处理引擎 (表格/图片/公式)
- [x] 通用清洗与增强层
- [x] 输出层 (Markdown + 元数据)
- [x] gRPC 服务 (端口 50056)
- [x] Kafka 异步驱动 (15个Topic)
- [x] 任务调度与路由
- [x] Docker 部署支持

### 2. RAG-PYTHON
- [x] 添加清洗服务配置 (`settings.yaml`)
- [x] 添加清洗 Topic 常量 (`kafka_constants.py`)
- [ ] FILE_PROCESS handler 更新为调用清洗服务 (gRPC 客户端)
- [ ] 消费 `rag-cleaning-complete` 事件自动触发分块

### 3. RAG-BACKEND
- [ ] 添加清洗服务 gRPC 客户端
- [ ] 文档状态机：UPLOADED → PARSING → CLEANING → PENDING_REVIEW
- [ ] Kafka 生产者配置清洗 Topic
- [ ] 消费清洗完成事件更新文档状态

### 4. 基础设施
- [ ] docker-compose.yml 添加 RAG-CLEANING 容器
- [ ] MinIO bucket 配置清洗结果路径
- [ ] Kafka 创建清洗相关 Topic

## 渐进式迁移策略

1. **并行运行**: 新旧清洗逻辑同时运行，对比结果
2. **灰度切换**: 部分知识库启用新清洗服务
3. **全量切换**: 所有文档走 RAG-CLEANING

## 测试验证

```bash
# 1. 启动清洗服务
cd RAG-CLEANING && PYTHONPATH=src python -m src.main

# 2. 发送测试任务 (Kafka)
echo '{"taskId":"test-001","taskType":"FILE_PROCESS","documentId":"1","kbId":1,"data":{"fileName":"test.pdf","fileUrl":"rag-documents/test.pdf"}}' | kafka-console-producer --topic rag-cleaning-task-submit --bootstrap-server localhost:9092

# 3. 验证清洗结果
# 检查 MinIO: rag-documents/cleaned/default/1.md
# 检查 MinIO: rag-documents/cleaned/default/1.json
```
