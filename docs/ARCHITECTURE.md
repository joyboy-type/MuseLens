# MuseLens 系统架构

## 数据流

```text
React / TypeScript 前端
        ↓ HTTP
FastAPI 输入校验与接口层
        ↓
ImageLibrary 业务层
   ↙          ↘
CLIP 编码器    SQLite Repository
   ↓                 ↓
VectorIndex      MuseLensLibrary
        ↘          ↙
        语义搜索结果
```

## 代码边界

- `frontend/app`：页面组合、交互状态和响应式产品界面。
- `frontend/components`：搜索框、图片网格等可复用组件。
- `frontend/lib`：API 客户端和前后端类型契约。
- `src/muselens/api.py`：HTTP、CORS、请求校验和响应模型。
- `src/muselens/library.py`：导入、去重、编码和文件落盘流程。
- `src/muselens/encoder.py`：可替换的 CLIP 模型适配器。
- `src/muselens/index.py`：统一向量索引接口与余弦检索。
- `src/muselens/repository.py`：SQLite 持久化与启动恢复。
- `scripts`：可重复的数据下载与离线评测任务。

## 开源项目借鉴

本项目只借鉴成熟产品的信息架构与工程思想，没有复制其源码或品牌视觉。

- Immich：自托管相册、重复检测、CLIP 语义搜索、图片库与机器学习服务分层。
- PhotoPrism：本地优先、组合搜索、响应式图片浏览与隐私说明。
- Ente Photos：隐私优先、后台导入和跨端产品一致性。

这些项目规模远大于 MuseLens。当前版本刻意保留一个小型、可解释的架构，后续再以接口替换的方式加入 FAISS/Qdrant、缩略图任务和分页，而不是提前复制大型系统复杂度。

详细调研、许可证边界和实施优先级见 `OPEN_SOURCE_RESEARCH.md`。

## 当前取舍

- 使用 SQLite 保存元数据和小规模向量，降低本地启动门槛。
- 使用内存暴力检索保证基线结果可解释；数据扩大后再对比 ANN 索引。
- 图片导入到专用目录，不直接操作原始图片。
- 导入时生成最长边 640px 的版本化 WebP 缩略图；旧图片首次请求时自动补建，图库与灯箱分别加载缩略图和原图。
- 文件夹导入先写入本地暂存区，任务与逐文件状态保存到 SQLite；模型分批后台索引，服务中断后任务转为可重试状态。
- CLIP 延迟加载，健康检查和普通列表请求不会占用模型内存。
- 前端直接连接本机 FastAPI，因此当前版本定位为本地应用，不部署到公共网站。
