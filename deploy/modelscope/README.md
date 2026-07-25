---
tags:
  - multimodal
  - computer-vision
  - image-retrieval
  - semantic-search
  - chinese
---

# MuseLens 多模态图片检索

MuseLens 是一个本地优先的中英文多模态图片搜索系统。这个公开演示使用 24 张具有明确
CC BY 2.0 署名信息的固定图片，同时允许访客创建相互隔离、自动过期的临时图库。

[![MuseLens 中英文多模态检索演示](https://raw.githubusercontent.com/joyboy-type/MuseLens/main/docs/assets/launch/muselens-demo.gif)](https://sinbaby-muselens.ms.show)

## 公开演示能力

- 中文或英文自然语言搜图；
- 上传查询图片进行视觉相似搜索；
- 上传自己的临时图库并进行真实向量检索；
- FastAPI、React、SigLIP2 和持久化向量索引；
- 固定图库由服务端强制只读，临时图库默认 30 分钟后清除。

公开 CPU 实例使用轻量 SigLIP2 召回。本地 Apple M4 高精度版本可以继续启用
Qwen3-VL-Reranker-2B 精排和图库外内容拒绝。

## 可复现结果

- 线上固定图库 84 条中英文查询：Hit@5 **95.24%**；
- 500 图、2,500 张扰动查询：以图搜图 Recall@1 **99.36%**；
- 5,000 图精确索引：相对旧实现加速 **10.87 倍**，排名一致率 **100%**。

[GitHub 源码](https://github.com/joyboy-type/MuseLens) ·
[完整技术复盘](https://github.com/joyboy-type/MuseLens/blob/main/docs/PROJECT_STORY_CN.md) ·
[最终验收](https://github.com/joyboy-type/MuseLens/blob/main/docs/FINAL_ACCEPTANCE.md)

固定演示图片署名见 `demo_assets/ATTRIBUTIONS.md`。
