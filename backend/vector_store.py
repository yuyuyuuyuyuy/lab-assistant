# -*- coding: utf-8 -*-
"""向量存储：sqlite-vec 实现（一个 SQLite 文件装下全部数据）。

设计要点：
- chunks 表存文本与元数据，vec 虚表存向量，两边用同一个整数 id 对应；
- 向量入库前归一化，检索分数 = 1 - 距离²/2（即余弦相似度，范围 0~1）；
- 接口只有 add / search / copy_file / 文件哈希表 / count 几个方法，
  将来若打包遇阻，可整体换成 numpy 暴力检索实现而不影响其他代码。
"""
import json
import os
import sqlite3

import numpy as np
import sqlite_vec

DIM = 1024  # text-embedding-v4 的向量维度


def normalize(v):
    n = float(np.linalg.norm(v))
    return (np.asarray(v, dtype=np.float32) / n) if n > 0 else np.asarray(v, dtype=np.float32)


def _pack(vec):
    """向量 → float32 字节流（sqlite-vec 的 BLOB 格式）"""
    return np.asarray(vec, dtype=np.float32).tobytes()


class VectorStore:
    def __init__(self, path):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS chunks ("
            "id INTEGER PRIMARY KEY, file TEXT, text TEXT, meta TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS files ("
            "path TEXT PRIMARY KEY, md5 TEXT, chunk_count INTEGER)"
        )
        self.db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec USING vec0(embedding float[{DIM}])"
        )
        self.db.commit()

    # ---- 写入 ----
    def add(self, items):
        """items: [(cid, file_rel, text, vector, meta_dict)]"""
        for cid, file_rel, text, vec, meta in items:
            self.db.execute(
                "INSERT INTO chunks(id, file, text, meta) VALUES (?,?,?,?)",
                (cid, file_rel, text, json.dumps(meta, ensure_ascii=False)),
            )
            self.db.execute(
                "INSERT INTO vec(rowid, embedding) VALUES (?,?)",
                (cid, _pack(normalize(vec))),
            )
        self.db.commit()

    def set_file(self, file_rel, md5, chunk_count):
        self.db.execute(
            "INSERT OR REPLACE INTO files(path, md5, chunk_count) VALUES (?,?,?)",
            (file_rel, md5, chunk_count),
        )
        self.db.commit()

    def get_files(self):
        """返回 {相对路径: (md5, chunk_count)}，用于增量判断。"""
        rows = self.db.execute("SELECT path, md5, chunk_count FROM files").fetchall()
        return {r[0]: (r[1], r[2]) for r in rows}

    def copy_file(self, other, file_rel):
        """从另一个（旧）库里把某个未变化文件的全部块搬过来，免重新向量化。

        id 在新库里**重新分配**（不复用旧 id）：同一轮重建里新旧文件混合时，
        保留旧 id 会与新文件的 id 区间重叠，导致 UNIQUE constraint failed。
        """
        rows = other.db.execute(
            "SELECT id, file, text, meta FROM chunks WHERE file=?", (file_rel,)
        ).fetchall()
        emb_by_id = {
            rowid: emb
            for rowid, emb in other.db.execute(
                "SELECT vec.rowid, vec.embedding FROM vec "
                "WHERE vec.rowid IN (SELECT id FROM chunks WHERE file=?)",
                (file_rel,),
            ).fetchall()
        }
        next_id = self.max_id()
        for r in rows:
            next_id += 1
            self.db.execute(
                "INSERT INTO chunks(id, file, text, meta) VALUES (?,?,?,?)",
                (next_id, r[1], r[2], r[3]),
            )
            self.db.execute(
                "INSERT INTO vec(rowid, embedding) VALUES (?,?)",
                (next_id, emb_by_id[r[0]]),
            )
        self.db.commit()

    # ---- 检索 ----
    def search(self, vec, top_k=6):
        """余弦相似度检索，返回 [{id, file, text, meta, score}]，按分数降序。

        注：sqlite-vec 的 KNN 查询在 JOIN 场景下必须用 k = ? 显式约束。
        """
        rows = self.db.execute(
            "SELECT chunks.id, chunks.file, chunks.text, chunks.meta, vec.distance "
            "FROM vec JOIN chunks ON chunks.id = vec.rowid "
            "WHERE vec.embedding MATCH ? AND k = ? "
            "ORDER BY vec.distance",
            (_pack(normalize(vec)), int(top_k)),
        ).fetchall()
        out = []
        for cid, file_rel, text, meta, dist in rows:
            score = max(0.0, min(1.0, 1.0 - (dist * dist) / 2.0))  # 余弦相似度
            out.append(
                {
                    "id": cid,
                    "file": file_rel,
                    "text": text,
                    "meta": json.loads(meta),
                    "score": round(score, 4),
                }
            )
        out.sort(key=lambda x: -x["score"])
        return out[:top_k]

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def max_id(self):
        row = self.db.execute("SELECT MAX(id) FROM chunks").fetchone()
        return row[0] if row and row[0] else 0

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def atomic_replace(tmp_path, final_path):
    """用临时文件替换正式索引文件（Windows 下 os.replace 原子性足够）。"""
    if os.path.exists(final_path):
        os.remove(final_path)
    os.replace(tmp_path, final_path)
