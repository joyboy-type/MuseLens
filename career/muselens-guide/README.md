# MuseLens v0.1.0 项目指南

> 面向长期维护、作品集展示和技术面试的事实型文档。基线版本：`v0.1.0`（2026-07-24）。

## 阅读路线

| 场景 | 先读 | 再读 |
| --- | --- | --- |
| 5 分钟了解项目 | [项目说明书](PROJECT_CASE_STUDY.md) | [模型与评估卡](MODEL_AND_EVALUATION_CARD.md) |
| 系统设计面试 | [系统设计](SYSTEM_DESIGN.md) | [面试备忘录](INTERVIEW_PLAYBOOK.md) |
| 更新指标或发布新版本 | [维护与证据规则](MAINTENANCE.md) | 对应机器可读 artifact |

## 为什么采用这组文档

优秀 AI 工程项目通常需要同时回答五类问题：为什么做、系统如何工作、模型适合做什么、证据
是否可比、作者能否解释失败与取舍。MuseLens 是完整应用而非单独发布的模型，因此不照搬一份
独立模型仓库的 Model Card，而采用：

1. **Case study / 项目说明书**：从用户问题、范围、结果和取舍讲完整故事；
2. **System design document**：描述边界、数据流、状态、性能、安全与扩展路径；
3. **Model + evaluation card**：记录模型用途、数据、协议、指标、失败和不适用场景；
4. **Interview playbook**：把事实转化为不同长度的口述和高频追问；
5. **Maintenance guide**：规定来源优先级、指标写法和版本更新检查表。

这种组合借鉴了 Hugging Face 对 Model Card 的要求（用途、限制、训练数据、实验参数和评估
结果）、Model Cards 论文倡导的透明报告，以及 ADR 的“背景—决策—后果”结构。Google 的
Production ML Systems 材料强调模型只是系统的一部分，因此本文档同样覆盖数据校验、服务、
测试、部署和监控，而不是只列模型分数。

## 一句话事实边界

MuseLens v0.1.0 是一个本地优先的多模态图片检索与整理系统：React/TypeScript 前端调用
FastAPI，SigLIP2 生成图文向量，SQLite 保存业务状态，默认 mmap 精确索引完成检索；线上
ModelScope 演示支持只读固定图库和会话隔离的临时图库。它已验证 5,000 图真实 API 和
100,000 个合成向量的内存基准，但没有证据支持“百万级生产系统”或“任意查询高准确率”。

## 参考方法

- [Hugging Face Model Cards](https://huggingface.co/docs/hub/en/model-cards)
- [Annotated Model Card](https://huggingface.co/docs/hub/en/model-card-annotated)
- [Model Cards for Model Reporting](https://arxiv.org/abs/1810.03993)
- [Google: Production ML systems](https://developers.google.com/machine-learning/crash-course/production-ml-systems)
- [Architecture Decision Record](https://github.com/architecture-decision-record/architecture-decision-record)

