# SOURCE: NOT IN PAPERS. Own thin client for a hosted LLM (no GPU here). The provider is chosen by
# LLM_PROVIDER; the Gemini request format follows Google's Gemini API reference (generateContent,
# x-goog-api-key header). The key is read from os.environ only, sent only in a header, and removed from
# every message this module raises or logs. No request or response body is ever logged.
"""Provider-agnostic text generation: generate(system, user) -> LLMResult, or LLMUnavailable."""
from __future__ import annotations

import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("uvicorn.error")

DEFAULT_PROVIDER = "gemini"
# Verified 2026-11-04 on https://ai.google.dev/gemini-api/docs/models (Stable; free of charge on the free tier).
DEFAULT_MODELS = {"gemini": "gemini-3.5-flash-lite"}
# The free-tier requests per minute for each model are shown only in the AI Studio dashboard (not readable
# without signing in), so this default is deliberately low. Raise it with LLM_RPM after checking your project.
DEFAULT_RPM = 5
DEFAULT_TIMEOUT_S = 30.0
MAX_ATTEMPTS = 3          # tries per call (the first call plus up to two retries on 429/5xx)
MAX_AUTO_WAIT_S = 8.0     # a longer wait asked for by the provider is reported to the user, not slept
NO_KEY_FIX = "Set the LLM_API_KEY environment variable on the server (a key from Google AI Studio), then restart it."


class LLMUnavailable(Exception):
    """The generated part cannot be produced now. Carries the not_ready convention: reason and fix."""

    def __init__(self, kind: str, reason: str, fix: str, retry_after: int | None = None):
        super().__init__(reason)
        self.kind, self.reason, self.fix, self.retry_after = kind, reason, fix, retry_after


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    usage: dict = field(default_factory=dict)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def redact(text: str, key: str | None = None) -> str:
    """Remove the API key (and anything shaped like one) from text that may leave the server."""
    key = key or _env("LLM_API_KEY")
    if key:
        text = text.replace(key, "[key removed]")
    return text


class RateLimiter:
    """Sliding one-minute window. Never sleeps: a full window raises with the seconds to wait."""

    def __init__(self, rpm: int, clock=time.monotonic):
        self.rpm, self.clock = max(1, rpm), clock
        self._hits: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self.clock()
            while self._hits and now - self._hits[0] >= 60.0:
                self._hits.popleft()
            if len(self._hits) >= self.rpm:
                wait = max(1, int(60.0 - (now - self._hits[0]) + 0.999))
                raise rate_limited(wait)
            self._hits.append(now)


def rate_limited(seconds: int) -> LLMUnavailable:
    return LLMUnavailable("rate_limited", f"The AI service is rate limited. Try again in {seconds} seconds.",
                          "Wait and try again. The free tier allows only a few requests per minute and per day.", seconds)


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def generate(self, system: str, user: str, *, temperature: float = 0, max_output_tokens: int = 512) -> LLMResult: ...


