# MuseLens 中文发布文案

## 标准版

我开源了 MuseLens v0.1.1：一个本地优先的多模态图片检索与整理系统。

它不是只能搜索固定样例的页面。你可以上传自己的图片，再用中文、英文或另一张图片检索；
公开访客图库按会话隔离，支持主动清理，并在索引完成 30 分钟后自动过期。

项目使用 React、TypeScript、FastAPI、PyTorch、SigLIP2、SQLite 和 NumPy mmap，实现了
图片导入、SHA-256 去重、后台索引、重启恢复、自动标签、人工纠正、智能/自定义相册和
以图搜图。

部分可复现结果：

- 100 图、500 条英文查询：Recall@1 91.6%；
- 100 图、30 条中文查询：Recall@1 96.67%；
- 500 图、2,500 张扰动查询：以图搜图 Recall@1 99.36%；
- 5,000 图精确索引：纯索引加速 10.87 倍，Top-10 排名一致率 100%；
- 线上 24 图、84 条中英文查询：Hit@5 95.24%。

我也训练了轻量 Adapter，但独立测试没有超过冻结的 SigLIP2 基线，中文 Recall@1 反而下降
3.4 个百分点，因此没有为了展示“训练成功”而上线。训练代码、负结果和决策过程都保留在
仓库中。

在线体验：<https://sinbaby-muselens.ms.show>  
GitHub：<https://github.com/joyboy-type/MuseLens>

欢迎试用临时图库，也欢迎对检索效果、工程实现和评测协议提出建议。

#多模态检索 #图文检索 #PyTorch #FastAPI #React #开源项目

## 精简版

MuseLens v0.1.1 已开源：上传自己的图片，就能用中文、英文或另一张图片搜索。

这不是固定关键词 Demo。系统包含真实的上传、SigLIP2 编码、向量索引、会话隔离和数据清理
链路，并通过 GitHub Actions 在线验证。当前 84 条中英文演示查询 Hit@5 为 95.24%；
5,000 图精确索引相对旧实现加速 10.87 倍。

在线体验：<https://sinbaby-muselens.ms.show>  
源码：<https://github.com/joyboy-type/MuseLens>

#AI工程 #多模态 #图片搜索 #开源

## GitHub / ModelScope 简介版

本地优先的多模态图片搜索与智能整理系统：支持中英文文本搜图、以图搜图、会话隔离临时图库、
自动标签、去重、相册和低内存精确索引。React + TypeScript + FastAPI + PyTorch +
SigLIP2 + SQLite。

## 一句话版

MuseLens：一个真正允许用户上传自己的图片，并用中英文或另一张图片进行检索的本地优先
多模态搜索系统。

## 发布时的配图顺序

1. `docs/assets/launch/muselens-social-preview.png`：用作文章头图与社交分享封面。
2. `docs/assets/launch/muselens-demo.gif`：展示真实中英文检索过程。
3. `docs/images/muselens-home.png`：展示完整首页。
4. `docs/images/muselens-architecture.svg`：说明系统不是只有前端外壳。
5. `docs/images/acceptance/v0.1.1/dog-preview.png`：展示结果解释与预览。
6. `docs/images/acceptance/v0.1.1/mobile-filter.png`：展示移动端筛选。

## 发布说明

- 不要把余弦相似度称为准确率或置信概率。
- 不要写“百万级图库”或“生产级云相册”；当前完成了 5,000 图真实 API 与 10 万向量内存基准。
- 不要把 24 张固定演示图库的 Hit@5 外推成通用模型效果。
- 不要写 Adapter 提升了线上效果；训练完成但没有通过独立测试，因此未上线。
- 如果平台不支持 Markdown，可保留“精简版”正文与两个裸链接，并上传演示 GIF。
