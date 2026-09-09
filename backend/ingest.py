# -*- coding: utf-8 -*-
"""索引构建：扫描文档目录 → 解析分块 → 向量化 → 入库。

增量策略：文件 md5 未变化时，直接从旧索引原样复制块（免重新向量化，省钱省时）；
任何文件变化（新增/修改/删除）都会反映到新索引，最后原子替换。
"""
import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import ocr, parser, vector_store
from .embeddings import embed, make_client


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_docs(docs_dir, extra_exts=()):
    """递归扫描支持的文档，返回 [(绝对路径, 相对路径)]。

    extra_exts 为额外收录的后缀（按文件名结尾匹配——OCR sidecar 形如
    「讲义.pdf.ocr.json」，os.path.splitext 只能取到 .json，必须整名匹配）。
    """
    found = []
    if not os.path.isdir(docs_dir):
        return found
    for root, _dirs, files in os.walk(docs_dir):
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext in parser.SUPPORTED_EXTS:
                found.append((os.path.join(root, name), os.path.relpath(os.path.join(root, name), docs_dir)))
            elif any(name.lower().endswith(e) for e in extra_exts):
                found.append((os.path.join(root, name), os.path.relpath(os.path.join(root, name), docs_dir)))
    return found


def _meta_from_rel(rel, kb_name):
    parts = rel.split(os.sep)
    category = parts[0] if len(parts) > 1 else ""
    return {"category": category, "source": os.path.basename(rel), "kb": kb_name}


