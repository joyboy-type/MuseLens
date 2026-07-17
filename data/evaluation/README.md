# Evaluation data

MuseLens 的首个检索评测样本来自 Hugging Face 数据集 `intro/flickr8k` 的 `test` split。

- 上游数据集：Flickr8k Captions With Splits
- 上游地址：https://huggingface.co/datasets/intro/flickr8k
- 数据卡标注许可：CC0
- 完整数据规模：8,000 张图片
- 本地样本版本：`sample-v1`
- 采样规则：按测试集元数据文件名排序后取前 N 张，默认 N=100
- 每张图片保留5条人工描述，用于文本到图片检索评测

本地图片和生成的 manifest 被 `.gitignore` 排除，不上传 GitHub。重新生成：

```bash
python scripts/download_evaluation_sample.py --count 100
```
