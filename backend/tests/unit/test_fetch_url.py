import pytest

from app.core.errors import InvalidUrl
from app.pipeline.fetch import parse_video_id

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtube.com/watch?v={VID}&t=42s",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?si=abc",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/embed/{VID}",
        f"www.youtube.com/watch?v={VID}",
        f"https://www.youtube.com/watch?v={VID}&list=PL123",  # single video inside a playlist
    ],
)
def test_valid_urls(url: str) -> None:
    assert parse_video_id(url) == VID


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/playlist?list=PL123",
        "https://vimeo.com/123",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/@channel",
        "not a url",
        f"https://evil.com/watch?v={VID}",
    ],
)
def test_invalid_urls(url: str) -> None:
    with pytest.raises(InvalidUrl):
        parse_video_id(url)
