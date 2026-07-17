# COCO 5000 图真实 API 规模测试

## 结论

MuseLens 已通过真实 HTTP 接口完成 COCO 2017 validation 全部 5000 张图片的后台导入、
文本检索和服务重启恢复。测试没有绕过 FastAPI，也没有直接在离线矩阵上伪造产品指标。

当前 NumPy/Python 线性索引在 5000 图规模仍能工作，但平均查询延迟从 1000 图的 16.87 ms
升至 51.40 ms，P99 达到 106.93 ms。下一阶段引入矩阵化索引并与 FAISS 对比已有充分依据，
不再是为了堆技术栈而过度设计。

后续优化已经完成：连续 NumPy 矩阵将相同 5000 图协议的平均热查询降至 18.31 ms，质量
指标不变。这里保留的是优化前基线，前后对比与最终选型见 `INDEX_BENCHMARK.md`。

## 数据与方法

- 设备：Apple M4，16 GB 内存
- 模型：`google/siglip2-base-patch16-224`
- 数据：COCO 2017 validation，共 5000 张图片
- 查询：每张图片的第一条人工描述，每个检查点一图一查询
- 导入：`POST /v1/import-jobs`，每个持久化任务 500 张
- 搜索：`POST /v1/search/text`，请求 `top_k=10`
- 相关项：描述所属的原始图片
- 结果过滤：使用本地图库当前的“保留最佳匹配 + 相对分差”产品策略

完整数据通过 `scripts/prepare_coco_validation.py` 下载和准备。图片、标注与隔离运行目录均由
`.gitignore` 排除；manifest 保存每张图片的原始来源和 COCO license id。

## 规模结果

| 指标 | 1000 图 | 5000 图 |
|---|---:|---:|
| 新导入图片 | 1000 | 4000 |
| 导入耗时 | 70.06 s | 384.66 s |
| 导入吞吐 | 14.27 张/s | 10.40 张/s |
| 导入失败 | 0 | 0 |
| 查询数 | 1000 | 5000 |
| Recall@1 | 65.80% | 45.56% |
| Recall@5 | 87.90% | 69.82% |
| Recall@10 | 92.00% | 77.82% |
| 空结果率 | 0% | 0% |
| 平均结果数 | 4.63 | 6.76 |
| 平均查询延迟 | 16.87 ms | 51.40 ms |
| P95 查询延迟 | 18.93 ms | 67.06 ms |
| P99 查询延迟 | 21.37 ms | 106.93 ms |

Recall 下降不等于系统退化。候选从 1000 增至 5000 后，同类场景和合理近邻显著增加；COCO
描述如“一个人在冲浪”本身也可能准确描述多张图片，但当前单相关项评测只把原始图片算作
正确。这组指标适合作为相同协议下的版本比较，不应解释成主观相关性的绝对上限。

## 资源与恢复

- 持续运行后的服务 RSS：约 615 MB
- 重启后、加载模型前 RSS：约 263 MB
- 重启后、加载模型后 RSS：约 355 MB
- SQLite 元数据与向量：约 22 MB
- 5000 张运行时原图副本与缩略图：约 1.1 GB
- 重启后恢复图片：5000/5000
- 重启后健康检查：4.49 ms
- 返回 5000 张元数据：6.42 ms
- 冷启动首次搜索：13.75 s
- 模型加载后的验证搜索：27.19 ms

重启后首先观察到 `model_loaded: false`，但索引已恢复 5000 张；首次文本搜索后变为
`model_loaded: true`，中间没有重新编码图片。这证明图片向量和任务状态均已持久化。

## 可复现命令

```bash
python scripts/prepare_coco_validation.py

MUSELENS_MODE=local \
MUSELENS_IMAGE_DIR=data/benchmarks/coco-live/library \
MUSELENS_STATE_DIR=data/benchmarks/coco-live/state \
MUSELENS_THUMBNAIL_DIR=data/benchmarks/coco-live/thumbnails \
uvicorn muselens.api:app --host 127.0.0.1 --port 8001 --no-access-log

python scripts/benchmark_live_library.py \
  --base-url http://127.0.0.1:8001 \
  --checkpoints 1000 5000
```

机器可读结果位于 `artifacts/evaluations/coco-val2017-live-api-v1.json`，其中包含有限数量的
失败样例，便于后续做索引优化前后的回归比较。

## 下一步决策

1. 已完成连续矩阵与可选 FAISS 精确索引对比，最终默认使用 NumPy。
2. 保留精确索引作为当前产品实现，不让本地运行强依赖额外服务。
3. 基于 COCO 类别增加元数据过滤，并测试“语义搜索 + 条件过滤”的组合查询。
4. 图库达到至少 5 万张后，再重新评估 ANN 或独立向量服务。
