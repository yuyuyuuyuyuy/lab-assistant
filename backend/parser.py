# -*- coding: utf-8 -*-
"""文档解析：txt / pdf / docx → 分块列表。

分块规则（Dify 项目验证过的结论）：
- txt 按行切分（语料按"每行一条完整知识点"编写，每行自带主题词+数值）；
- pdf/docx 按自然段落切分，短段合并、超长段按句号分号断句；
- 绝不按固定字符数硬切。
"""
import os

from charset_normalizer import from_bytes


def read_text_file(path):
    """读取 txt，自动探测编码（UTF-8 / GB18030 等），失败时 ignore 兜底防乱码崩溃。"""
    with open(path, "rb") as f:
        raw = f.read()
    if not raw:
        return ""
    best = from_bytes(raw).best()
    if best is None:
        return raw.decode("utf-8", errors="ignore")
    return str(best)


def split_paragraphs(text, max_len=800, min_len=8):
    """按自然段落切块：短段落合并，超长段落按句号/分号断句。"""
    paras = []
    for p in text.replace("\r\n", "\n").split("\n\n"):
        joined = " ".join(l.strip() for l in p.split("\n") if l.strip())
        if joined:
            paras.append(joined)

    chunks, buf = [], ""
    for p in paras:
        buf = (buf + "\n" + p).strip()
        if len(buf) > max_len:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)

    result = []
    for c in chunks:
        if len(c) <= max_len:
            result.append(c)
            continue
        pieces, cur = [], ""
        for ch in c:
            cur += ch
            if ch in "。；;" and len(cur) >= min_len:
                pieces.append(cur.strip())
                cur = ""
        if cur.strip():
            pieces.append(cur.strip())
        result.extend(pieces)
    return [r for r in result if len(r) >= min_len]


def parse_txt(path):
    """txt 按行切分，每行一条完整知识点。"""
    text = read_text_file(path)
    return [l.strip() for l in text.splitlines() if len(l.strip()) >= 4]


def parse_pdf(path):
    import pymupdf

    doc = pymupdf.open(path)
    try:
        pages_text, scanned = [], 0
        for page in doc:
            t = page.get_text().strip()
            pages_text.append(t)
            if len(t) < 30:
                scanned += 1
    finally:
        doc.close()
    if pages_text and scanned / len(pages_text) > 0.7:
        raise ValueError("疑似扫描版 PDF（缺少文字层），图片 OCR 属二期功能，暂不支持")
    return split_paragraphs("\n\n".join(pages_text))


def parse_docx(path):
    from docx import Document

    paras = [p.text.strip() for p in Document(path).paragraphs if p.text.strip()]
    if not paras:
        return []
    return split_paragraphs("\n\n".join(paras))


SUPPORTED_EXTS = {".txt": parse_txt, ".pdf": parse_pdf, ".docx": parse_docx}


def parse_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"不支持的文件格式 {ext}（仅支持 txt / pdf / docx）")
    return SUPPORTED_EXTS[ext](path)
