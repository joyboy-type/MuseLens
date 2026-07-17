# SigLIP2 轻量适配训练结果

## 实验目标

验证在 Apple M4 16 GB 上，冻结 SigLIP2 主干并训练双塔残差 Adapter，能否提升
个人图片文本检索，同时保持中文能力。

## 数据与防泄漏设计

- Flickr8k `train`：5,000张图片、25,000条英文描述，用于训练。
- Flickr8k `dev`（逻辑 validation）：500张图片、2,500条描述，仅用于选配置和早停。
- Flickr8k `test` 固定样本：100张图片、500条英文描述，仅用于最终测试。
- 中文保持集：30组中英文成对查询，仅用于最终检查。
- split 按图片隔离；同一图片的五条描述不会跨集合。
- 训练/验证特征缓存包含 manifest SHA-256，数据变化后不会误用旧缓存。

## 训练方法

SigLIP2 图像塔和文本塔全部冻结。两个独立 Adapter 均使用
`768 → bottleneck → 768` 残差结构，输出重新做 L2 归一化。训练使用批内唯一图片和
双向 InfoNCE，避免同一图片的不同描述被当成假负样本。验证 MRR 连续5轮不提升即早停。

正式特征缓存耗时约360秒。特征缓存后，每组 Adapter 实验约3–5秒。

## 消融实验（官方 validation）

零训练 SigLIP2：R@1 78.56%，MRR 0.86108。

| bottleneck | 学习率 | 可训练参数 | 最佳 MRR | 结论 |
| ---: | ---: | ---: | ---: | --- |
| 32 | 5e-5 | 99,907 | 0.86184 | 小幅提升 |
| 64 | 1e-4 | 198,275 | 0.86235 | 第3轮后过拟合 |
| 64 | 5e-5 | 198,275 | **0.86327** | 唯一进入最终测试 |
| 128 | 5e-5 | 395,011 | 0.86300 | 容量增大无收益 |

训练损失会持续下降，但验证指标很快下降，说明不能用训练 loss 代替检索泛化指标。

## 锁定检查点的最终 test

| 指标 | 原始 SigLIP2 | Adapter | 变化 |
| --- | ---: | ---: | ---: |
| 英文 R@1 | 91.6% | 91.6% | 0 |
| 英文 MRR | 0.95071 | 0.95097 | +0.00026 |
| 中文 R@1 | 96.7% | 93.3% | **-3.4 pp** |
| 中文 R@5 | 100% | 100% | 0 |

## 工程决策

不将 Adapter 集成到在线检索。英文收益小到没有产品意义，同时中文 R@1 明显下降。
线上继续使用原始 SigLIP2；训练代码、最佳检查点和全部实验结果保留，作为可复现的
失败实验和后续多语言训练的基线。

下一轮若继续训练，必须引入与英文训练图片对应的中文描述或多语言图文数据，并把
中文验证指标加入模型选择目标，而不是只在训练完成后检查中文。

## 产物

- 训练脚本：`scripts/train_adapter.py`
- Adapter：`src/muselens/adapters.py`
- 最佳检查点：`artifacts/training/adapter-5k-b64-lr5e5-v1/best.pt`
- 正式训练记录：`artifacts/training/adapter-5k-*/training_result.json`
- 最终英文结果：`artifacts/evaluations/siglip2-adapter-5k-test-english-v1.json`
- 最终双语结果：`artifacts/evaluations/siglip2-adapter-5k-test-bilingual-v1.json`
- 机器可读决策：`artifacts/evaluations/adapter-training-decision-v1.json`
