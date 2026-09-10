# -*- coding: utf-8 -*-
"""P1 多知识库任选验收：
- /api/search 支持 kb_ids 列表（多选/单选/旧 kb_id 兼容）
- 会话创建与列表返回解析后的 kb_ids
- 旧会话（kb_id="all" 字符串）兼容读取
用法：在 app 目录下运行  venv\\Scripts\\python.exe tests\\test_multikb.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from backend import kb as kb_mod, store  # noqa: E402
from backend.server import create_app, load_settings  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("PASS | " if ok else "FAIL | ") + name + (f" | {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def wait_ingest(kb_id, timeout=120):
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

    # 1. 建一个临时自建库并放入专属文档
    kb_id = kb_mod.create_kb("多选测试")
    try:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        tmp.write("多选测试专属内容：药鉴二期验收用段落，仅存在于本测试库中。\n")
        tmp.close()
        kb_mod.import_files(kb_id, [tmp.name])
        os.unlink(tmp.name)
        kb_mod.start_ingest(kb_id, settings)
        st = wait_ingest(kb_id)
        check("测试库索引完成", not st.get("error"), str(st.get("stats", "")))
        if st.get("error"):
            print("   索引失败，退出")
            sys.exit(1)

        # 2. 多选检索：内置库 + 测试库，应命中测试库内容且带 kb_name
        r = client.post("/api/search", json={
            "question": "多选测试专属内容是什么",
            "kb_ids": [config.BUILTIN_KB_ID, kb_id], "top_k": 6, "threshold": 0.0,
        }).get_json()
        check("多选检索返回 ok", r.get("ok") is True, str(r)[:120])
        hits = r.get("hits") or []
        top = hits[0] if hits else {}
        check("多选检索命中测试库", top.get("file") == os.path.basename(tmp.name) or any(h.get("kb_id") == kb_id for h in hits), str(top)[:150])
        check("命中带 kb_name", bool(top.get("kb_name")), top.get("kb_name", ""))

        # 3. 单选检索：只选测试库，命中仍带 kb_name
        r = client.post("/api/search", json={
            "question": "多选测试专属内容是什么", "kb_ids": [kb_id], "top_k": 3, "threshold": 0.0,
        }).get_json()
        check("单选（kb_ids 单元素）ok", r.get("ok") is True)

        # 4. 旧 kb_id 字符串兼容
        r = client.post("/api/search", json={
            "question": "多选测试专属内容是什么", "kb_id": kb_id, "top_k": 3, "threshold": 0.0,
        }).get_json()
        check("旧 kb_id 兼容 ok", r.get("ok") is True and r.get("hits"))

        # 5. 会话 kb_ids 创建与列表解析
        r = client.post("/api/conversations", json={"kb_ids": [config.BUILTIN_KB_ID, kb_id]}).get_json()
        conv_id = r.get("id")
        check("会话创建（kb_ids 数组）", bool(conv_id), str(r))
        convs = client.get("/api/conversations").get_json()["conversations"]
        conv = next((c for c in convs if c["id"] == conv_id), None)
        check("会话列表返回 kb_ids", conv is not None and set(conv.get("kb_ids") or []) == {config.BUILTIN_KB_ID, kb_id}, str(conv))

        # 6. 旧数据兼容：直接写入 "all" 字符串的会话
        old_id = store.new_conversation("all", "旧格式会话")
        convs = client.get("/api/conversations").get_json()["conversations"]
        old = next((c for c in convs if c["id"] == old_id), None)
        check("旧格式 kb_id=all 解析为 ['all']", old is not None and old.get("kb_ids") == ["all"], str(old))
        check("旧格式按 kb_id 过滤命中", bool(client.get(f"/api/conversations?kb_id={kb_id}").get_json()["conversations"] and any(c["id"] == old_id for c in client.get("/api/conversations?kb_id=all").get_json()["conversations"])))

        # 7. 单元素单选列表会话
        r = client.post("/api/conversations", json={"kb_ids": [kb_id]}).get_json()
        convs = client.get("/api/conversations").get_json()["conversations"]
        one = next((c for c in convs if c["id"] == r["id"]), None)
        check("单选列表会话解析", one is not None and one.get("kb_ids") == [kb_id])

        # 8. delete_last_assistant（P4 重新生成依赖，先验证可用）
        store.add_message(conv_id, "user", "问题一")
        store.add_message(conv_id, "assistant", "回答一")
        store.add_message(conv_id, "user", "问题二")
        store.add_message(conv_id, "assistant", "回答二")
        store.delete_last_assistant(conv_id)
        msgs = store.get_messages(conv_id)
        check("delete_last_assistant 只删最后一条助手", [m["content"] for m in msgs] == ["问题一", "回答一", "问题二"], str(msgs))

        # 9. 增量索引回归：先建 2 文件 → 再加 1 新文件重建（旧块复制 id 必须重分配，
        #    否则与新文件的 id 区间重叠 → UNIQUE constraint failed: chunks.id）
        mix_kb = kb_mod.create_kb("多选增量回归")
        try:
            d = kb_mod.kb_paths(mix_kb)["docs"]
            for i in range(2):
                with open(os.path.join(d, f"旧文件{i}.txt"), "w", encoding="utf-8") as f:
                    f.write(f"旧文件{i}的知识点内容：仅用于增量回归测试。\n")
            kb_mod.start_ingest(mix_kb, settings)
            st = wait_ingest(mix_kb)
            check("增量回归-首建", not st.get("error") and st.get("stats", {}).get("chunks") == 2, str(st))
            with open(os.path.join(d, "新文件.txt"), "w", encoding="utf-8") as f:
                f.write("新文件的知识点内容：混合新旧文件的增量重建场景。\n")
            kb_mod.start_ingest(mix_kb, settings)
            st = wait_ingest(mix_kb)
            check("增量回归-混合重建（旧复制+新向量化）",
                  not st.get("error") and st.get("stats", {}).get("files") == 3
                  and not st.get("stats", {}).get("errors")
                  and st.get("stats", {}).get("chunks") == 3,
                  str(st))
            kb_mod.start_ingest(mix_kb, settings)
            st = wait_ingest(mix_kb)
            check("增量回归-全量复制", not st.get("error") and st.get("stats", {}).get("copied") == 3, str(st))
        finally:
            kb_mod.delete_kb(mix_kb)

    finally:
        kb_mod.delete_kb(kb_id)

    print("\n===== P1 result: %s =====" % ("ALL PASS" if not FAILED else f"{len(FAILED)} FAILED: {FAILED}"))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
