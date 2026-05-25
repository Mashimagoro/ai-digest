"""Gemini REST 客户端，配额耗尽时自动在多个模型间降级。"""
from __future__ import annotations

import json
import os
import time

import requests

_last_call = 0.0

MODEL_FALLBACK = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
]


def generate(prompt: str, model: str = "", rate_limit: float = 7.0) -> dict:
    """调用 Gemini，遇到 429/404 自动降级。返回解析后的 JSON，失败返回 {}。"""
    global _last_call

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {}

    elapsed = time.time() - _last_call
    if elapsed < rate_limit:
        time.sleep(rate_limit - elapsed)

    models = [model] + [m for m in MODEL_FALLBACK if m != model] if model else MODEL_FALLBACK
    _last_call = time.time()

    for m in models:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{m}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.3,
                "maxOutputTokens": 4096,
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=40)
            if resp.status_code == 200:
                return _parse(resp)
            if resp.status_code in (429, 404, 503):
                time.sleep(1)
                continue
            print(f"  [AI] {m} HTTP {resp.status_code}: {resp.text[:160]}")
            return {}
        except requests.RequestException as exc:
            print(f"  [AI] {m} 请求异常: {exc}")
            continue

    return {}


def _parse(resp) -> dict:
    try:
        text = (
            resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        )
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(text)
    except (json.JSONDecodeError, KeyError, IndexError):
        return {}
