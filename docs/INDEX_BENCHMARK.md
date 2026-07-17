# 5000 图精确向量索引选型

## 结论

MuseLens 默认索引从“Python 字典逐向量点积”升级为“连续 NumPy 矩阵乘法”。在 Apple M4
的 5000 个 SigLIP2 向量上，纯索引平均延迟降低约 10.87 倍；真实 HTTP 平均延迟从
51.40 ms 降至 18.31 ms，同时 Top-10 排名与 Recall 指标完全不变。

FAISS `IndexFlatIP` 的纯索引速度比 NumPy 矩阵再快约 1.5 倍，但 pip 安装的 FAISS 与
PyTorch macOS ARM64 wheel 各自携带一份 OpenMP 运行时，同进程搜索会被底层直接终止。
因此本项目没有通过 `KMP_DUPLICATE_LIB_OK` 绕过安全检查：M4 应用默认使用 NumPy；FAISS
保留为隔离 benchmark 和其他兼容平台的可选后端。

## 为什么比较精确索引

当前图库只有 5000 张。FAISS 官方选型指南指出，查询次数较少或必须保证精确结果时应先用
Flat 索引；`IndexFlatIP` 对预先 L2 归一化的向量等价于余弦相似度。此规模直接引入 HNSW、
IVF 或 Qdrant 会混入近似召回和运维成本，尚无数据证明必要。

- [FAISS index 选择指南](https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index)
- [FAISS 余弦相似度说明](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances)
- [FAISS 索引类型](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes)

## 纯索引公平对比

实验使用同一个 SQLite 中的 5000 个 768 维 float32 向量，以前 1000 个图片向量作为查询，
每次取 Top-10，并连续执行 5 轮、共计 5000 次计时查询。模型编码、HTTP 和 JSON 序列化
不计入这一组数字。

| 后端 | 平均延迟 | P95 | P99 | QPS | 相对旧实现 |
|---|---:|---:|---:|---:|---:|
| Python 字典循环 | 3.942 ms | 6.539 ms | 7.402 ms | 254 | 1.00× |
| NumPy 连续矩阵 | 0.363 ms | 0.433 ms | 0.714 ms | 2756 | 10.87× |
| FAISS IndexFlatIP | 0.237 ms | 0.280 ms | 0.317 ms | 4213 | 16.61× |

三个实现的 1000 条 Top-10 排名一致率均为 100%，最大公共分数差为
`2.98e-7`，属于 float32 数值误差。NumPy 和 FAISS 首次构建连续索引均约 3.1 ms。

## 真实 API 前后对比

| 指标 | 旧字典循环 | NumPy 矩阵 | 变化 |
|---|---:|---:|---:|
| 图片数 | 5000 | 5000 | 相同 |
| 查询数 | 5000 | 5000 | 相同 |
| Recall@1 | 45.56% | 45.56% | 不变 |
| Recall@5 | 69.82% | 69.82% | 不变 |
| Recall@10 | 77.82% | 77.82% | 不变 |
| 空结果率 | 0% | 0% | 不变 |
| 平均热查询延迟 | 51.40 ms | 18.31 ms | -64.4% |
| P95 | 67.06 ms | 25.58 ms | -61.9% |
| P99 | 106.93 ms | 32.71 ms | -69.4% |

HTTP 指标包含 SigLIP2 文本编码、索引搜索、结果过滤和 JSON 往返。它比纯索引提升小，说明
优化后主要耗时已转移到文本编码和请求处理，这也是下一阶段性能工作的依据。

## 实现方式

`VectorIndex` 仍保留字典作为增量写入的真实来源。新增图片只把连续矩阵标记为失效；下一次
搜索统一 `np.stack` 成连续 float32 矩阵，之后所有查询使用一次矩阵向量乘法。相同分数使用
稳定排序，确保与旧实现的插入顺序一致。

`MUSELENS_INDEX_BACKEND` 支持 `numpy` 和 `faiss`。FAISS 是可选依赖：

```bash
python -m pip install -e '.[faiss]'
```

macOS 上若同一进程已加载 PyTorch，MuseLens 会明确拒绝初始化 pip FAISS 后端，避免进程在
搜索时无提示崩溃。可通过不导入 PyTorch 的隔离脚本复现实验：

```bash
python scripts/benchmark_vector_indexes.py
```

机器可读结果：

- `artifacts/evaluations/vector-index-5k-v1.json`
- `artifacts/evaluations/coco-val2017-live-api-numpy-matrix-v1.json`

## 下一步

在 5000 图规模，NumPy 已将索引 P95 压到 0.5 ms 以下，暂无引入近似索引或独立向量服务的
收益证据。后续先做元数据组合过滤和重复图片检测；图库扩展到至少 5 万张后，再用相同协议
评估 HNSW、IVF 或 Qdrant。
