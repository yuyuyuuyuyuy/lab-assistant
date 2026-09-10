# -*- coding: utf-8 -*-
"""自动化问答评测（金标对照回归）：引用溯源检查 + 要点覆盖率裁判 + 拒答检查。

用法：在 app 目录下运行
  venv\\Scripts\\python.exe tests\\eval.py [--dry]
  --dry  只校验金标数据与索引是否就绪，不调用大模型（免费）

费用：约 0.8~1 元/轮（20 单题 + 3 组追问 + 2 拒答的问答与裁判），按需运行。
输出：tests\\eval_reports\\eval_时间戳.md 报告 + latest_summary.json（供下次运行做回归对比）。

评分规则（见金标数据集 eval_dataset.json）：
- 溯源检查：回答引用文件名必须命中题目指定的来源子串（防止"答对了但依据是错的"）
- 要点覆盖率：裁判模型逐条判断金标准要点是否被覆盖，得分 = 覆盖数 / 要点数
- 及格线：溯源必过 且 要点覆盖 >= 60%；拒答题必须输出"资料中未找到相关内容"
- 多轮追问：每轮做溯源检查，全部通过才算该组通过
"""
import json
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台显示中文不乱码
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import chat, kb as kb_mod, search  # noqa: E402
from backend.embeddings import make_client  # noqa: E402
from backend.server import load_settings  # noqa: E402
import config  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(HERE, "eval_dataset.json")
REPORT_DIR = os.path.join(HERE, "eval_reports")
SUMMARY_PATH = os.path.join(REPORT_DIR, "latest_summary.json")

PASS_RATIO = 0.6  # 要点覆盖率及格线

JUDGE_SYSTEM = (
    "你是药品检验知识问答的评测裁判。根据【问题】与【金标准要点】，判断【回答】是否覆盖了每个要点。\n"
    "要求：\n"
    "1. 只依据回答文字判断；要点语义被覆盖即算覆盖（表述不同但意思一致也算）\n"
    "2. 回答为“资料中未找到相关内容”或答非所问时，所有要点均判为未覆盖\n"
    "3. 按要点顺序逐一输出，不得遗漏、不得合并，格式：\n"
    '{"results":[{"point":"<要点原文>","covered":true,"reason":"<一句话理由>"}]}\n'
    "只输出 JSON，不要任何其他文字。"
)


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


def check_sources(citations, expected):
    """引用文件名（或源文件名）命中任一指定子串即溯源通过；无引用直接失败。"""
    if not citations:
        return False
    for c in citations:
        hay = (c.get("file") or "") + "|" + (c.get("source") or "")
        if any(s in hay for s in expected):
            return True
    return False


