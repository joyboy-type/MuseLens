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

## 自动发布链路

仓库包含以下组件：

- `scripts/package_modelscope.py`：只打包 Docker、前后端源码、许可演示语料和部署配置；
- `scripts/publish_modelscope.py`：验证发布包，通过临时 Git AskPass 推送，不把令牌写进 URL；
- `scripts/wait_for_deployment.py`：容忍平台构建和冷启动，直到健康合同通过；
- `scripts/smoke_deployment.py`：验证只读 403 和跨类别中英文检索质量；
- `.github/workflows/deploy-modelscope.yml`：串联打包、推送、OpenAPI 部署和线上验收。

工作流只允许从 `main` 发布，并绑定 GitHub `production` Environment。并发策略不会取消已经
开始的生产部署，避免一次新的点击把正在发布的实例停在中间状态。

## 首次账号与 Studio 配置

自动化不能代替平台要求的实名认证。首次发布需要完成一次人工身份和资源选择：

1. 注册并登录 ModelScope，绑定完成实名认证的阿里云账号；
2. 创建公开的“编程式创空间”，英文名建议 `MuseLens`，SDK 选择 Docker，资源选择免费的
   `2 vCPU / 16 GB`；
3. 在个人中心创建具有仓库写入能力的 Access Token；
4. 在 GitHub 仓库的 `production` Environment 中新增 Secret：
   `MODELSCOPE_API_TOKEN`；令牌不得写入 `.env`、命令历史、文档或仓库；
5. 合并当前 PR 到 `main` 后，在 GitHub Actions 手动运行 `Deploy ModelScope Studio`，输入：
   - `studio_id`：ModelScope 的 `用户名/MuseLens`；
   - `public_url`：Studio 实际对外应用 URL，首次不确定时可留空，发布后再补做验收。

工作流会生成发布包、推送到 Studio 的 `master` 分支、调用官方 OpenAPI 的 deploy 接口，
并在填写公开 URL 时最长等待 30 分钟完成构建和冷启动。

## 本地预检与手动发布

不需要令牌即可验证发布包：

```bash
MODELSCOPE_STUDIO_ID=你的用户名/MuseLens make package-modelscope
```

需要绕过 GitHub Actions 手动发布时：

```bash
python scripts/package_modelscope.py /tmp/muselens-modelscope
read -s "MODELSCOPE_API_TOKEN?ModelScope Token: "
export MODELSCOPE_API_TOKEN
python scripts/publish_modelscope.py /tmp/muselens-modelscope \
  --repo-id 你的用户名/MuseLens --deploy
unset MODELSCOPE_API_TOKEN
```

发布后先运行跨 4 类内容的 8 条中英文快速合同：

```bash
python scripts/smoke_deployment.py https://你的-Studio-地址 \
  --contract quick --min-hit-at-5 0.9 --timeout 300
```

再运行全部 54 条查询并保存机器可读报告：

```bash
python scripts/evaluate_demo_search.py https://你的-Studio-地址 \
  --output artifacts/evaluations/modelscope-demo-search-v1.json
```

发布验收至少要求：固定图库为 24 张、模式为 `demo`、固定图库写接口返回 403、英文与中文
正例 Top-5 命中，以及图库外查询的已知能力边界与页面文案一致。

ModelScope 官方 Docker Studio 文档要求服务监听 `0.0.0.0:7860`，并说明运行时环境变量可在
Studio 设置页管理；项目当前配置已直接把非敏感运行变量写入 `ms_deploy.json`，密钥仍不得
提交到仓库。Docker Studio 目前还要求实名认证并绑定已实名的阿里云账号。

ModelScope Docker Studio 的构建期暂不支持注入环境变量，所以 MuseLens 不依赖构建期密钥。
模型是公开权重，固定图库也全部来自仓库中的许可语料。

## 为什么不把 Qwen 精排放进免费 Studio

Qwen3-VL-Reranker-2B 权重约 4.27 GB。它在 M4 本地能显著提升排序与图库外拒绝，但在
2 核 CPU 免费实例上会增加镜像体积、冷启动和逐候选延迟。公开演示的职责是可访问、可上传
临时图库并展示真实向量检索；高精度模式用于本地面试演示或未来具备足够算力的实例。

## 官方资料

- ModelScope Studio 创建与部署：https://www.modelscope.cn/docs/studios/create
- ModelScope Docker Studio：https://www.modelscope.cn/docs/studios/docker
- ModelScope OpenAPI：https://modelscope.cn/docs/openapi
- Qwen3-VL-Embedding 与 Reranker：https://github.com/QwenLM/Qwen3-VL-Embedding
