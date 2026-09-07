# -*- coding: utf-8 -*-
"""检索：问题向量化 + 单库/多库检索。"""
from .embeddings import embed


def query_vector(client, question, model):
    return embed(client, [question], model)[0]


def search_store(store, vec, top_k, threshold):
    """单库检索：先取 top_k*3 候选，再按阈值过滤、截断到 top_k（给阈值留余地）。"""
    hits = [h for h in store.search(vec, top_k * 3) if h["score"] >= threshold]
    return hits[:top_k]


def search_multi(kb_stores, vec, top_k, threshold):
    """多库（"全部"模式）合并检索：各库各取候选，合并按分数取前 top_k。

    kb_stores: [(kb_id, kb_name, VectorStore)]
    每条命中附 kb_id / kb_name 供引用展示。
    """
    merged = []
    for kb_id, kb_name, store in kb_stores:
        for h in store.search(vec, top_k * 3):
            if h["score"] >= threshold:
                h["kb_id"] = kb_id
                h["kb_name"] = kb_name
                merged.append(h)
    merged.sort(key=lambda x: -x["score"])
    return merged[:top_k]
