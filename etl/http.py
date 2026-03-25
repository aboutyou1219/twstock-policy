from __future__ import annotations

import os
import time
from threading import Lock

import random
import requests

_QPS = float(os.getenv("ETL_QPS", "4"))
_MIN_INTERVAL = 1.0 / _QPS if _QPS > 0 else 0.0
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}
_lock = Lock()
_last_request_at = 0.0


def _request_with_retry(url: str, timeout: int, params: dict | None, headers: dict | None, retries: int) -> requests.Response:
    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, timeout=timeout, params=params, headers=headers)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                backoff = (2 ** attempt) + random.random()
                time.sleep(backoff)
                continue
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= retries:
                raise
            backoff = (2 ** attempt) + random.random()
            time.sleep(backoff)
    if last_exc:
        raise last_exc
    raise RuntimeError("request failed without exception")


def get_json(url: str, timeout: int = 30, params: dict | None = None, retries: int = 3):
    global _last_request_at
    with _lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()

    resp = _request_with_retry(
        url,
        timeout=timeout,
        params=params,
        headers={**_DEFAULT_HEADERS, "Accept": "application/json"},
        retries=retries,
    )
    resp.raise_for_status()
    if not resp.content:
        print(f"[warn] empty response: {url}")
        return []
    try:
        data = resp.json()
    except Exception:
        sample = resp.text[:200].replace("\n", " ")
        print(f"[warn] non-JSON response from {url}: {sample}")
        return []
    return data


def get_text(url: str, timeout: int = 30, params: dict | None = None, retries: int = 3) -> str:
    global _last_request_at
    with _lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()

    resp = _request_with_retry(
        url,
        timeout=timeout,
        params=params,
        headers=_DEFAULT_HEADERS,
        retries=retries,
    )
    resp.raise_for_status()
    return resp.text
