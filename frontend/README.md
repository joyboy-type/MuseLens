# MuseLens Web

MuseLens 的本地图库前端，负责文件夹导入、后台索引进度、语义搜索、缩略图瀑布流和原图预览。

## 本地运行

先启动项目根目录的 FastAPI 服务，再运行：

```bash
npm install
npm run dev
```

默认访问 <http://localhost:3000>，并连接 <http://localhost:8000>。如需修改后端地址，在本地 `.env` 中设置：

```bash
NEXT_PUBLIC_MUSELENS_API=http://localhost:8000
```

## 验证

```bash
npm run lint
npm test
npm audit --omit=dev
```

当前前端依赖本机图片库和 Python 模型服务，因此定位为本地应用，不单独部署为公共网站。
