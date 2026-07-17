# GitHub 图文检索项目调研与训练决策

调研日期：2026-07-16。Star 数量只用于判断社区影响力，会随时间变化。

| 项目 | Star 快照 | 借鉴内容 | 不直接照搬的部分 |
| --- | ---: | --- | --- |
| [facebookresearch/faiss](https://github.com/facebookresearch/faiss) | 40.5k | 精确/近似索引分层、速度/召回/内存取舍、独立 benchmark | M4 没有 CUDA，不采用 GPU Faiss |
| [openai/CLIP](https://github.com/openai/CLIP) | 33.8k | 归一化图文特征、线性探测、零样本基线 | 官方仓库不提供完整预训练流水线 |
| [mlfoundations/open_clip](https://github.com/mlfoundations/open_clip) | 14.0k | train/val 独立、检查点、配置化训练、WebDataset、系统评测 | 亿级数据和多 GPU/FSDP 不适合本机 |
| [jina-ai/clip-as-service](https://github.com/jina-ai/clip-as-service) | 12.8k | 编码服务与业务层解耦、批处理、可替换模型 | 不引入分布式服务复杂度 |
| [rom1504/clip-retrieval](https://github.com/rom1504/clip-retrieval) | 2.8k | 离线特征计算、索引构建与检索服务分阶段 | 当前个人图库不需要十亿级数据管线 |
| [LAION-AI/CLIP_benchmark](https://github.com/LAION-AI/CLIP_benchmark) | 0.8k | 多模型/多数据集统一输出 JSON、跳过已有结果 | 先实现项目相关的中英文检索指标 |
| [gaopengcuhk/Tip-Adapter](https://github.com/gaopengcuhk/Tip-Adapter) | 0.7k | 缓存冻结特征、轻量适配、训练前后对比 | 原项目面向少样本分类，不直接复用分类逻辑 |

## 对 MuseLens 的具体影响

1. 数据、冻结特征、训练产物和最终测试结果分目录保存。
2. 训练/验证按图片划分，同一图片的五条描述不能跨 split，避免数据泄漏。
3. SigLIP2 主干冻结并预计算特征，训练两个小型残差 Adapter。
4. 使用图到文和文到图的对称 InfoNCE；每个 batch 中图片 ID 唯一，避免同图描述互为假负样本。
5. 每个 epoch 保存训练损失和验证 Recall@K/MRR，只保留验证 MRR 最佳检查点。
6. 最终结论必须在从未参与训练与调参的 Flickr8k `test` split 上产生。
7. 上线前同时检查英文、中文和拒答指标；若中文退化，则不替换零样本模型。

## M4 16 GB 训练边界

SigLIP2 Base 权重约 1.5 GB，但完整训练还需要梯度、优化器状态和中间激活，收益与
单机成本不匹配。本阶段冻结主干，只训练两个瓶颈残差网络和一个温度参数；基础特征
缓存后，后续超参数实验不再反复运行大模型。

这不是把“无法全量训练”包装成优点：项目会明确报告训练参数量、数据规模、耗时、
训练前后指标和失败案例，并将完整微调列为拥有更大 GPU 资源后的扩展实验。
