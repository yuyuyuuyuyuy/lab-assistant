# -*- coding: utf-8 -*-
"""语料统计（A3b）冒烟测试：触发内置库增量索引（文件未变化=复用旧索引，零 API 费用），
校验 /api/kbs/<id>/stats 返回台账与文件明细。

用法：在 app 目录下运行
  venv\\Scripts\\python.exe tests\\test_stats.py
"""
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from backend import kb as kb_mod  # noqa: E402
from backend.server import create_app, load_settings  # noqa: E402


def wait_ingest(kb_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = kb_mod.get_ingest_status(kb_id)
        if st and not st.get("running"):
            return st
        time.sleep(0.5)
    raise TimeoutError("索引超时")


def main():
    kb_mod.ensure_data_dirs()
    kb_mod.start_ingest(config.BUILTIN_KB_ID, load_settings())
    status = wait_ingest(config.BUILTIN_KB_ID)
    assert not status.get("error"), f"索引失败：{status.get('error')}"
    print(f"索引完成：{status['stats']}")

    app = create_app()
    c = app.test_client()

    r = c.get("/api/kbs").get_json()
    builtin = next(k for k in r["kbs"] if k["id"] == config.BUILTIN_KB_ID)
    print(f"/api/kbs：docs={builtin['docs']} chunks={builtin['chunks']}")

    r2 = c.get(f"/api/kbs/{config.BUILTIN_KB_ID}/stats").get_json()
    assert r2["ok"], f"stats 接口失败：{r2}"
    assert r2["ledger"] and not r2["ledger"].get("error"), "台账未落盘"
    print(f"台账：{r2['ledger']['updated_at']} ｜ 文件明细 {len(r2['files'])} 条 ｜ 未入库 {len(r2['missing'])} 个")
    assert len(r2["files"]) == builtin["docs"], "文件明细数与文档数不一致"
    assert not r2["missing"], f"存在未入库文件：{r2['missing']}"

    r3 = c.get("/api/kbs/不存在的库/stats").get_json()
    assert not r3["ok"], "不存在的库应报错"
    print("===== A3b 冒烟测试通过 =====")


if __name__ == "__main__":
    main()
