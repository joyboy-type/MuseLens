# ModelScope Studio 国内公开演示

## 定位

MuseLens 的国内公开演示优先使用 ModelScope Studio Docker 模式。项目根目录的
`ms_deploy.json` 已声明 Docker SDK、7860 端口和平台 CPU 资源；Studio 构建时直接复用
项目现有 `Dockerfile`，不维护第二套应用源码。配置文件同时注入
`MUSELENS_MODE=demo` 和 `MUSELENS_SEARCH_MIN_SCORE=-1`，因此不能依赖平台是否提供某个
特定环境变量来猜测运行模式，也不会误把公开服务启动成可写的本地模式。

公开演示保持轻量配置：

- SigLIP2 文本/图片向量召回；
- 24 张可署名固定图库；
- 访客临时图库隔离、限额和 30 分钟 TTL；
- `MUSELENS_MODE=demo` 下禁止修改固定图库；
- 不启用 4.27 GB Qwen3-VL 精排，以控制 CPU 冷启动和单查询延迟。

本地 M4 高精度模式与公开轻量模式使用同一 API；差异仅由
`MUSELENS_RERANKER_MODEL` 环境变量控制。

## 后续账号步骤

当前不需要为了开发中断去注册账号。准备发布时：

1. 注册并登录 ModelScope。
2. 创建 Studio，选择 Docker SDK。
3. 将当前 GitHub 仓库内容推送或导入 Studio 仓库，确保根目录包含 `Dockerfile` 和
   `ms_deploy.json`。
4. 等待构建完成，访问 Studio 地址并检查 `/health`。
5. 先运行跨 4 类内容的 8 条中英文快速合同：

```bash
python scripts/smoke_deployment.py https://你的-Studio-地址 \
  --contract quick --min-hit-at-5 0.9 --timeout 300
```

6. 再运行全部 54 条查询并保存机器可读报告：

```bash
python scripts/evaluate_demo_search.py https://你的-Studio-地址 \
  --output artifacts/evaluations/modelscope-demo-search-v1.json
```

发布验收至少要求：固定图库为 24 张、模式为 `demo`、固定图库写接口返回 403、英文与中文
正例 Top-5 命中，以及图库外查询的已知能力边界与页面文案一致。

ModelScope 官方 Docker Studio 文档要求服务监听 `0.0.0.0:7860`，并说明运行时环境变量可在
Studio 设置页管理；项目当前配置已直接把非敏感运行变量写入 `ms_deploy.json`，密钥仍不得
提交到仓库。Docker Studio 目前还要求实名认证并绑定已实名的阿里云账号。

## 为什么不把 Qwen 精排放进免费 Studio

Qwen3-VL-Reranker-2B 权重约 4.27 GB。它在 M4 本地能显著提升排序与图库外拒绝，但在
2 核 CPU 免费实例上会增加镜像体积、冷启动和逐候选延迟。公开演示的职责是可访问、可上传
临时图库并展示真实向量检索；高精度模式用于本地面试演示或未来具备足够算力的实例。

## 官方资料

- ModelScope Studio 创建与部署：https://www.modelscope.cn/docs/studios/create
- ModelScope Docker Studio：https://www.modelscope.cn/docs/studios/docker
- Qwen3-VL-Embedding 与 Reranker：https://github.com/QwenLM/Qwen3-VL-Embedding
