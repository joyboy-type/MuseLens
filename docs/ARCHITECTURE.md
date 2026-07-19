# MuseLens 系统架构

## 数据流

```text
React / Vite / TypeScript 前端
        ↓ 同源 HTTP
FastAPI 静态托管、输入校验与接口层
        ↓
ImageLibrary 业务层
   ↙          ↘
CLIP 编码器    SQLite Repository
   ↓                 ↓
SearchIndex      MuseLensLibrary
        ↘          ↙
        语义搜索结果

公开 Demo 的访客上传
        ↓
TemporaryGalleryService（限额、随机会话、TTL）
        ↓
每会话 SQLite + VectorIndex + 私有临时目录
        ↓
全局串行模型编码队列 → 仅返回本会话结果
```

## 代码边界

- `frontend/app`：页面组合、交互状态和响应式产品界面。
- `frontend/components`：搜索框、图片网格等可复用组件。
- `frontend/lib`：API 客户端和前后端类型契约。
- `src/muselens/api.py`：HTTP、CORS、请求校验和响应模型。
- `src/muselens/library.py`：导入、去重、编码和文件落盘流程。
- `src/muselens/encoder.py`：可替换的 CLIP 模型适配器。
- `src/muselens/index.py`：统一向量索引接口、NumPy 连续矩阵与可选 FAISS 精确检索。
- `src/muselens/duplicates.py`：感知哈希、归一化色彩约束与精确候选分块分组。
- `src/muselens/repository.py`：SQLite 持久化与启动恢复。
- `src/muselens/sessions.py`：访客临时图库、会话隔离、资源上限与到期清理。
- `scripts`：可重复的数据下载与离线评测任务。
- `deploy/huggingface`：Space 元数据模板，不保存业务代码副本。
- `Dockerfile`：先构建前端，再生成只包含 FastAPI 运行时的单容器镜像。

## 开源项目借鉴

本项目只借鉴成熟产品的信息架构与工程思想，没有复制其源码或品牌视觉。

- Immich：自托管相册、重复检测、CLIP 语义搜索、图片库与机器学习服务分层。
- PhotoPrism：本地优先、组合搜索、响应式图片浏览与隐私说明。
- Ente Photos：隐私优先、后台导入和跨端产品一致性。

这些项目规模远大于 MuseLens。当前版本刻意保留一个小型、可解释的架构，后续再以接口替换的方式加入 FAISS/Qdrant、缩略图任务和分页，而不是提前复制大型系统复杂度。

详细调研、许可证边界和实施优先级见 `OPEN_SOURCE_RESEARCH.md`。

## 当前取舍

- 使用 SQLite 保存元数据和小规模向量，降低本地启动门槛。
- 默认使用连续 NumPy 矩阵进行精确余弦检索；FAISS 保留为兼容平台的可选后端，数据扩大到
  至少 5 万张后再判断是否需要 ANN 或独立向量服务。
- 图片导入到专用目录，不直接操作原始图片。
- 导入时同时计算 SHA-256、64 位感知哈希和平均色彩。SHA-256 跳过完全相同文件；感知哈希
  识别缩放、压缩等近似副本，删除动作只作用于专用目录里的导入副本。
- 导入时生成最长边 640px 的版本化 WebP 缩略图；旧图片首次请求时自动补建，图库与灯箱分别加载缩略图和原图。
- 文件夹导入先写入本地暂存区，任务与逐文件状态保存到 SQLite；模型分批后台索引，服务中断后任务转为可重试状态。
- CLIP 延迟加载，健康检查和普通列表请求不会占用模型内存。
- `local` 模式开放导入和持久化，定位为个人本地图库。
- `demo` 模式从固定种子恢复示例图库；持久化写接口返回 403。访客上传使用独立临时 API，
  每个会话拥有自己的文件目录、SQLite 元数据和内存向量索引，不会污染示例图库。
- 临时图库限制文件数、单文件和总大小、全局活动会话数；模型任务串行执行，完成后默认
  保留 30 分钟并由周期任务清理，服务重启也会清空全部访客状态。
- 官方固定语料与用户图库使用不同的搜索契约：固定语料沿用留出集校准的拒答值；本地
  持久化图库和访客临时图库均不设绝对门槛，始终保留最佳匹配，再用相对分差截断弱结果。
- 编码器使用互斥推理和 100 项文本向量 LRU 缓存；临时图库批量编码图片，避免重复加载、
  并发推理竞争和逐张调用模型。
- 生产环境由 FastAPI 同源托管 Vite 静态产物，避免跨域配置和双进程容器。
- GitHub 是唯一源码仓库；Space 发布目录由 CI 临时组装，避免部署副本长期漂移。
