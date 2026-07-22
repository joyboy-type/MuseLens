# 中英文检索精排与无结果判定

## 结论

MuseLens 不再用 `dog` 单词作为部署效果的代表。当前固定演示图库使用 94 条可复现查询契约，
覆盖 21 类图库内内容的 84 条中英文短词/描述句，以及 10 条图库中不存在内容的查询。

2026-07-22 对公开轻量服务重新实测：Top-1 72.62%，Top-5 95.24%；英语 Top-5 97.62%，
中文 Top-5 92.86%。四个 Top-5 失败集中在小目标时钟和一句复杂的大象描述。轻量模式对
10 条图库外查询的拒绝率仍为 0%，说明仅靠 SigLIP2 最高余弦分数无法可靠区分“较弱正例”
与“图库不存在”：正例最低最高分为 0.034，负例最高分范围为 0.015～0.077，区间明显重叠。
因此线上轻量模式不伪造绝对置信度，只展示相对相关性；严格拒答仍属于可选精排模式。

轻量 SigLIP2 能完成召回，但会把所有图库外查询强行匹配到“最近邻”。可选高精度模式采用
两阶段检索：SigLIP2 快速召回最多 5 张图片，再由 Qwen3-VL-Reranker-2B 对原始查询与
每张候选图片进行交叉注意力精排，并用相关性概率决定是否返回。

| 方案 | 图库内 Top-1 | 图库内 Top-5 | 图库外拒绝率 |
|---|---:|---:|---:|
| SigLIP2 原始查询 | 75.00% | 97.73% | 0.00% |
| SigLIP2 照片提示召回 | 70.45% | 100.00% | 0.00% |
| Qwen3-VL 精排，不设拒绝阈值 | 95.45% | 100.00% | 0.00% |
| Qwen3-VL 精排，阈值 0.40 | 93.18% | 93.18% | 100.00% |

选择 0.40 是因为它在本评测中拒绝 10/10 图库外查询，同时保留并正确命中 41/44 图库内
查询。0.35 阈值仍会把 `train/火车` 错配到车辆或飞机图片，图库内命中率却没有提高，
因此不是更好的工作点。

## 数据与协议

- 图库：24 张 COCO 2017 验证图，均在 `demo_assets/manifest.json` 保存原作者、来源和
  CC BY 2.0 署名。
- 正例：84 条，英语 42 条、中文 42 条，覆盖狗、猫、鸟、象、汽车、公交车、飞机、船、
  马、披萨、蛋糕、球、滑雪板、笔记本电脑、手机、书、时钟、自行车、摩托车、长颈鹿、羊。
- 负例：10 条，`train/火车`、`zebra/斑马`、`surfboard/冲浪板`、`donut/甜甜圈`、
  `flower/花朵`；这些类别在固定图库中不存在。
- 召回：发送 `A photo of {query}.` 到真实 `/v1/search/text` API，最多取 5 张候选。
- 精排：用原始查询和候选原图调用 Qwen3-VL-Reranker-2B，而不是使用文件名或人工标签。
- 计分：正例检查 COCO 类别是否出现在 Top-1/Top-5；负例检查阈值后是否为空。

查询集位于 `demo_assets/query_suite.json`，机器可读结果位于：

- `artifacts/evaluations/demo-bilingual-search-v1.json`
- `artifacts/evaluations/demo-bilingual-search-a-photo.json`
- `artifacts/evaluations/demo-qwen-reranker-v1.json`
- `artifacts/evaluations/demo-bilingual-search-v2-full.json`

## 失败案例与边界

阈值 0.40 下的 3 个失败查询是 `手机`、`clock`、`时钟`。图库中的手机只占镜中人物手部
很小区域；时钟位于商店背景顶部，尺寸很小且部分被裁切。精排模型对这些图给出的最高分
分别为 0.344、0.281、0.330，因此选择不确定返回，而不是给出错误的高置信结果。

这项实验不证明“任意关键词 100% 准确”。开放词汇检索仍受图库是否包含目标、目标尺寸、
遮挡、语言表达和模型训练分布影响。产品承诺应是：有内容时尽可能召回，没有足够证据时
明确返回空结果；评测集应继续扩展，而不是为某一个关键词写特判。

## 复现

轻量 API 合同：

```bash
python scripts/evaluate_demo_search.py http://127.0.0.1:7860 \
  --output artifacts/evaluations/demo-bilingual-search-v1.json
```

本地高精度评测：

```bash
python -m pip install -e '.[dev,precision]'
python scripts/evaluate_precision_reranker.py http://127.0.0.1:7860
```

开启真实 API 高精度模式：

```bash
MUSELENS_RERANKER_MODEL=Qwen/Qwen3-VL-Reranker-2B \
MUSELENS_RERANKER_MIN_SCORE=0.40 \
uvicorn muselens.api:app
```

Qwen3-VL-Reranker-2B 权重约 4.27 GB，首次下载后缓存在本机。免费 2 核 CPU 公开演示仍使用
SigLIP2 轻量模式；高精度模式用于 M4 本地演示或后续具备足够内存/算力的部署环境。
`GET /health` 的 `reranker_enabled` 和 `reranker_loaded` 可分别确认配置是否启用、模型是否已经
完成首次延迟加载。

## 参考实现

- QwenLM/Qwen3-VL-Embedding：两阶段 embedding + reranking 架构、yes/no 相关性评分和
  多模态消息格式。
- Sentence Transformers CrossEncoder：可选精排接口设计。当前 Transformers 5 环境下，
  MuseLens 直接封装 Qwen 官方消息流程，并修复 `mm_token_type_ids` 列表到张量的兼容问题。