class GeminiProvider(LLMProvider):
    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, model: str, *, rpm: int = DEFAULT_RPM, timeout: float = DEFAULT_TIMEOUT_S,
                 client: httpx.Client | None = None, sleep=time.sleep, limiter: RateLimiter | None = None):
        self._key, self.model, self._timeout, self._sleep = api_key, model, timeout, sleep
        self._client = client
        self.limiter = limiter or RateLimiter(rpm)

    def is_configured(self) -> bool:
        return bool(self._key)

    def _post(self, body: dict) -> httpx.Response:
        url = f"{self.BASE}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self._key, "Content-Type": "application/json"}
        if self._client is not None:
            return self._client.post(url, json=body, headers=headers, timeout=self._timeout)
        with httpx.Client() as c:
            return c.post(url, json=body, headers=headers, timeout=self._timeout)

    @staticmethod
    def _retry_seconds(r: httpx.Response) -> float | None:
        h = r.headers.get("retry-after")
        try:
            return float(h) if h else None
        except ValueError:
            return None

    def _message(self, r: httpx.Response) -> str:
        try:
            m = (r.json().get("error") or {}).get("message") or ""
        except Exception:
            m = ""
        return redact(str(m), self._key)[:300]

    def generate(self, system: str, user: str, *, temperature: float = 0, max_output_tokens: int = 512) -> LLMResult:
        if not self._key:
            raise LLMUnavailable("no_key", "The AI service is not set up: no API key is configured on the server.", NO_KEY_FIX)
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_output_tokens}}
        dropped_temperature = False
        last = "no response"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.limiter.acquire()
            try:
                r = self._post(body)
            except httpx.TimeoutException:
                last = "the request timed out"
                log.warning("llm gemini attempt %d: timeout", attempt)
                if attempt < MAX_ATTEMPTS:
                    self._sleep(min(2 ** attempt, MAX_AUTO_WAIT_S))
                    continue
                raise LLMUnavailable("timeout", "The AI service did not answer in time.", "Try again in a moment.")
            except httpx.HTTPError as e:  # connection problems; the message is the class name only
                last = type(e).__name__
                log.warning("llm gemini attempt %d: %s", attempt, last)
                if attempt < MAX_ATTEMPTS:
                    self._sleep(min(2 ** attempt, MAX_AUTO_WAIT_S))
                    continue
                raise LLMUnavailable("provider_error", f"The AI service could not be reached ({last}).", "Try again in a moment.")
            code = r.status_code
            if code == 200:
                return self._parse(r)
            log.warning("llm gemini attempt %d: HTTP %d", attempt, code)
            if code == 400 and not dropped_temperature and "temperature" in self._message(r).lower():
                body["generationConfig"].pop("temperature", None)  # some models ignore or reject it
                dropped_temperature = True
                continue
            if code in (401, 403):
                raise LLMUnavailable("bad_key", "The AI service rejected the API key.",
                                     "Check LLM_API_KEY on the server and that the Gemini API is enabled for that key's project.")
            if code == 429 or code >= 500:
                wait = self._retry_seconds(r)
                if code == 429 and wait is not None and wait > MAX_AUTO_WAIT_S:
                    raise rate_limited(int(wait + 0.999))
                if attempt < MAX_ATTEMPTS:
                    self._sleep(min(wait if wait is not None else 2 ** attempt, MAX_AUTO_WAIT_S))
                    continue
                if code == 429:
                    raise rate_limited(int(wait + 0.999) if wait else 30)
                raise LLMUnavailable("provider_error", f"The AI service returned an error (HTTP {code}).", "Try again later.")
            raise LLMUnavailable("provider_error", f"The AI service rejected the request (HTTP {code}).",
                                 "Try again later. If it keeps happening, check LLM_MODEL.")
        raise LLMUnavailable("provider_error", f"The AI service failed ({last}).", "Try again later.")

    def _parse(self, r: httpx.Response) -> LLMResult:
        try:
            data = r.json()
            cand = data["candidates"][0]
            text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", [])).strip()
        except Exception:
            raise LLMUnavailable("provider_error", "The AI service sent a reply that could not be read.", "Try again later.")
        if not text:
            why = cand.get("finishReason", "unknown") if isinstance(cand, dict) else "unknown"
            raise LLMUnavailable("provider_error", f"The AI service returned no text (finish reason: {why}).", "Try again later.")
        u = data.get("usageMetadata") or {}
        usage = {k: u[k] for k in ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "totalTokenCount") if k in u}
        usage["finishReason"] = cand.get("finishReason")
        return LLMResult(text=text, provider=self.name, model=self.model, usage=usage)


_PROVIDERS = {"gemini": GeminiProvider}
_cache: dict[tuple, LLMProvider] = {}
_cache_lock = threading.Lock()


def _rpm() -> int:
    try:
        return max(1, int(_env("LLM_RPM") or DEFAULT_RPM))
    except ValueError:
        return DEFAULT_RPM


def get_provider() -> LLMProvider:
    """The provider named by LLM_PROVIDER (default gemini), built from the environment. Cached so the
    rate limiter persists across requests. Raises LLMUnavailable for an unknown provider name."""
    name = (_env("LLM_PROVIDER") or DEFAULT_PROVIDER).lower()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise LLMUnavailable("bad_config", f"LLM_PROVIDER is set to an unknown provider ({name[:30]!r}).",
                             "Use one of: " + ", ".join(sorted(_PROVIDERS)) + ".")
    model = _env("LLM_MODEL") or DEFAULT_MODELS[name]
    key, rpm = _env("LLM_API_KEY"), _rpm()
    with _cache_lock:
        ck = (name, model, key, rpm)
        if ck not in _cache:
            _cache.clear()
            _cache[ck] = cls(key, model, rpm=rpm)
        return _cache[ck]


def reset() -> None:
    with _cache_lock:
        _cache.clear()


def generate(system: str, user: str, *, temperature: float = 0, max_output_tokens: int = 512) -> LLMResult:
    """One call through the configured provider. Raises LLMUnavailable; its text never holds the key."""
    try:
        return get_provider().generate(system, user, temperature=temperature, max_output_tokens=max_output_tokens)
    except LLMUnavailable as e:
        e.reason, e.fix = redact(e.reason), redact(e.fix)
        raise


def status() -> dict:
    """provider, model and readiness for GET /api/answer/status. Never includes the key."""
    try:
        p = get_provider()
    except LLMUnavailable as e:
        return {"provider": (_env("LLM_PROVIDER") or DEFAULT_PROVIDER).lower()[:30], "model": _env("LLM_MODEL") or None,
                "ready": False, "reason": e.reason, "fix": e.fix}
    if not p.is_configured():
        return {"provider": p.name, "model": p.model, "ready": False,
                "reason": "The AI service is not set up: no API key is configured on the server.", "fix": NO_KEY_FIX}
    return {"provider": p.name, "model": p.model, "ready": True, "reason": None, "fix": None}
