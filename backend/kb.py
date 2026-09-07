# -*- coding: utf-8 -*-
"""知识库管理：注册表（chat.db）+ 磁盘布局 kbs/<id>/{docs/, index.sqlite}。

索引进度存在内存 INGEST_STATUS（单机单用户应用，够用）。
"""
import os
import shutil
import threading
import time
import uuid

import config
from . import ingest, store
from .vector_store import VectorStore

INGEST_STATUS = {}  # kb_id -> {running, pct, message, error, stats}


def ensure_data_dirs():
    os.makedirs(config.KBS_DIR, exist_ok=True)
    store.init_db()
    store.ensure_builtin_kb()


def kb_paths(kb_id):
    """内置库的文档目录在程序包内（只读），索引在用户数据目录；用户库两者都在数据目录。"""
    if kb_id == config.BUILTIN_KB_ID:
        return {
            "base": os.path.join(config.KBS_DIR, kb_id),
            "docs": config.BUILTIN_DOCS_DIR,
            "index": os.path.join(config.KBS_DIR, kb_id, "index.sqlite"),
        }
    base = os.path.join(config.KBS_DIR, kb_id)
    return {
        "base": base,
        "docs": os.path.join(base, "docs"),
        "index": os.path.join(base, "index.sqlite"),
    }


def create_kb(name):
    kb_id = uuid.uuid4().hex[:8]
    p = kb_paths(kb_id)
    os.makedirs(p["docs"], exist_ok=True)
    store.add_kb(kb_id, name, builtin=0)
    return kb_id


def delete_kb(kb_id):
    row = store.get_kb(kb_id)
    if row is None:
        return
    if row["builtin"]:
        raise ValueError("内置知识库不可删除")
    store.delete_kb_row(kb_id)
    shutil.rmtree(kb_paths(kb_id)["base"], ignore_errors=True)
    INGEST_STATUS.pop(kb_id, None)


def index_exists(kb_id):
    return os.path.exists(kb_paths(kb_id)["index"])


def open_store(kb_id):
    p = kb_paths(kb_id)
    if not os.path.exists(p["index"]):
        return None
    return VectorStore(p["index"])


def list_docs(kb_id):
    """列出知识库当前文档（相对路径 + 大小 + 修改时间）。"""
    docs_dir = kb_paths(kb_id)["docs"]
    out = []
    for abs_path, rel in ingest.scan_docs(docs_dir):
        st = os.stat(abs_path)
        out.append(
            {"rel": rel, "size": st.st_size, "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))}
        )
    return out


def import_files(kb_id, src_paths):
    """把用户选择的文件复制进知识库 docs 目录（同名覆盖），返回复制数量。"""
    docs_dir = kb_paths(kb_id)["docs"]
    copied = 0
    for src in src_paths:
        if not os.path.isfile(src):
            continue
        ext = os.path.splitext(src)[1].lower()
        if ext not in (".txt", ".pdf", ".docx"):
            continue
        dst = os.path.join(docs_dir, os.path.basename(src))
        shutil.copy2(src, dst)
        copied += 1
    return copied


def import_folder(kb_id, folder):
    """把文件夹里所有支持的文档复制进知识库（递归），返回复制数量。"""
    files = [os.path.join(root, name)
             for root, _dirs, names in os.walk(folder)
             for name in names
             if os.path.splitext(name)[1].lower() in (".txt", ".pdf", ".docx")]
    return import_files(kb_id, files)


def start_ingest(kb_id, settings):
    """后台线程重建索引（增量）。"""
    p = kb_paths(kb_id)
    os.makedirs(os.path.dirname(p["index"]), exist_ok=True)
    row = store.get_kb(kb_id)
    kb_name = row["name"] if row else kb_id

    def cb(pct, message):
        INGEST_STATUS[kb_id] = {
            "running": True, "pct": pct, "message": message,
            "error": None, "stats": None, "updated_at": time.time(),
        }

    def work():
        try:
            stats = ingest.build_index(p["index"], p["docs"], kb_name, settings, cb)
            INGEST_STATUS[kb_id] = {
                "running": False, "pct": 100, "message": "索引完成",
                "error": None, "stats": stats, "updated_at": time.time(),
            }
        except Exception as e:
            INGEST_STATUS[kb_id] = {
                "running": False, "pct": 0, "message": "索引失败",
                "error": str(e), "stats": None, "updated_at": time.time(),
            }

    INGEST_STATUS[kb_id] = {
        "running": True, "pct": 0, "message": "启动中",
        "error": None, "stats": None, "updated_at": time.time(),
    }
    threading.Thread(target=work, daemon=True).start()


def get_ingest_status(kb_id):
    return INGEST_STATUS.get(kb_id)
