# 工程优化审计

本轮审计参考 Immich、PhotoPrism 和 Ente 的公开仓库、发布记录与问题讨论，只借鉴工程思想并独立实现，不复制 AGPL 源码。

## 已完成

| 范围 | 原问题 | 优化 |
| --- | --- | --- |
| SQLite 并发 | 默认 DELETE 日志、外键关闭 | 启用 WAL、外键、30 秒 busy timeout 与 NORMAL synchronous |
| 图片安全 | 只限制压缩文件大小 | 新增 4,000 万解码像素上限，并保留单文件和任务总大小限制 |
| 文件一致性 | 原图直接写最终路径 | 临时文件写入完成后原子替换，异常时清理原图与缩略图 |
| 后台任务 | 未预期异常可能遗留 `running` | 捕获工作器顶层异常，将失败原因持久化为可重试状态 |
| 搜索交互 | 慢请求可能覆盖后发查询 | 加入请求序号，只允许最后一次搜索更新界面 |
| 首屏容错 | 最近任务接口失败会连带图库加载失败 | 初始请求独立结算，非核心任务接口失败不阻断图库 |
| 前端负担 | 残留 D1、Drizzle、认证示例和模板图标 | 删除未使用模板代码与依赖，保留实际产品表面 |
| 依赖安全 | 开发工具链存在 7 个审计问题 | 升级 Vite、Cloudflare 插件和 Wrangler，完整审计归零 |
| GitHub 准备 | 无许可证、CI、贡献与安全说明 | 新增 MIT、GitHub Actions、配置样例、Makefile 和项目规范 |

## 验证门槛

- Python：Ruff、Pytest、字节码编译。
- Web：ESLint、完整生产构建、服务端渲染测试。
- 依赖：生产与开发依赖 `npm audit` 均为 0。
- 数据库：测试验证 WAL、外键和等待时间配置。
- GitHub：push 和 pull request 自动运行后端与前端检查。

## 暂不实施

- Docker：当前核心模型依赖 Apple Silicon MPS，本机原生运行更适合开发；容器化应在 CPU/Linux 兼容测试完成后进行。
- 公网部署：当前没有认证，且产品读取本机图库；安全策略明确要求只绑定 localhost。
- FAISS/Qdrant：10 张演示图库使用暴力余弦检索更简单可解释，扩大数据后再基准对比。
- 游标分页与虚拟列表：需要先补充图片尺寸元数据和千图压力测试。
- 感知哈希：精确 SHA-256 已稳定，近似重复检测将作为独立、可评测功能实现。

## 参考来源

- Immich：<https://github.com/immich-app/immich>
- PhotoPrism：<https://github.com/photoprism/photoprism>
- Ente：<https://github.com/ente-io/ente>
- PhotoPrism 发布记录：<https://github.com/photoprism/photoprism/releases>
