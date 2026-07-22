# 精确向量索引选型与低内存演进

## 结论

MuseLens 第一阶段从“Python 字典逐向量点积”升级为“连续 NumPy 矩阵乘法”。在 Apple M4
的 5000 个 SigLIP2 向量上，纯索引平均延迟降低约 10.87 倍；真实 HTTP 平均延迟从
51.40 ms 降至 18.31 ms，同时 Top-10 排名与 Recall 指标完全不变。

FAISS `IndexFlatIP` 的纯索引速度比 NumPy 矩阵再快约 1.5 倍，但 pip 安装的 FAISS 与
PyTorch macOS ARM64 wheel 各自携带一份 OpenMP 运行时，同进程搜索会被底层直接终止。
因此本项目没有通过 `KMP_DUPLICATE_LIB_OK` 绕过安全检查：FAISS 保留为隔离 benchmark
和其他兼容平台的可选后端。

第二阶段默认后端升级为磁盘映射精确索引。它保持相同的精确余弦结果，但不再把完整向量字典
和连续矩阵同时常驻进程内存。

## 10 万图内存对比

在独立进程中依次插入 100,000 个 768 维 float32 向量并执行首次 Top-10 查询。RSS 通过
macOS `ps` 读取，两个后端使用相同协议和随机种子。

| 后端 | 构建后 RSS | 首次搜索后 RSS | 首次搜索 | 可删除缓存文件 |
|---|---:|---:|---:|---:|
| NumPy 连续矩阵 | 377.0 MB | 679.8 MB | 63.9 ms | 0 MB |
| mmap 分块精确索引 | 74.4 MB | 74.7 MB | 36.0 ms | 293.0 MB |

mmap 将首次搜索后的进程 RSS 降低约 89%。293 MB 文件是从 SQLite 流式恢复的派生缓存，
服务正常停止时自动删除；内存映射页面也可由操作系统在内存紧张时回收。本实验可通过
`scripts/benchmark_index_memory.py` 复现。

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

`MUSELENS_INDEX_BACKEND` 支持默认的 `mmap`，以及 `numpy` 和 `faiss`。FAISS 是可选依赖：

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
- `artifacts/evaluations/vector-index-memory-100k-v1.json`

## 下一步

当前 mmap 后端已经解决消费级设备上的常驻内存问题，并保持精确排名。图库扩展到至少 50 万张
后，再用相同协议评估量化、HNSW、IVF 或 Qdrant，避免过早引入近似召回损失和额外服务。
