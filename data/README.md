# 数据目录

用户导入的图片副本默认保存在 `~/Pictures/MuseLensLibrary/`。程序不会移动、覆盖或删除原始照片；导入时使用随机 ID 生成新文件名，避免与其他文件冲突。

图片元数据与 CLIP 向量保存在 `~/Pictures/MuseLensLibrary/.muselens/index.sqlite3`。程序启动时从该数据库恢复索引；重复图片通过文件 SHA-256 识别，不会再次复制。

评测阶段会选用带文本描述的公开图文数据集子集，但不会将数据本体提交到仓库。
