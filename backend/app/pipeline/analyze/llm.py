"""AI ranking: Gemini → Groq → Ollama fallback, JSON-only, Pydantic-validated.

A batch that fails on every provider simply has no ratings; scoring then falls
back to the non-AI signals and the clip is marked "AI ranking unavailable".
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import httpx
from pydantic import TypeAdapter, ValidationError

from app.core.config import LLMConfig, ProviderConfig, Settings
from app.core.logging import get_logger
from app.core.retry import with_retries
from app.pipeline.models import Candidate, LLMRating, LLMResult

log = get_logger("llm")

SYSTEM_PROMPT = """You are an expert YouTube Shorts editor. For each candidate segment, rate 0-10:
- hook: do the first 3 seconds make a viewer stop scrolling?
- standalone: does it make sense with no context from the full video?
- payoff: does it end with a punchline, insight, reveal or emotional peak?
- emotion: surprise, humor, controversy, inspiration, or strong opinion?
Penalize: intros, sponsor reads, "like and subscribe", unfinished thoughts.
Also write:
- title: a catchy Shorts title, max 60 characters
- hook_line: a short on-screen text hook (max 80 characters) for the first seconds
- reason: one sentence explaining the rating
Return JSON only, in the form:
{"ratings": [{"id": 0, "hook": 0, "standalone": 0, "payoff": 0, "emotion": 0,
"title": "", "hook_line": "", "reason": ""}]}
Include exactly one entry per candidate id."""

_ratings_adapter = TypeAdapter(list[LLMRating])


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class _HttpProvider:
    name = "base"

    def __init__(self, model: str, timeout: float, client: httpx.Client | None = None) -> None:
        self.model = model
        self.client = client or httpx.Client(timeout=timeout)

    def _post(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        def _do() -> dict[str, Any]:
            r = self.client.post(url, json=payload, headers=headers)
            if r.status_code in (429, 500, 502, 503, 504):
                r.raise_for_status()  # retryable
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            return data

        return with_retries(
            _do,
            attempts=3,
            base_delay=3.0,
            retry_on=(httpx.TransportError, httpx.HTTPStatusError),
            what=f"llm:{self.name}",
        )


class GeminiProvider(_HttpProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        super().__init__(model, timeout)
        self.api_key = api_key

    def complete(self, system: str, user: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
        }
        data = self._post(url, payload, {"x-goog-api-key": self.api_key})
        return str(data["candidates"][0]["content"]["parts"][0]["text"])


class GroqProvider(_HttpProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        super().__init__(model, timeout)
        self.api_key = api_key

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }
        data = self._post(
            "https://api.groq.com/openai/v1/chat/completions",
            payload,
            {"Authorization": f"Bearer {self.api_key}"},
        )
        return str(data["choices"][0]["message"]["content"])


class OllamaProvider(_HttpProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        super().__init__(model, max(timeout, 180))  # local models are slower
        self.base_url = base_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.3},
        }
        data = self._post(f"{self.base_url}/api/chat", payload, {})
        return str(data["message"]["content"])


def build_providers(cfg: LLMConfig, settings: Settings) -> list[Provider]:
    out: list[Provider] = []
    for p in cfg.providers:
        prov = _make(p, cfg, settings)
        if prov is not None:
            out.append(prov)
    return out


def _make(p: ProviderConfig, cfg: LLMConfig, s: Settings) -> Provider | None:
    if p.name == "gemini" and s.gemini_api_key:
        return GeminiProvider(s.gemini_api_key, p.model, cfg.timeout_s)
    if p.name == "groq" and s.groq_api_key:
        return GroqProvider(s.groq_api_key, p.model, cfg.timeout_s)
    if p.name == "ollama" and s.ollama_url:
        return OllamaProvider(s.ollama_url, p.model, cfg.timeout_s)
    return None


def format_batch(cands: Sequence[Candidate], video_title: str) -> str:
    lines = [f'Video title: "{video_title}"', "", "Candidates:"]
    for c in cands:
        lines.append(f"[id={c.id}] ({_ts(c.start)}-{_ts(c.end)}, {c.duration:.0f}s)\n{c.text}\n")
    return "\n".join(lines)


def _ts(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def parse_ratings(raw: str, expected_ids: set[int]) -> list[LLMRating]:
    """Parse + validate model output. Raises ValueError on anything unusable."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    data: Any = json.loads(text)
    if isinstance(data, dict):
        data = data.get("ratings", data.get("candidates", data.get("results")))
    if not isinstance(data, list):
        raise ValueError("expected a list of ratings")
    for item in data:  # be lenient on length / numeric strings, strict on structure
        if isinstance(item, dict):
            for k in ("hook", "standalone", "payoff", "emotion"):
                if k in item:
                    item[k] = min(10.0, max(0.0, float(item[k])))
            item["title"] = str(item.get("title", ""))[:60]
            item["hook_line"] = str(item.get("hook_line", ""))[:80]
            item["reason"] = str(item.get("reason", ""))[:300]
    ratings = [r for r in _ratings_adapter.validate_python(data) if r.id in expected_ids]
    if len(ratings) < max(1, len(expected_ids) // 2):
        raise ValueError(f"only {len(ratings)}/{len(expected_ids)} ratings returned")
    return ratings


def rate_candidates(
    cands: Sequence[Candidate],
    providers: Sequence[Provider],
    *,
    video_title: str,
    batch_size: int = 10,
    on_batch: Callable[[int, int], None] | None = None,
) -> LLMResult:
    ratings: dict[int, LLMRating] = {}
    used: str | None = None
    batches = [cands[i : i + batch_size] for i in range(0, len(cands), batch_size)]
    for bi, batch in enumerate(batches):
        ids = {c.id for c in batch}
        prompt = format_batch(batch, video_title)
        for prov in providers:
            got = _try_provider(prov, prompt, ids)
            if got is not None:
                ratings.update({r.id: r for r in got})
                used = used or prov.name
                break
        else:
            log.warning("batch_unrated", batch=bi, ids=sorted(ids))
        if on_batch:
            on_batch(bi + 1, len(batches))
    return LLMResult(provider=used, ratings=ratings)


def _try_provider(prov: Provider, prompt: str, ids: set[int]) -> list[LLMRating] | None:
    for attempt in (1, 2):  # validation failure → retry once, then next provider
        try:
            raw = prov.complete(SYSTEM_PROMPT, prompt)
            return parse_ratings(raw, ids)
        except (ValueError, ValidationError, json.JSONDecodeError, KeyError, IndexError) as e:
            log.warning("llm_bad_output", provider=prov.name, attempt=attempt, error=str(e)[:300])
        except Exception as e:
            log.warning("llm_call_failed", provider=prov.name, error=str(e)[:300])
            return None
    return None
