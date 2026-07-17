# MuseLens

本地优先的多模态图片搜索与智能整理系统。用户导入自己的图片后，可以用中文或英文自然语言搜索，也可以上传一张图片查找视觉相似内容。

导入图片的副本默认保存在 `~/Pictures/MuseLensLibrary/` 专用目录，不移动、覆盖或删除用户原始照片。

## 当前进度

- [x] 可安装的 Python 工程骨架
- [x] Apple Silicon MPS / CUDA / CPU 自动选择
- [x] CLIP / SigLIP2 通用延迟加载适配器
- [x] 内存向量索引与余弦检索
- [x] 图片导入、文本搜索、以图搜图 API 骨架
- [x] 不下载模型即可运行的基础测试
- [x] Flickr8k 100图/500查询的首个零样本检索基线
- [x] SQLite 图片元数据与向量持久化
- [x] SHA-256 去重与批量导入
- [x] 服务重启后自动恢复向量索引
- [ ] FAISS/Qdrant 向量索引
- [x] 中英文检索基线、模型对比与安全向量迁移
- [x] 冻结主干的双塔残差 Adapter 与对称 InfoNCE 训练骨架
- [x] 5000/500/100 官方 split Adapter 训练、消融与最终测试
- [ ] 重复图片检测与自动标签
- [x] Recall@K、MRR 与编码延迟评测
- [x] React + TypeScript 响应式图片画廊前端
- [x] 版本化 WebP 缩略图缓存与旧图片按需补建
- [x] SQLite 持久化后台索引任务、实时进度与失败重试
- [x] 无关查询拒答评测、校准/留出切分与阈值策略对比
- [x] GitHub Actions CI
- [ ] Docker 与演示视频

## 快速开始

```bash
cd /Users/joyboy/Desktop/AI-Engineering-Portfolio/MuseLens
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

启动 API：

```bash
uvicorn muselens.api:app --reload
```

打开 <http://127.0.0.1:8000/docs>，可在交互式文档中测试接口。

另开一个终端启动前端：

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 <http://localhost:3000>。界面支持文件夹批量导入、语义搜索、瀑布流结果、匹配度展示和图片灯箱预览。

也可以使用统一命令：

```bash
make install
make lint
make test
```

配置项示例见 `.env.example`。本项目没有认证层，API 只应绑定本机地址，不应直接暴露到公网。

运行可复现的文本搜图基线：

```bash
python scripts/download_evaluation_sample.py --count 100
python scripts/evaluate_retrieval.py --batch-size 16
python scripts/evaluate_rejection.py
```

首个小样本结果：Recall@1 0.852、Recall@5 0.976、Recall@10 0.998、MRR 0.908。候选集只有100张图片，因此这只是工程基线，不代表最终系统效果。详见 `docs/BASELINE_RESULTS.md`。

中英文成对查询实验中，默认模型升级为 SigLIP2：中文 Recall@1 从 3.3% 提升到 96.7%，英文 Recall@1 为 100%。模型切换同时包含向量隔离、安全重建和拒答阈值再校准。详见 `docs/MULTILINGUAL_RESULTS.md`。

轻量 Adapter 在5000张训练图上完成真实训练与消融，但最终英文收益可以忽略，中文 Recall@1 反而下降3.4个百分点，因此没有为了展示“训练成功”而上线。完整结果和决策见 `docs/TRAINING_RESULTS.md`。

无关查询拒答实验中，留出集综合分数由 0.923 提升到 0.974；动态 z-score 未超过校准固定阈值，因此没有为了复杂度强行上线。详见 `docs/REJECTION_RESULTS.md`。

## 接口

- `GET /health`：服务、模型和索引状态
- `GET /v1/images`：已索引图片
- `GET /v1/images/{image_id}/content`：读取原图
- `GET /v1/images/{image_id}/thumbnail`：读取或按需生成缓存缩略图
- `POST /v1/images`：导入图片并生成向量
- `POST /v1/images/batch`：批量导入、批量编码并自动去重
- `POST /v1/import-jobs`：创建持久化后台导入任务
- `GET /v1/import-jobs/latest`：恢复最近一次任务状态
- `GET /v1/import-jobs/{job_id}`：查询任务进度
- `POST /v1/import-jobs/{job_id}/retry`：重试失败文件
- `POST /v1/search/text`：文本搜索图片
- `POST /v1/search/image`：以图搜图

## 学习方式

从 `docs/DAY_01.md` 开始。每完成一个模块，在 `docs/LEARNING_LOG.md` 中回答“用途、原理、替代方案、验证方法”四个问题。详细路线见 `docs/PROJECT_PLAN.md`。

系统分层见 `docs/ARCHITECTURE.md`，开源项目调研、许可证边界和功能决策见 `docs/OPEN_SOURCE_RESEARCH.md`。

高收藏图文检索项目的训练规模对比，以及针对 M4 16 GB 的取舍见 `docs/GITHUB_TRAINING_RESEARCH.md`。

本轮可靠性、安全、依赖和 GitHub 准备审计见 `docs/ENGINEERING_AUDIT.md`。项目采用 MIT 许可证；贡献和安全报告方式分别见 `CONTRIBUTING.md` 与 `SECURITY.md`。
