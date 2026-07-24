# MuseLens v0.1.0 模型与评估卡

## 模型用途

默认模型是 `google/siglip2-base-patch16-224`，用于中英文文本—图片和图片—图片的向量召回，
以及复用图片向量的受控词表零样本标签。可选
`Qwen/Qwen3-VL-Reranker-2B` 只对少量候选进行精排和拒答；免费线上实例未启用。

适用：个人图库的开放词汇排序、相似图发现、小规模演示。  
不适用：人脸身份识别、敏感属性判断、安全关键决策、可靠内容审核、未经新评测的百万图
或高并发服务。

## 训练与选择

MuseLens 没有从头训练 SigLIP2。项目训练了冻结主干的双塔残差 Adapter：

- 数据划分：5,000 训练图、500 验证图、100 最终测试图，每图 5 条 caption；
- 选中配置：bottleneck 64、学习率 5e-5、可训练参数 198,275、最佳 epoch 5；
- 验证 MRR：0.86108 → 0.86327；
- 测试英文 R@1：91.6% → 91.6%；中文 R@1：96.67% → 93.33%；
- 决策：不部署。

这不是“训练失败”，而是独立测试证据不支持增加生产复杂度。

## 数据说明

| 数据/语料 | 用途 | 边界 |
| --- | --- | --- |
| Flickr8k 固定样本 | 英文基线、本地端到端、Adapter | 100 图候选集较简单，不能外推 |
| COCO 2017 validation | 规模、以图搜图、演示图库 | 不代表私人相册完整分布 |
| 24 张演示图 | 线上回归合同 | 小而受控，只验证部署与覆盖类 |
| 84 双语正例 + 10 图库外负例 | 轻量/精排比较 | 人工合同规模有限，协议版本需固定 |
| 合成 100k 向量 | 内存基准 | 只测索引资源，不测模型质量 |

演示图来源、作者、许可和 SHA-256 见 `demo_assets/manifest.json` 与
`demo_assets/ATTRIBUTIONS.md`。本文不声称训练数据覆盖所有语言、场景或人群切片。

## 主要评估

### 文本搜图

- 100 图 / Flickr8k 500 英文查询：R@1 91.6%，R@5 99.0%，R@10 99.2%；
- 同 100 图 / 各 30 条配对查询：英文 R@1 100%，中文 R@1 96.67%；
- 线上 24 图 / 84 双语查询：Hit@1 72.62%，Hit@5 95.24%；英文 Hit@5 97.62%，中文
  92.86%。

`Recall@K` 的相关项是查询对应原图；线上 `Hit@K` 的相关项是预期 COCO 类别。二者定义和
候选集不同，不应直接比较。

### 以图搜图

500 图图库，每图生成 center crop、低质量 JPEG、blur、dark、low resolution 五种扰动，
共 2,500 查询：R@1 99.36%，R@5 99.96%。最差排名 7；blur 与低分辨率相对更难。

### 精排与拒答

旧版 44 正例 + 10 负例合同中：

- Qwen3-VL 无阈值：正例 Top-1 95.45%，Top-5 100%，负例拒绝 0%；
- 阈值 0.40：正例命中 93.18%，负例拒绝 100%。

该阈值来自同一小型合同，不能视为全局通用。阈值下失败包括 `手机`、`clock`、`时钟`，
对应小目标、背景位置或裁切。线上轻量模式的 84 正例协议与此 44 正例精排协议不同。

## 评估质量与风险

- 所有关键结果均链接机器可读 JSON，而不是只保留截图；
- 训练、验证、测试用途分开，Adapter 最终决策看独立测试；
- 指标必须携带候选集、查询数、语言、相关性定义、运行环境和 artifact；
- 小图库会放大指标，合成向量不能证明实际检索质量；
- 线上合同是部署回归，不是通用 benchmark；
- 当前没有人口统计、公平性或私人相册长期分布评估；
- 开放词汇最近邻总会返回“最像”的内容，除非有经过评估的拒答层。

## 可复现证据索引

相对仓库根目录：

- `artifacts/evaluations/local-library-e2e-100-v1.json`
- `artifacts/evaluations/coco-val2017-live-api-v1.json`
- `artifacts/evaluations/image-retrieval-coco500-v1.json`
- `artifacts/evaluations/vector-index-5k-v1.json`
- `artifacts/evaluations/vector-index-memory-100k-v1.json`
- `artifacts/evaluations/modelscope-live-bilingual-v2.json`
- `artifacts/evaluations/modelscope-live-temporary-gallery-v2.json`
- `artifacts/evaluations/demo-qwen-reranker-v1.json`
- `artifacts/evaluations/adapter-training-decision-v1.json`

