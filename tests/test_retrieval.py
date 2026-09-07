# -*- coding: utf-8 -*-
"""检索验收：20 题 top-8 命中检查（只花 embedding 费用，可反复跑）。

用法：在 app 目录下运行
  venv\\Scripts\\python.exe tests\\test_retrieval.py
输出每题 top-8 命中的分数、文件名与原文片段，人工核对命中率（目标 ≥90%）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import kb as kb_mod, search  # noqa: E402
from backend.embeddings import make_client  # noqa: E402
from backend.server import load_settings  # noqa: E402
import config  # noqa: E402

TOP_K = 8


def short(path):
    return os.path.basename(path)


def main():
    kb_mod.ensure_data_dirs()
    settings = load_settings()
    if not settings.get("api_key"):
        print("!! 尚未配置 API Key：请先在设置页填写后再运行")
        sys.exit(1)

    client = make_client(settings)
    store = kb_mod.open_store(config.BUILTIN_KB_ID)
    if store is None:
        print("!! 内置知识库还没有索引，先运行:")
        print("   venv\\Scripts\\python.exe -c \"from backend import kb as k; from backend.server import load_settings; k.start_ingest('builtin_qc', load_settings())\"")
        sys.exit(1)

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "acceptance_questions.json"), encoding="utf-8") as f:
        data = json.load(f)

    for i, q in enumerate(data["single"], 1):
        vec = search.query_vector(client, q, settings["embed_model"])
        hits = store.search(vec, TOP_K)
        print(f"\n===== 第{i:02d}题 | {q}")
        for j, h in enumerate(hits, 1):
            text = h["text"].replace("\n", " ")
            if len(text) > 90:
                text = text[:90] + "…"
            print(f"  [{j}] {h['score']:.3f} | {short(h['file'])} | {text}")
    print(f"\n===== 输出完毕，共 {len(data['single'])} 题 =====")
    store.close()


if __name__ == "__main__":
    main()