def build_index(index_path, docs_dir, kb_name, settings, progress_cb=None):
    """重建索引（增量、原子替换）。progress_cb(pct, message)；返回统计 dict。"""
    progress_cb = progress_cb or (lambda pct, msg: None)
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    tmp_path = index_path + ".tmp"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    found = scan_docs(docs_dir, extra_exts=(parser.OCR_SIDECAR_EXT,))
    if not found:
        # 无文档：也建一个空索引，保证后续打开正常
        empty = vector_store.VectorStore(tmp_path)
        empty.close()
        vector_store.atomic_replace(tmp_path, index_path)
        progress_cb(100, "完成（暂无文档）")
        return {"files": 0, "chunks": 0, "new": 0, "copied": 0, "errors": []}

    old = None
    old_files = {}
    if os.path.exists(index_path):
        old = vector_store.VectorStore(index_path)
        old_files = old.get_files()

    client = make_client(settings)
    new = vector_store.VectorStore(tmp_path)
    stats = {"files": len(found), "new": 0, "copied": 0, "chunks": 0, "errors": []}
    n = len(found)
    # 已有 OCR sidecar 的 pdf 跳过直接解析（其内容由 sidecar 的页面文本代替）
    sidecars = {rel for _abs, rel in found if rel.lower().endswith(parser.OCR_SIDECAR_EXT)}

    try:
        for i, (abs_path, rel) in enumerate(found):
            pct = 5 + int(90 * i / n)
            progress_cb(pct, f"正在处理 {rel}")
            is_sidecar = rel.lower().endswith(parser.OCR_SIDECAR_EXT)
            base_rel = rel[: -len(parser.OCR_SIDECAR_EXT)] if is_sidecar else rel
            if not is_sidecar and (base_rel + parser.OCR_SIDECAR_EXT) in sidecars:
                continue  # 扫描版 pdf：交给 sidecar 索引
            md5 = _md5(abs_path)
            prev = old_files.get(rel)
            try:
                if prev and prev[0] == md5 and prev[1] > 0:
                    # 未变化：整文件复制，免重新向量化
                    new.copy_file(old, rel)
                    new.set_file(rel, md5, prev[1])
                    stats["copied"] += 1
                    stats["chunks"] += prev[1]
                elif is_sidecar:
                    # OCR sidecar：每页文本分段，chunk 携带页码与源 PDF 名
                    meta_base = _meta_from_rel(base_rel, kb_name)
                    chunks, metas = [], []
                    for text, page in parser.parse_ocr_json(abs_path):
                        for c in parser.split_paragraphs(text):
                            chunks.append(c)
                            metas.append(dict(meta_base, page=page))
                    if not chunks:
                        raise ValueError("OCR 结果为空")
                    vectors = embed(client, chunks, settings["embed_model"])
                    items = [
                        (new.max_id() + 1 + k, rel, text, vec, dict(meta, chunk=k))
                        for k, (text, vec, meta) in enumerate(zip(chunks, vectors, metas))
                    ]
                    new.add(items)
                    new.set_file(rel, md5, len(chunks))
                    stats["new"] += 1
                    stats["chunks"] += len(chunks)
                elif rel.lower().endswith(".pptx"):
                    # PPT：文本层零费用直接入库；图片型页提取页内图片并发 OCR 兜底
                    meta_base = _meta_from_rel(rel, kb_name)
                    pages = parser.parse_pptx(abs_path)
                    ocr_needed = [(page, imgs) for _text, page, imgs in pages if imgs]
                    ocr_texts = {}
                    if ocr_needed:
                        def ocr_page(page, imgs):
                            texts = []
                            for b in imgs:
                                uri = ocr.preprocess_image(b)
                                if uri is None:
                                    continue  # 无法解析的图片格式（如 EMF），跳过
                                last = None
                                for attempt in range(2):
                                    try:
                                        texts.append(ocr.recognize_image(client, settings["ocr_model"], uri))
                                        last = None
                                        break
                                    except Exception as e:
                                        last = e
                                        time.sleep(1.5 * (attempt + 1))
                                if last is not None:
                                    raise RuntimeError(f"识别失败：{last}")
                            return page, "\n".join(texts)

                        with ThreadPoolExecutor(max_workers=2) as ex:
                            futs = {ex.submit(ocr_page, p, imgs): p for p, imgs in ocr_needed}
                            done = 0
                            for fut in as_completed(futs):
                                p = futs[fut]
                                try:
                                    ocr_texts[p] = fut.result()[1]
                                except Exception as e:
                                    # 降级：该页保持文本层内容，不阻塞入库
                                    stats.setdefault("ocr_skipped", []).append(f"第{p}页：{e}")
                                done += 1
                                progress_cb(pct, f"正在识别 {rel} 图片页 {done}/{len(ocr_needed)}")
                    chunks, metas = [], []
                    for text, page, _imgs in pages:
                        full = text
                        if ocr_texts.get(page):
                            full = (full + "\n" if full else "") + ocr_texts[page]
                        if not full.strip():
                            continue  # 完全空页（无文本且 OCR 失败/无图片）
                        if len(full) <= 800:
                            chunks.append(full)
                            metas.append(dict(meta_base, page=page))
                        else:
                            for c in parser.split_paragraphs(full):
                                chunks.append(c)
                                metas.append(dict(meta_base, page=page))
                    if not chunks:
                        raise ValueError("未解析出任何文字内容（图片页识别失败或页面为空）")
                    vectors = embed(client, chunks, settings["embed_model"])
                    items = [
                        (new.max_id() + 1 + k, rel, text, vec, dict(meta, chunk=k))
                        for k, (text, vec, meta) in enumerate(zip(chunks, vectors, metas))
                    ]
                    new.add(items)
                    new.set_file(rel, md5, len(chunks))
                    stats["new"] += 1
                    stats["chunks"] += len(chunks)
                else:
                    chunks = parser.parse_file(abs_path)
                    if not chunks:
                        raise ValueError("未解析出任何文字内容（可能是图片型文档）")
                    vectors = embed(client, chunks, settings["embed_model"])
                    meta_base = _meta_from_rel(rel, kb_name)
                    items = [
                        (new.max_id() + 1 + k, rel, text, vec, dict(meta_base, chunk=k))
                        for k, (text, vec) in enumerate(zip(chunks, vectors))
                    ]
                    new.add(items)
                    new.set_file(rel, md5, len(chunks))
                    stats["new"] += 1
                    stats["chunks"] += len(chunks)
            except Exception as e:
                stats["errors"].append(f"{rel}: {e}")
                progress_cb(pct, f"{rel} 处理失败，已跳过")

        if stats["chunks"] == 0 and stats["errors"]:
            raise RuntimeError("全部文件处理失败：" + "；".join(stats["errors"][:3]))
    finally:
        if old is not None:
            old.close()
        new.close()

    vector_store.atomic_replace(tmp_path, index_path)
    progress_cb(100, "索引完成")
    return stats
