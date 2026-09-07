# -*- coding: utf-8 -*-
"""完整问答验收：20 题 + 3 组多轮 + 2 题拒答（走真实 API，一轮约 2~3 毛钱，按需运行）。

用法：在 app 目录下运行
  venv\\Scripts\\python.exe tests\\test_qa.py [--multi] [--refusal]
输出每题答案与引用清单，人工核对引用正确率与拒答情况。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import chat, kb as kb_mod, search, store  # noqa: E402
from backend.embeddings import make_client  # noqa: E402
from backend.server import load_settings  # noqa: E402
import config  # noqa: E402

DO_MULTI = "--multi" in sys.argv
DO_REFUSAL = "--refusal" in sys.argv
ALL = not (DO_MULTI or DO_REFUSAL)


def ask_one(client, settings, store_vs, question, history):
    """单轮问答：返回 (答案, 引用列表, 命中列表)。多轮时先改写追问再检索。"""
    search_q = chat.rewrite_question(client, settings, question, history)
    vec = search.query_vector(client, search_q, settings["embed_model"])
    hits = search.search_store(store_vs, vec, settings["top_k"], settings["score_threshold"])
    if not hits:
        return chat.REFUSAL_TEXT, [], []
    parts = list(chat.stream_answer(client, settings, question, hits, history))
    answer = "".join(parts)
    return answer, chat.extract_citations(answer, hits), hits


def run_single(client, settings, store_vs, questions):
    print("\n########## 单轮 20 题 ##########")
    for i, q in enumerate(questions, 1):
        answer, citations, hits = ask_one(client, settings, store_vs, q, [])
        cites = " ".join(f"[{c['n']}]{c['source']}" for c in citations) or "（无引用）"
        print(f"\n----- 第{i:02d}题 | {q}")
        print(f"引用: {cites}")
        print(f"回答: {answer}")


def run_multi(client, settings, store_vs, groups):
    print("\n########## 多轮追问 ##########")
    for g, questions in enumerate(groups, 1):
        print(f"\n===== 第{g}组 =====")
        history = []
        for q in questions:
            answer, citations, hits = ask_one(client, settings, store_vs, q, history)
            history.append({"q": q, "a": answer})
            cites = " ".join(f"[{c['n']}]" for c in citations) or "（无引用）"
            print(f"\n问: {q}\n引用: {cites}\n答: {answer}")


def run_refusal(client, settings, store_vs, questions):
    print("\n########## 拒答场景 ##########")
    for q in questions:
        answer, citations, hits = ask_one(client, settings, store_vs, q, [])
        print(f"\n问: {q}\n命中数: {len(hits)}\n答: {answer}")


def main():
    kb_mod.ensure_data_dirs()
    settings = load_settings()
    if not settings.get("api_key"):
        print("!! 尚未配置 API Key")
        sys.exit(1)
    client = make_client(settings)
    store_vs = kb_mod.open_store(config.BUILTIN_KB_ID)
    if store_vs is None:
        print("!! 内置知识库还没有索引")
        sys.exit(1)

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "acceptance_questions.json"), encoding="utf-8") as f:
        data = json.load(f)

    try:
        if ALL or not (DO_MULTI or DO_REFUSAL):
            run_single(client, settings, store_vs, data["single"])
        if ALL or DO_MULTI:
            run_multi(client, settings, store_vs, data["multi_turn"])
        if ALL or DO_REFUSAL:
            run_refusal(client, settings, store_vs, data["refusal"])
    finally:
        store_vs.close()
    print("\n===== 验收运行完毕 =====")


if __name__ == "__main__":
    main()
