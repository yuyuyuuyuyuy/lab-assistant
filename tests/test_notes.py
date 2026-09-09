# -*- coding: utf-8 -*-
"""P2 知识笔记验收：
- /api/notes/generate 生成结构化笔记（带引用）
- 无相关内容时 empty 拒答（不调 LLM，防幻觉铁律）
- 保存/列表/删除/导出（md + docx）
- 一键入库（note-save，同名加序号）+ ocr-save 重构回归
用法：在 app 目录下运行  venv\\Scripts\\python.exe tests\\test_notes.py
（需 API Key：生成笔记约 5 分钱）
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from backend import kb as kb_mod  # noqa: E402
from backend.server import create_app, load_settings  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("PASS | " if ok else "FAIL | ") + name + (f" | {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def wait_ingest(kb_id, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = kb_mod.get_ingest_status(kb_id) or {}
        if not st.get("running"):
            return st
        time.sleep(0.5)
    return {"error": "ingest timeout"}


def main():
    kb_mod.ensure_data_dirs()
    settings = load_settings()
    if not settings.get("api_key"):
        print("!! 尚未配置 API Key")
        sys.exit(1)
    app = create_app()
    client = app.test_client()

    # 1. 生成笔记（内置库：重金属检查法）
    r = client.post("/api/notes/generate", json={
        "keyword": "重金属检查法", "kb_ids": ["all"],
    }).get_json()
    check("生成笔记 ok", r.get("ok") is True, str(r)[:200])
    note = r.get("note") or ""
    check("笔记内容含标题", note.startswith("##") or "笔记" in note, note[:120])
    check("笔记带引用", bool(r.get("citations")), f"citations={len(r.get('citations') or [])}")

    # 2. 拒答双防线：
    #    阈值防线：完全不同领域的词 → empty 不调 LLM；
    #    模型铁律：同领域但主题漂移（embedding 无法区分物化 vs 高能物理）→ LLM 诚实拒答
    r = client.post("/api/notes/generate", json={
        "keyword": "王者荣耀打野出装攻略", "kb_ids": ["all"],
    }).get_json()
    check("无关领域词返回 empty（阈值防线）", r.get("ok") is True and r.get("empty") is True, str(r)[:160])

    r = client.post("/api/notes/generate", json={
        "keyword": "量子色动力学重整化群方程", "kb_ids": ["all"],
    }).get_json()
    check("同领域主题漂移拒答（模型铁律）",
          r.get("ok") is True and (r.get("empty") or "未找到" in (r.get("note") or "")),
          (r.get("note") or str(r))[:100])

    # 3. 保存 → 列表 → 删除
    r = client.post("/api/notes/save", json={
        "keyword": "重金属检查法", "kb_ids": ["all"], "content": note,
    }).get_json()
    nid = r.get("id")
    check("保存笔记", bool(nid), str(r))
    notes = client.get("/api/notes").get_json()["notes"]
    check("列表包含新笔记", any(n["id"] == nid for n in notes), f"共 {len(notes)} 篇")
    client.delete(f"/api/notes/{nid}")
    notes = client.get("/api/notes").get_json()["notes"]
    check("删除笔记", not any(n["id"] == nid for n in notes), "")

    # 4. 导出 md / docx
    r = client.post("/api/notes/export", json={
        "title": "重金属检查法", "content": note, "format": "md",
    }).get_json()
    check("导出 md", r.get("ok") is True and os.path.isfile(r.get("path") or ""), str(r)[:160])
    if r.get("path"):
        os.unlink(r["path"])
    r = client.post("/api/notes/export", json={
        "title": "重金属检查法", "content": note, "format": "docx",
    }).get_json()
    check("导出 docx", r.get("ok") is True and os.path.isfile(r.get("path") or ""), str(r)[:160])
    if r.get("path"):
        os.unlink(r["path"])

    # 5. 一键入库 + 检索命中 + ocr-save 重构回归 + 同名加序号
    kb_id = kb_mod.create_kb("笔记测试")
    try:
        r = client.post(f"/api/kbs/{kb_id}/note-save", json={
            "name": "道尔顿分压定律", "text": "道尔顿分压定律知识点：混合气体的总压等于各组分气体分压之和。P总=P1+P2。",
        }).get_json()
        check("note-save 入库", r.get("ok") is True, str(r))
        wait_ingest(kb_id)
        r = client.post("/api/search", json={
            "question": "道尔顿分压定律", "kb_ids": [kb_id], "top_k": 3, "threshold": 0.0,
        }).get_json()
        check("检索命中入库笔记", any("分压" in h["text"] for h in (r.get("hits") or [])), "")

        r = client.post(f"/api/kbs/{kb_id}/ocr-save", json={
            "name": "OCR回归", "text": "OCR保存重构回归测试内容。",
        }).get_json()
        check("ocr-save 回归（重构后）", r.get("ok") is True, str(r))
        wait_ingest(kb_id)

        r = client.post(f"/api/kbs/{kb_id}/note-save", json={
            "name": "道尔顿分压定律", "text": "第二次保存同名笔记：应生成序号文件、不覆盖已有文档。",
        }).get_json()
        check("同名入库自动加序号", r.get("ok") is True and r.get("file", "").endswith(".txt"), str(r))
        wait_ingest(kb_id)
        docs = client.get(f"/api/kbs/{kb_id}/docs").get_json()["docs"]
        check("同名文档两篇共存", sum(1 for d in docs if d["rel"].startswith("道尔顿分压定律")) == 2, str([d["rel"] for d in docs]))
    finally:
        kb_mod.delete_kb(kb_id)

    print("\n===== P2 notes result: %s =====" % ("ALL PASS" if not FAILED else f"{len(FAILED)} FAILED: {FAILED}"))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
