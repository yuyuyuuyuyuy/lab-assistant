# -*- coding: utf-8 -*-
"""向量化：调用阿里云百炼 text-embedding-v4（OpenAI 兼容接口）。

只对外暴露 embed() 一个接口，将来换本地模型只改本文件。
"""
from openai import OpenAI


def make_client(settings):
    if not settings.get("api_key"):
        raise RuntimeError("尚未配置 API Key，请先在设置页填写百炼 API Key")
    return OpenAI(api_key=settings["api_key"], base_url=settings["base_url"])


def embed(client, texts, model, batch_size=10):
    """批量向量化，返回 list[list[float]]；每批失败自动重试 2 次。"""
    vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        last_err = None
        for attempt in range(3):
            try:
                resp = client.embeddings.create(model=model, input=batch, encoding_format="float")
                got = [d.embedding for d in resp.data]
                if len(got) != len(batch):
                    raise RuntimeError(f"向量化返回数量不一致：期望 {len(batch)} 实际 {len(got)}")
                vectors.extend(got)
                last_err = None
                break
            except Exception as e:  # 网络抖动等，重试
                last_err = e
        if last_err is not None:
            raise RuntimeError(f"向量化失败（批次 {i // batch_size + 1}）：{last_err}")
    return vectors
