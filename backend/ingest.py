# -*- coding: utf-8 -*-
"""索引构建：扫描文档目录 → 解析分块 → 向量化 → 入库。

增量策略：文件 md5 未变化时，直接从旧索引原样复制块（免重新向量化，省钱省时）；
任何文件变化（新增/修改/删除）都会反映到新索引，最后原子替换。
"""
import hashlib
import os

from . import parser, vector_store
from .embeddings import embed, make_client


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_docs(docs_dir):
    """递归扫描支持的文档，返回 [(绝对路径, 相对路径)]。"""
    found = []
    if not os.path.isdir(docs_dir):
        return found
    for root, _dirs, files in os.walk(docs_dir):
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext in parser.SUPPORTED_EXTS:
                found.append((os.path.join(root, name), os.path.relpath(os.path.join(root, name), docs_dir)))
    return found


def _meta_from_rel(rel, kb_name):
    parts = rel.split(os.sep)
    category = parts[0] if len(parts) > 1 else ""
    return {"category": category, "source": os.path.basename(rel), "kb": kb_name}


def build_index(index_path, docs_dir, kb_name, settings, progress_cb=None):
    """重建索引（增量、原子替换）。progress_cb(pct, message)；返回统计 dict。"""
    progress_cb = progress_cb or (lambda pct, msg: None)
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    tmp_path = index_path + ".tmp"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    found = scan_docs(docs_dir)
    if not found:
        # 无文档：也建一个空索引，保证后续打开正常
        empty = vector_store.VectorStore(tmp_path)
        empty.close()
        vector_store.atomic_replace(tmp_path, index_path)
        progress_cb(100, "完成（暂无文档）")
        return {"files": 0, "chunks": 0, "new": 0, "copied": 0, "errors": []}

    old = None
    old_files = {}
    if os.path.exists(index_path):
        old = vector_store.VectorStore(index_path)
        old_files = old.get_files()

    client = make_client(settings)
    new = vector_store.VectorStore(tmp_path)
    stats = {"files": len(found), "new": 0, "copied": 0, "chunks": 0, "errors": []}
    n = len(found)

    try:
        for i, (abs_path, rel) in enumerate(found):
            pct = 5 + int(90 * i / n)
            progress_cb(pct, f"正在处理 {rel}")
            md5 = _md5(abs_path)
            prev = old_files.get(rel)
            try:
                if prev and prev[0] == md5 and prev[1] > 0:
                    # 未变化：整文件复制，免重新向量化
                    new.copy_file(old, rel)
                    new.set_file(rel, md5, prev[1])
                    stats["copied"] += 1
                    stats["chunks"] += prev[1]
                else:
                    chunks = parser.parse_file(abs_path)
                    if not chunks:
                        raise ValueError("未解析出任何文字内容（可能是图片型文档）")
                    vectors = embed(client, chunks, settings["embed_model"])
                    meta_base = _meta_from_rel(rel, kb_name)
                    items = [
                        (new.max_id() + 1 + k, rel, text, vec, dict(meta_base, chunk=k))
                        for k, (text, vec) in enumerate(zip(chunks, vectors))
                    ]
                    new.add(items)
                    new.set_file(rel, md5, len(chunks))
                    stats["new"] += 1
                    stats["chunks"] += len(chunks)
            except Exception as e:
                stats["errors"].append(f"{rel}: {e}")
                progress_cb(pct, f"{rel} 处理失败，已跳过")

        if stats["chunks"] == 0 and stats["errors"]:
            raise RuntimeError("全部文件处理失败：" + "；".join(stats["errors"][:3]))
    finally:
        if old is not None:
            old.close()
        new.close()

    vector_store.atomic_replace(tmp_path, index_path)
    progress_cb(100, "索引完成")
    return stats
