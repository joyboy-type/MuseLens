# MuseLens 多模态图片检索

MuseLens 是一个本地优先的中英文多模态图片搜索系统。这个公开演示使用 24 张具有明确
CC BY 2.0 署名信息的固定图片，同时允许访客创建相互隔离、自动过期的临时图库。

## 公开演示能力

- 中文或英文自然语言搜图；
- 上传查询图片进行视觉相似搜索；
- 上传自己的临时图库并进行真实向量检索；
- FastAPI、React、SigLIP2 和持久化向量索引；
- 固定图库由服务端强制只读，临时图库默认 30 分钟后清除。

公开 CPU 实例使用轻量 SigLIP2 召回。本地 Apple M4 高精度版本可以继续启用
Qwen3-VL-Reranker-2B 精排和图库外内容拒绝。

源代码、训练记录、评测协议和机器可读结果：
https://github.com/joyboy-type/MuseLens

固定演示图片署名见 `demo_assets/ATTRIBUTIONS.md`。
