# 中英文检索模型对比

## 结论

MuseLens 默认视觉语言模型由 `openai/clip-vit-base-patch32` 切换为
`google/siglip2-base-patch16-224`。在本项目的 100 图、30 组中英成对查询上，
SigLIP2 将中文 Recall@1 从 3.3% 提升到 96.7%，同时没有牺牲英文检索。

## 可复现实验

- 候选集：Flickr8k 测试集固定抽样 100 张图片。
- 查询集：30 个不同目标，每个目标各一条英文和中文自然语言查询，共 60 条。
- 指标：文本到图片 Recall@K、MRR、平均/中位排名。
- 硬件：Apple M4、16 GB 统一内存，PyTorch MPS。
- 查询集：`data/evaluation/sample-v1/bilingual_queries.jsonl`。
- 原始结果：`artifacts/evaluations/*-bilingual-v1.json`。

| 模型 | 英文 R@1 | 中文 R@1 | 中文 R@5 | 总体 MRR | 单图编码 |
| --- | ---: | ---: | ---: | ---: | ---: |
| CLIP ViT-B/32 | 93.3% | 3.3% | 6.7% | 0.526 | 11.7 ms |
| SigLIP2 Base P16 224 | 100% | 96.7% | 100% | 0.992 | 28.7 ms |

候选集和查询集都较小，而且中文查询由项目人工整理，因此结果用于工程选型，
不应被表述为通用学术基准。后续应在更大的真实个人图库和用户查询日志上复验。

运行方式：

```bash
python scripts/evaluate_retrieval.py \
  --queries data/evaluation/sample-v1/bilingual_queries.jsonl \
  --model-id google/siglip2-base-patch16-224 \
  --batch-size 8 \
  --output artifacts/evaluations/siglip2-base-p16-224-bilingual-v1.json
```

## 无关查询拒答再校准

不同模型的余弦相似度分布不可直接共用阈值。旧 CLIP 阈值 `0.22` 在 SigLIP2 上
会误拒绝约 98% 的正常查询。重新扩大搜索区间后，校准阈值为 `0.12`；留出集上：

- 正常查询接受率：96.4%；
- Recall@5（拒答后）：96.0%；
- 无关查询拒绝率：100%；
- 平衡分数：0.980。

原始结果保存在
`artifacts/evaluations/siglip2-base-p16-224-rejection-v1.json`。

## 安全迁移

数据库恢复索引时只读取与当前 `model_id` 一致的向量，避免不同维度或不同向量空间
被混用。`scripts/rebuild_embeddings.py` 会先完成全部图片编码，再用同一个 SQLite 事务
替换向量；任何原图都不会被删除。

```bash
python scripts/rebuild_embeddings.py \
  --model-id google/siglip2-base-patch16-224 \
  --batch-size 8
```

## 模型资料

- SigLIP2 模型卡：https://huggingface.co/google/siglip2-base-patch16-224
- SigLIP2 论文：https://arxiv.org/abs/2502.14786
- Chinese-CLIP（备选）模型卡：https://huggingface.co/OFA-Sys/chinese-clip-vit-base-patch16

Chinese-CLIP 针对中文训练，但本项目需要一个同时覆盖中文和英文的统一向量空间；
SigLIP2 在本机实测已满足准确率和速度要求，因此本轮没有继续引入第二套线上索引。