def judge_points(client, settings, question, points, answer):
    """裁判：逐条判断金标准要点是否被回答覆盖。返回 (覆盖数, 总数, 明细列表, 异常信息)。"""
    prompt = "【问题】\n%s\n\n【金标准要点】\n%s\n\n【回答】\n%s" % (
        question,
        "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1)),
        answer,
    )
    try:
        resp = client.chat.completions.create(
            model=settings["llm_model"],
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=900,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return 0, len(points), [], f"裁判调用失败：{e}"
    results = _parse_judge(raw)
    if results is None:
        return 0, len(points), [], f"裁判输出无法解析：{raw[:80]}"
    if len(results) != len(points):
        return 0, len(points), [], f"裁判输出条数不符（期望{len(points)}，得到{len(results)}）"
    detail = []
    covered = 0
    for i, r in enumerate(results):
        ok = _covered(r.get("covered"))
        covered += 1 if ok else 0
        detail.append({"ok": ok, "reason": (r.get("reason") or "").strip()})
    return covered, len(points), detail, None


def _parse_judge(raw):
    """解析裁判 JSON：整体解析失败时退化为提取第一个 [...] 数组。"""
    try:
        data = json.loads(raw)
        return data.get("results") if isinstance(data, dict) else None
    except Exception:
        pass
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def _covered(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes", "是", "覆盖", "covered")


def _fmt_cites(citations):
    if not citations:
        return "（无引用）"
    return " ".join(f"[{c['n']}]{c['source']}" for c in citations)


def run_single(client, settings, store_vs, items):
    results = []
    for i, item in enumerate(items, 1):
        question = item["question"]
        answer, citations, _hits = ask_one(client, settings, store_vs, question, [])
        src_ok = check_sources(citations, item["sources"])
        covered, total, detail, judge_error = judge_points(
            client, settings, question, item["points"], answer
        )
        ratio = covered / total if total else 0
        passed = src_ok and ratio >= PASS_RATIO
        results.append(
            {
                "cat": "single",
                "idx": i,
                "question": question,
                "answer": answer,
                "citations": [c["source"] for c in citations],
                "sources_ok": src_ok,
                "points": covered,
                "points_total": total,
                "judge_detail": detail,
                "judge_error": judge_error,
                "passed": passed,
            }
        )
    return results


def run_multi(client, settings, store_vs, groups):
    results = []
    for g, group in enumerate(groups, 1):
        history = []
        turns = []
        for t, turn in enumerate(group["turns"], 1):
            question = turn["question"]
            answer, citations, _hits = ask_one(client, settings, store_vs, question, history)
            history.append({"q": question, "a": answer})
            src_ok = check_sources(citations, turn["sources"])
            turns.append(
                {
                    "question": question,
                    "answer": answer,
                    "citations": [c["source"] for c in citations],
                    "sources_ok": src_ok,
                }
            )
        results.append(
            {
                "cat": "multi",
                "idx": g,
                "turns": turns,
                "passed": all(t["sources_ok"] for t in turns),
            }
        )
    return results


def run_refusal(client, settings, store_vs, items):
    results = []
    for i, item in enumerate(items, 1):
        answer, citations, _hits = ask_one(client, settings, store_vs, item["question"], [])
        refused = "未找到" in answer
        results.append(
            {
                "cat": "refusal",
                "idx": i,
                "question": item["question"],
                "answer": answer,
                "passed": refused,
            }
        )
    return results


def load_previous_summary():
    try:
        with open(SUMMARY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_report(results, settings, report_path, prev, start_ts):
    def yesno(b):
        return "✅" if b else "❌"

    total_pass = sum(1 for r in results if r["passed"])
    lines = []
    lines.append(f"# 评测报告 {time.strftime('%Y-%m-%d %H:%M', time.localtime(start_ts))}\n")
    lines.append(
        f"- 模型：{settings['llm_model']} ｜ top_k={settings['top_k']} ｜ 阈值={settings['score_threshold']}"
    )
    lines.append(f"- 及格线：溯源必过 且 要点覆盖 ≥ {int(PASS_RATIO * 100)}%（拒答题必须拒答）\n")

    by_cat = {}
    for r in results:
        by_cat.setdefault(r["cat"], []).append(r)
    lines.append("## 总览\n")
    lines.append("| 类别 | 通过 | 总数 | 通过率 |")
    lines.append("|---|---|---|---|")
    for cat, name in (("single", "单轮"), ("multi", "多轮追问"), ("refusal", "拒答")):
        rs = by_cat.get(cat, [])
        ok = sum(1 for r in rs if r["passed"])
        lines.append(f"| {name} | {ok} | {len(rs)} | {int(100 * ok / len(rs)) if rs else '-'}% |")
    lines.append(f"\n**总分：{total_pass}/{len(results)}**\n")

    if prev:
        prev_map = {(r["cat"], r["idx"]): r["passed"] for r in prev.get("results", [])}
        regressed, fixed = [], []
        for r in results:
            key = (r["cat"], r["idx"])
            if key in prev_map and prev_map[key] and not r["passed"]:
                regressed.append(f"{r['cat']}-{r['idx']:02d} {r.get('question') or ''}")
            elif key in prev_map and not prev_map[key] and r["passed"]:
                fixed.append(f"{r['cat']}-{r['idx']:02d} {r.get('question') or ''}")
        lines.append("## 回归对比\n")
        lines.append(f"- 对比基线：{prev.get('time', '未知')}")
        lines.append(f"- 退化 {len(regressed)} 题：{'；'.join(regressed) if regressed else '无'}")
        lines.append(f"- 修复 {len(fixed)} 题：{'；'.join(fixed) if fixed else '无'}\n")

    for cat, name in (("single", "单轮详情"), ("multi", "多轮追问"), ("refusal", "拒答详情")):
        rs = by_cat.get(cat, [])
        if not rs:
            continue
        lines.append(f"## {name}\n")
        for r in rs:
            if cat == "single":
                lines.append(f"### {r['idx']:02d}. {r['question']} {yesno(r['passed'])}")
                lines.append(f"- 溯源：{yesno(r['sources_ok'])} 引用：{_fmt_sources(r['citations'])}")
                if r["judge_error"]:
                    lines.append(f"- 要点：⚠️ {r['judge_error']}")
                else:
                    lines.append(f"- 要点：{r['points']}/{r['points_total']}")
                    for j, d in enumerate(r["judge_detail"], 1):
                        lines.append(f"  - {yesno(d['ok'])} 要点{j}：{d['reason']}")
                lines.append(f"\n**回答**：{r['answer']}\n")
            elif cat == "multi":
                lines.append(f"### 第 {r['idx']} 组 {yesno(r['passed'])}")
                for t in r["turns"]:
                    lines.append(
                        f"- {yesno(t['sources_ok'])} {t['question']} 引用：{_fmt_sources(t['citations'])}"
                    )
                lines.append(f"\n**末轮回答**：{r['turns'][-1]['answer']}\n")
            else:
                lines.append(f"### {r['idx']:02d}. {r['question']} {yesno(r['passed'])}")
                lines.append(f"**回答**：{r['answer']}\n")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _fmt_sources(files):
    if not files:
        return "（无引用）"
    return "、".join(files)


def main():
    dry = "--dry" in sys.argv
    kb_mod.ensure_data_dirs()
    settings = load_settings()
    if not settings.get("api_key"):
        print("!! 尚未配置 API Key")
        sys.exit(1)
    store_vs = kb_mod.open_store(config.BUILTIN_KB_ID)
    if store_vs is None:
        print("!! 内置知识库还没有索引（先启动一次 APP 或运行索引）")
        sys.exit(1)
    with open(DATASET_PATH, encoding="utf-8") as f:
        data = json.load(f)

    singles, multis, refusals = data["single"], data["multi_turn"], data["refusal"]
    print(
        f"金标数据就绪：单轮 {len(singles)} 题 ｜ 追问 {len(multis)} 组 ｜ 拒答 {len(refusals)} 题"
    )
    if dry:
        print("--dry 模式：数据与索引校验通过，未调用大模型。")
        store_vs.close()
        return

    client = make_client(settings)
    start_ts = time.time()
    print("开始评测（约 1 元 API 费用，请稍候）…")
    try:
        results = []
        results += run_single(client, settings, store_vs, singles)
        results += run_multi(client, settings, store_vs, multis)
        results += run_refusal(client, settings, store_vs, refusals)
    finally:
        store_vs.close()

    prev = load_previous_summary()
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(start_ts))
    report_path = os.path.join(REPORT_DIR, f"eval_{stamp}.md")

    summary = {
        "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(start_ts)),
        "results": [
            {
                "cat": r["cat"],
                "idx": r["idx"],
                "question": r.get("question") or r["turns"][0]["question"],
                "passed": r["passed"],
                "sources_ok": r.get("sources_ok"),
                "points": r.get("points"),
                "points_total": r.get("points_total"),
            }
            for r in results
        ],
    }
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    write_report(results, settings, report_path, prev, start_ts)

    total_pass = sum(1 for r in results if r["passed"])
    print("\n===== 评测完成 =====")
    print(f"通过：{total_pass}/{len(results)}（单轮 {sum(1 for r in results if r['cat']=='single' and r['passed'])}/{len(singles)}，"
          f"追问 {sum(1 for r in results if r['cat']=='multi' and r['passed'])}/{len(multis)}，"
          f"拒答 {sum(1 for r in results if r['cat']=='refusal' and r['passed'])}/{len(refusals)}）")
    if prev:
        prev_map = {(r["cat"], r["idx"]): r["passed"] for r in prev.get("results", [])}
        regressed = [f"{r['cat']}-{r['idx']:02d}" for r in results
                     if prev_map.get((r["cat"], r["idx"])) and not r["passed"]]
        fixed = [f"{r['cat']}-{r['idx']:02d}" for r in results
                 if prev_map.get((r["cat"], r["idx"])) is False and r["passed"]]
        print(f"回归（vs {prev['time']}）：退化 {len(regressed)} 题 {regressed or ''}｜修复 {len(fixed)} 题 {fixed or ''}")
    print(f"报告：{report_path}")


if __name__ == "__main__":
    main()
