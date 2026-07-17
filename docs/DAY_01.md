# Day 01：理解多模态检索的数据流

## 今天的目标

不是追求准确率，而是能画出并解释这一条链路：

```text
图片/文字 -> CLIP -> 向量归一化 -> 相似度计算 -> Top-k 图片
```

## 先运行

在终端中执行：

```bash
cd /Users/joyboy/Desktop/AI-Engineering-Portfolio/MuseLens
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
uvicorn muselens.api:app --reload
```

然后访问 <http://127.0.0.1:8000/docs>。

第一次导入图片时才会下载并加载 CLIP 模型；只运行健康检查和测试不会下载模型。

## 按顺序阅读

1. `src/muselens/device.py`：程序怎样选择 MPS。
2. `src/muselens/encoder.py`：文字和图片怎样生成向量。
3. `src/muselens/index.py`：怎样计算相似度并排序。
4. `src/muselens/api.py`：HTTP 请求怎样调用编码器和索引。
5. `tests/`：怎样自动验证关键行为。

## 必须理解的五个问题

1. CLIP 为什么能比较文字和图片？
2. 为什么计算余弦相似度前要归一化？
3. Top-k 检索与分类有什么根本区别？
4. 为什么模型采用延迟加载？
5. 内存暴力检索在数据量变大后会出现什么问题？

## 今日动手任务

- 手算向量 `[1, 0]` 与 `[0.9, 0.1]` 的余弦相似度。
- 阅读 `tests/test_index.py`，解释为什么红色向量排在蓝色向量前面。
- 打开 `/health` 和 `/v1/images`，解释两个接口职责为什么不同。
- 在 `docs/LEARNING_LOG.md` 中填写“CLIP”和“向量检索”。

## 完成标准

你可以不看代码，用自己的话讲清楚文字查询怎样找到相关图片。完成后进入图片持久化与首次真实 CLIP 检索。
