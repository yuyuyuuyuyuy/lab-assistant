# -*- coding: utf-8 -*-
"""chat.db（SQLite）：会话、消息、知识库注册表。"""
import json
import sqlite3
import time
import uuid

import config


def _connect():
    db = sqlite3.connect(config.CHAT_DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = _connect()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations(
            id TEXT PRIMARY KEY, kb_id TEXT, title TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT,
            role TEXT, content TEXT, citations TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS kbs(
            id TEXT PRIMARY KEY, name TEXT, builtin INTEGER DEFAULT 0, created_at TEXT);
        """
    )
    db.commit()
    db.close()


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ---------- 会话 ----------

def new_conversation(kb_id, title=None):
    conv_id = uuid.uuid4().hex[:12]
    db = _connect()
    db.execute(
        "INSERT INTO conversations(id, kb_id, title, created_at) VALUES (?,?,?,?)",
        (conv_id, kb_id, title or "新对话", now()),
    )
    db.commit()
    db.close()
    return conv_id


def list_conversations(kb_id=None):
    db = _connect()
    if kb_id:
        rows = db.execute(
            "SELECT * FROM conversations WHERE kb_id=? ORDER BY created_at DESC", (kb_id,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM conversations ORDER BY created_at DESC").fetchall()
    db.close()
    return [dict(r) for r in rows]


def set_conversation_title(conv_id, title):
    db = _connect()
    db.execute("UPDATE conversations SET title=? WHERE id=?", (title, conv_id))
    db.commit()
    db.close()


def delete_conversation(conv_id):
    db = _connect()
    db.execute("DELETE FROM messages WHERE conv_id=?", (conv_id,))
    db.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    db.commit()
    db.close()


def add_message(conv_id, role, content, citations=None):
    db = _connect()
    db.execute(
        "INSERT INTO messages(conv_id, role, content, citations, created_at) VALUES (?,?,?,?,?)",
        (conv_id, role, content, json.dumps(citations or [], ensure_ascii=False), now()),
    )
    db.commit()
    db.close()


def get_messages(conv_id):
    db = _connect()
    rows = db.execute(
        "SELECT * FROM messages WHERE conv_id=? ORDER BY id", (conv_id,)
    ).fetchall()
    db.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["citations"] = json.loads(d["citations"] or "[]")
        except Exception:
            d["citations"] = []
        out.append(d)
    return out


def recent_history(conv_id, max_turns=6):
    """最近若干轮问答（用于多轮上下文），返回 [{"q":..., "a":...}]。"""
    msgs = get_messages(conv_id)
    pairs = []
    for m in msgs:
        if m["role"] == "user":
            pairs.append({"q": m["content"], "a": ""})
        elif pairs and m["role"] == "assistant":
            pairs[-1]["a"] = m["content"]
    return pairs[-max_turns:]


# ---------- 知识库注册表 ----------

def ensure_builtin_kb():
    db = _connect()
    row = db.execute("SELECT id FROM kbs WHERE builtin=1").fetchone()
    if row is None:
        db.execute(
            "INSERT INTO kbs(id, name, builtin, created_at) VALUES (?,?,1,?)",
            (config.BUILTIN_KB_ID, config.BUILTIN_KB_NAME, now()),
        )
        db.commit()
    db.close()


def add_kb(kb_id, name, builtin=0):
    db = _connect()
    db.execute(
        "INSERT INTO kbs(id, name, builtin, created_at) VALUES (?,?,?,?)",
        (kb_id, name, builtin, now()),
    )
    db.commit()
    db.close()


def list_kbs():
    db = _connect()
    rows = db.execute("SELECT * FROM kbs ORDER BY builtin DESC, created_at").fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_kb(kb_id):
    db = _connect()
    row = db.execute("SELECT * FROM kbs WHERE id=?", (kb_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def rename_kb(kb_id, name):
    db = _connect()
    db.execute("UPDATE kbs SET name=? WHERE id=?", (name, kb_id))
    db.commit()
    db.close()


def delete_kb_row(kb_id):
    db = _connect()
    db.execute("DELETE FROM kbs WHERE id=?", (kb_id,))
    db.commit()
    db.close()
