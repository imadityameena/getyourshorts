import json

import pytest

from app.pipeline.analyze.llm import format_batch, parse_ratings, rate_candidates
from app.pipeline.models import Candidate


def _cands(n: int) -> list[Candidate]:
    return [
        Candidate(id=i, start=i * 60, end=i * 60 + 30, text=f"text {i}", word_start=0, word_end=1)
        for i in range(n)
    ]


def _rating(i: int, **kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": i,
        "hook": 7,
        "standalone": 8,
        "payoff": 6,
        "emotion": 5,
        "title": f"Title {i}",
        "hook_line": "Wait for it",
        "reason": "Good.",
    }
    base.update(kw)
    return base


class FakeProvider:
    def __init__(self, name: str, outputs: list[str | Exception]) -> None:
        self.name = name
        self.outputs = outputs
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        out = self.outputs[min(self.calls - 1, len(self.outputs) - 1)]
        if isinstance(out, Exception):
            raise out
        return out


def test_parse_object_wrapper_and_fences() -> None:
    raw = "```json\n" + json.dumps({"ratings": [_rating(0), _rating(1)]}) + "\n```"
    rs = parse_ratings(raw, {0, 1})
    assert [r.id for r in rs] == [0, 1]


def test_parse_clamps_and_truncates() -> None:
    raw = json.dumps([_rating(0, hook=15, emotion="-2", title="x" * 200)])
    (r,) = parse_ratings(raw, {0})
    assert r.hook == 10 and r.emotion == 0 and len(r.title) == 60


def test_parse_drops_unknown_ids_and_rejects_too_few() -> None:
    raw = json.dumps([_rating(0), _rating(99)])
    assert [r.id for r in parse_ratings(raw, {0, 1})] == [0]
    with pytest.raises(ValueError):
        parse_ratings(json.dumps([_rating(99)]), {0, 1, 2, 3})


def test_parse_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_ratings("not json", {0})
    with pytest.raises(ValueError):
        parse_ratings(json.dumps({"foo": 1}), {0})


def test_format_batch_contains_ids_and_times() -> None:
    txt = format_batch(_cands(2), "My video")
    assert "[id=0]" in txt and "[id=1]" in txt and "1:00-1:30" in txt and "My video" in txt


def test_rate_retries_once_then_falls_back_to_next_provider() -> None:
    good = json.dumps({"ratings": [_rating(i) for i in range(3)]})
    bad = FakeProvider("gemini", ["oops", "still bad"])
    ok = FakeProvider("groq", [good])
    res = rate_candidates(_cands(3), [bad, ok], video_title="t", batch_size=10)
    assert bad.calls == 2
    assert ok.calls == 1
    assert res.provider == "groq"
    assert set(res.ratings) == {0, 1, 2}


def test_rate_provider_exception_moves_on_immediately() -> None:
    boom = FakeProvider("gemini", [RuntimeError("429")])
    ok = FakeProvider("ollama", [json.dumps([_rating(0)])])
    res = rate_candidates(_cands(1), [boom, ok], video_title="t")
    assert boom.calls == 1 and res.provider == "ollama"


def test_rate_all_fail_returns_empty() -> None:
    res = rate_candidates(_cands(2), [FakeProvider("g", ["x"])], video_title="t")
    assert res.ratings == {} and res.provider is None


def test_rate_batches() -> None:
    def out_for_all() -> str:
        return json.dumps([_rating(i) for i in range(25)])

    p = FakeProvider("g", [out_for_all()])
    seen: list[tuple[int, int]] = []
    res = rate_candidates(
        _cands(25), [p], video_title="t", batch_size=10, on_batch=lambda i, n: seen.append((i, n))
    )
    assert p.calls == 3
    assert seen == [(1, 3), (2, 3), (3, 3)]
    assert len(res.ratings) == 25


def test_http_retries_only_transient_errors() -> None:
    import httpx

    from app.pipeline.analyze.llm import GroqProvider

    calls = {"n": 0}

    def handler(status: int):  # type: ignore[no-untyped-def]
        def _h(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(status, json={"error": "x"})

        return _h

    for status, expected_calls in ((404, 1), (401, 1)):
        calls["n"] = 0
        p = GroqProvider("k", "m", 5)
        p.client = httpx.Client(transport=httpx.MockTransport(handler(status)))
        with pytest.raises(httpx.HTTPStatusError):
            p.complete("s", "u")
        assert calls["n"] == expected_calls


def test_http_retries_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from app.pipeline.analyze.llm import GroqProvider

    monkeypatch.setattr("app.core.retry.time.sleep", lambda _s: None)
    responses = iter([429, 503, 200])

    def _h(request: httpx.Request) -> httpx.Response:
        code = next(responses)
        body = {"choices": [{"message": {"content": "{}"}}]} if code == 200 else {}
        return httpx.Response(code, json=body)

    p = GroqProvider("k", "m", 5)
    p.client = httpx.Client(transport=httpx.MockTransport(_h))
    assert p.complete("s", "u") == "{}"
