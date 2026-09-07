# -*- coding: utf-8 -*-
"""对话编排：检索命中 → 拼装防幻觉提示词 → 流式生成 → 引用解析。

无命中时由调用方直接返回拒答语，不发 API（省钱的第二道防线）。
"""
import re

import config


def load_system_prompt():
    try:
        with open(config.PROMPT_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "你是「实验室助手」。只能依据【参考资料】回答，每个结论后紧跟引用编号 [n]，查不到就说“资料中未找到相关内容”。"


def build_user_content(question, hits, history):
    """拼装用户消息：对话历史（仅助指代）+ 参考资料（编号）+ 问题。"""
    parts = []
    if history:
        lines = ["【对话历史】（仅用于理解「它」「该法」等指代，答案内容只能来自下方参考资料）"]
        for p in history:
            lines.append(f"问：{p['q']}")
            if p["a"]:
                lines.append(f"答：{p['a']}")
        parts.append("\n".join(lines))
    if hits:
        refs = []
        for i, h in enumerate(hits, 1):
            src = h.get("meta", {})
            tag = "｜".join(x for x in (src.get("kb", ""), src.get("category", ""), src.get("source", "")) if x)
            refs.append(f"[{i}]（来源：{tag}）\n{h['text']}")
        parts.append("【参考资料】\n" + "\n\n".join(refs))
    else:
        parts.append("【参考资料】\n（空：本轮未检索到相关内容）")
    parts.append(f"【用户问题】\n{question}")
    return "\n\n".join(parts)


def stream_answer(client, settings, question, hits, history):
    """流式返回答案文本增量（generator of str）。"""
    messages = [
        {"role": "system", "content": load_system_prompt()},
        {"role": "user", "content": build_user_content(question, hits, history)},
    ]
    stream = client.chat.completions.create(
        model=settings["llm_model"],
        messages=messages,
        stream=True,
        temperature=settings.get("temperature", 0),
        max_tokens=1500,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def extract_citations(answer, hits):
    """解析回答中的 [n]，按首次出现顺序返回引用列表（附原文供前端展示）。"""
    seen, out = set(), []
    for n in re.findall(r"\[(\d+)\]", answer):
        n = int(n)
        if 1 <= n <= len(hits) and n not in seen:
            seen.add(n)
            h = hits[n - 1]
            meta = h.get("meta", {})
            out.append(
                {
                    "n": n,
                    "text": h["text"],
                    "score": h["score"],
                    "file": h.get("file", ""),
                    "kb_name": h.get("kb_name") or meta.get("kb", ""),
                    "source": meta.get("source", ""),
                    "category": meta.get("category", ""),
                }
            )
    return out


REFUSAL_TEXT = "资料中未找到相关内容。"


REWRITE_SYSTEM = (
    "你是追问改写助手。把用户的追问改写为独立完整的问题："
    "把「它」「该法」「第三种」等指代词替换为对话历史中提到的具体对象。"
    "只输出改写后的问题本身，不要任何解释、不要引号。"
)


def rewrite_question(client, settings, question, history):
    """多轮追问改写：把「它分几种方法？」改成「重金属检查法分几种方法？」，用于检索。
    改写失败时返回原问题（降级不阻塞问答）。"""
    if not history:
        return question
    hist_lines = []
    for p in history[-3:]:
        hist_lines.append(f"问：{p['q']}")
        if p["a"]:
            hist_lines.append(f"答：{p['a']}")
    try:
        resp = client.chat.completions.create(
            model=settings["llm_model"],
            messages=[
                {"role": "system", "content": REWRITE_SYSTEM},
                {"role": "user", "content": "\n".join(hist_lines) + f"\n\n追问：{question}"},
            ],
            temperature=0,
            max_tokens=120,
        )
        out = (resp.choices[0].message.content or "").strip()
        return out if out else question
    except Exception:
        return question
