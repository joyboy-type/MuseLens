# MuseLens Web

MuseLens 的本地图库前端，负责文件夹导入、后台索引进度、语义搜索、缩略图瀑布流和原图预览。

## 本地运行

先启动项目根目录的 FastAPI 服务，再运行：

```bash
npm install
npm run dev
```

默认访问 <http://localhost:3000>，Vite 会把 API 请求转发到
<http://localhost:8000>。如需连接其他后端，在本地 `.env` 中设置：

```bash
VITE_MUSELENS_API=http://localhost:8000
```

## 验证

```bash
npm run lint
npm test
npm audit --omit=dev
```

生产构建是静态 SPA，由 FastAPI 在同一个 Docker 容器中托管。界面根据 `/health`
返回的能力自动切换：本地模式显示导入流程，公开演示模式显示固定图库标识。
