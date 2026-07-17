# MuseLens 部署设计

## 结论

MuseLens 不维护第二份“部署版源码”。GitHub 主仓库是唯一代码源，公共演示通过 CI
生成临时发布树。部署目录只保存 Hugging Face 元数据模板。

## 为什么这样设计

- 大型检索项目通常拆分前端、后端、编码和索引，而不是复制一个只读版本。
- 固定语料演示的只读属性来自服务端能力边界和预计算索引，不能只隐藏上传按钮。
- MuseLens 只有一个客户端页面，不需要 SSR。React/Vite 静态构建比原 Cloudflare
  Worker 构建链更适合 FastAPI 和 Hugging Face Docker Space。
- 单容器同源部署减少 CORS、反向代理、两个进程和两套健康检查。
- Docker 显式安装 PyTorch CPU wheel，避免免费 CPU Space 意外打包 CUDA 运行库。

## 运行配置

| 配置 | `local` | `demo` |
|---|---|---|
| 文件夹导入 | 开放 | API 返回 403 |
| 批量索引与重试 | 开放 | API 返回 403 |
| 文本搜索 | 开放 | 开放 |
| 以图搜图 | 开放 | 临时处理，不保存查询图 |
| 数据来源 | 用户专用目录 | 带许可证清单的固定语料 |
| 持久化 | Docker volume / 本机目录 | 启动时复制到临时运行目录 |

## 发布链路

```text
GitHub main
  → CI 与测试
  → package_space.py 选择运行所需文件
  → 用 Space README 替换项目 README
  → Hugging Face Docker build
  → FastAPI :7860 同源提供 SPA、API 与图片
```

`.github/workflows/deploy-space.yml` 目前只允许手动触发，并要求：

1. `demo_assets/manifest.json` 已存在，防止发布空图库；
2. GitHub Actions Secret `HF_TOKEN` 已配置；
3. 演示图片均可公开再分发，来源和许可证记录在 manifest 中。

Space 环境会提供 `SPACE_ID`，MuseLens 因此默认进入 `demo` 模式。其他环境默认进入
`local` 模式，也可以通过 `MUSELENS_MODE` 显式覆盖。
