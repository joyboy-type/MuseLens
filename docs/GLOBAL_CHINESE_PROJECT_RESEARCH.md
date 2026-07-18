# 中国 AI 项目的国际化开源与部署调研

## 结论

MuseLens 采用中国头部开源 AI 项目已经验证过的“双平台、单源码、多运行档位”模式：

1. GitHub 主仓库作为唯一源码和国际开发者入口；
2. Hugging Face 提供国际演示镜像，ModelScope 提供中国可访问镜像；
3. 本地 Web Demo、Docker 和 HTTP API 共用同一核心实现；
4. 免费 CPU 演示运行轻量召回，本地 M4 或未来 GPU 实例启用高精度精排；
5. 用可复现中英文评测报告证明能力，不用单个精心选择的关键词代替验收。

这里借鉴的是发布结构和工程原则，不复制其他项目源码或界面资产。

## 参考项目与可复用做法

### Qwen3-VL（阿里云 Qwen 团队）

官方仓库同时链接 Hugging Face 与 ModelScope 模型集合，为中国大陆用户明确推荐
ModelScope；另外提供 Web Demo、预构建 Docker 镜像，以及 vLLM/SGLang 的 API 服务方式。

MuseLens 对应决策：双平台入口、单容器 Web/API、本地轻量和高精度两档运行配置。

- https://github.com/QwenLM/Qwen3-VL

### InternVL（上海 AI Lab / OpenGVLab）

模型表为同一个版本同时给出 Hugging Face 与 ModelScope 链接，并提供较小视觉编码器和
在线 Web UI。其发布方式说明“中国可访问镜像”不应成为与国际版本分叉的第二套代码。

MuseLens 对应决策：保留一个 GitHub 主线，同一个模型身份和 API 契约跨平台验收。

- https://github.com/OpenGVLab/InternVL

### Chinese-CLIP（OFA-Sys）

项目不仅发布推理 API，还公开训练、评测、数据格式、ONNX/TensorRT 部署路径和在线 Demo；
模型下载允许切换 ModelScope，评测报告使用 Recall/Top-K 等可复现指标。

MuseLens 对应决策：训练和失败实验也保留机器可读产物；部署必须运行真实检索评测，而不是
只检查首页能否打开。

- https://github.com/OFA-Sys/Chinese-CLIP

### BGE / Visualized-BGE（北京智源 FlagOpen）

Visualized-BGE 明确覆盖文本、图片、图文组合等多模态检索输入，并发布数据、微调和零样本
评测。BGE 主仓库同时维护英文和中文文档入口。

MuseLens 对应决策：仓库新增英文入口；把文本搜图、以图搜图与未来组合查询放在同一检索
工程中，并分别报告能力边界。

- https://github.com/FlagOpen/FlagEmbedding
- https://github.com/FlagOpen/FlagEmbedding/tree/master/research/visual_bge

### ModelScope Docker Studio

官方文档要求 Docker 服务监听 `0.0.0.0:7860`，支持 FastAPI 等自定义应用，运行时变量可由
Studio 注入；持久化目录是 `/mnt/workspace`。MuseLens 的公开访客图库刻意保持临时和隔离，
因此不写入持久卷；固定许可语料在镜像中确定性恢复。

- https://www.modelscope.cn/docs/studios/docker
- https://modelscope.cn/api/v1/studios/deploy_schema.json

## 已落地到 MuseLens 的改造

- `ms_deploy.json` 强制注入 `MUSELENS_MODE=demo`，避免公开实例误启可写模式；
- 保留 Hugging Face、ModelScope、Cloud Run 和本地 Docker 的同一构建入口；
- 新增英文 README，与中文文档互相链接；
- 部署快速验收从单个 `dog` 改为 4 类、8 条中英文查询，Hit@5 门槛为 90%；
- 完整发布验收继续运行 44 条正例与 10 条图库外查询，并输出 JSON；
- 免费 CPU 演示不加载 4.27 GB Qwen 精排，本地 M4 高精度模式继续保留。

## 暂不照搬的部分

- 不引入 vLLM/SGLang：它们面向生成式大模型服务，当前检索编码器在 M4 与免费 CPU 上不需要；
- 不为 ModelScope 复制第二份前后端：会产生行为漂移，削弱工程可信度；
- 不承诺免费 CPU 上的高精度 Qwen 精排：公开演示首先保证可访问和真实检索；
- 不切换到未经同一数据合同验证的新模型：平台可用性不能替代精度与资源评测。
