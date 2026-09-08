# -*- coding: utf-8 -*-
"""图片 OCR：预处理 + 百炼多模态识别（qwen-vl 系列，复用 OpenAI 兼容 client）。"""
import base64
import io

from PIL import Image, ImageOps

MAX_EDGE = 3000        # 长边压缩目标（省流量提速，识别精度影响小）
JPEG_QUALITY = 85
RECOGNIZE_PROMPT = (
    "请识别图片中的全部文字，按原文顺序输出纯文本，保留换行与层级。"
    "只输出识别结果本身，不要解释、不要添加任何其他内容。"
    "无法辨认的字用「□」表示。"
)


def preprocess_image(data):
    """EXIF 方向校正 + 长边等比压缩 → JPEG base64 data URI；无效图片返回 None。"""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)  # 手机照片方向校正
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > MAX_EDGE:
            scale = MAX_EDGE / max(w, h)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return "data:image/jpeg;base64," + b64
    except Exception:
        return None


def recognize_image(client, model, image_uri, prompt=RECOGNIZE_PROMPT):
    """识别一张图片（client 为 openai 兼容 client；image_uri 为 base64 data URI 或 http 地址）。"""
    resp = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_uri}},
                {"type": "text", "text": prompt},
            ],
        }],
        temperature=0,
        max_tokens=4000,
    )
    return (resp.choices[0].message.content or "").strip()
