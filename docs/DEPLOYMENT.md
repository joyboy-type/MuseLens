# MuseLens 部署设计

## 结论

MuseLens 不维护第二份“部署版源码”。GitHub 主仓库是唯一代码源，公共演示通过 CI
生成临时发布树。部署目录只保存 Hugging Face 与 ModelScope 的平台元数据模板。

## 为什么这样设计

- 大型检索项目通常拆分前端、后端、编码和索引，而不是复制一个只读版本。
- 固定语料的只读属性来自服务端能力边界，不能只隐藏上传按钮。访客上传走独立的临时
  会话服务，不会混入固定语料或其他访客的索引。
- MuseLens 只有一个客户端页面，不需要 SSR。React/Vite 静态构建比原 Cloudflare
  Worker 构建链更适合 FastAPI 和 Hugging Face Docker Space。
- 单容器同源部署减少 CORS、反向代理、两个进程和两套健康检查。
- Docker 显式安装 PyTorch CPU wheel，避免免费 CPU Space 意外打包 CUDA 运行库。
- 公共 SigLIP2 权重在 Docker 构建阶段写入模型缓存，避免把首次下载等待转嫁给访客。

## 运行配置

| 配置 | `local` | `demo` |
|---|---|---|
| 固定图库导入 | 开放 | API 返回 403 |
| 持久化批量索引与重试 | 开放 | API 返回 403 |
| 访客临时图库 | 不需要 | 开放，默认最多 30 张 |
| 文本搜索 | 开放 | 开放 |
| 以图搜图 | 开放 | 临时处理，不保存查询图 |
| 数据来源 | 用户专用目录 | 固定许可语料 + 访客会话图片 |
| 持久化 | Docker volume / 本机目录 | 固定语料启动恢复；访客数据不持久化 |
| 访客隔离 | 不适用 | 128-bit 随机会话 ID，各自 SQLite 与向量索引 |
| 自动清理 | 不适用 | 默认完成索引 30 分钟后删除，也可主动删除 |

## 公共演示资源边界

每个临时图库默认限制为 30 张图片、单张 8 MB、合计 120 MB；同一实例最多保留 8 个
活动会话。图片先经过 MIME、大小和 Pillow 解码校验，再交给一个全局串行编码队列，避免
免费 CPU 实例因并发加载模型而耗尽内存。临时图片响应使用 `private, no-store` 缓存策略。

会话 ID 是临时访问凭据，而不是登录认证。生产入口仍应增加平台级请求大小、速率限制和
并发限制；如需长期个人图库，应运行 `local` 模式或在后续版本加入真实账户与对象存储。

## 发布链路

```text
GitHub main
  → CI 与测试
  → 平台打包器选择运行所需文件
  → 替换为对应平台的 README
  → Hugging Face Space 或 ModelScope Studio Docker build
  → FastAPI :7860 同源提供 SPA、API 与图片
```

`.github/workflows/deploy-space.yml` 目前只允许手动触发，并要求：

1. `demo_assets/manifest.json` 已存在，防止发布空图库；
2. GitHub Actions Secret `HF_TOKEN` 已配置；
3. 演示图片均可公开再分发，来源和许可证记录在 manifest 中。

Space 环境会提供 `SPACE_ID`，MuseLens 因此默认进入 `demo` 模式。其他环境默认进入
`local` 模式，也可以通过 `MUSELENS_MODE` 显式覆盖。

ModelScope 不依赖隐式平台检测：`ms_deploy.json` 显式注入 `MUSELENS_MODE=demo`。手动
GitHub Actions 工作流将最小发布包推送到 Studio，调用 OpenAPI 部署，等待健康状态后运行
跨类别中英文合同。两条发布路径共用同一个 Dockerfile、API 和前端。

固定演示语料由 `scripts/prepare_demo_assets.py` 从本地 COCO 2017 validation 数据中
确定性选取。构建脚本仅保留 Flickr 官方元数据仍显示为 CC BY 2.0 的图片，并为每张图片
记录标题、作者、原始页面、许可证、SHA-256 和检索索引身份。Docker 演示不使用旧的
绝对分数门槛；小型图库依赖相对分数窗口，以避免 SigLIP2 的分数标定差异导致有效查询
被错误清空。
