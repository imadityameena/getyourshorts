from app.pipeline.render.face_track import (
    CropPath,
    choose_track,
    longest_gap,
    sendcmd_script,
    smooth,
)


def test_choose_track_prefers_dominant_face() -> None:
    big_left = (0.3, 0.4, 0.2, 0.3)
    small_right = (0.8, 0.4, 0.05, 0.08)
    samples = [(i * 0.2, [big_left, small_right]) for i in range(10)]
    track = choose_track(samples)
    assert all(x is not None and abs(x - 0.3) < 1e-9 for x in track)


def test_choose_track_none_without_faces() -> None:
    assert choose_track([(0.0, []), (0.2, [])]) == [None, None]


def test_longest_gap() -> None:
    times = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6]
    track = [0.5, None, None, None, None, None, None, 0.5, 0.5]
    assert abs(longest_gap(times, track, 1.8) - 1.2) < 1e-9
    assert longest_gap(times, [None] * 9, 1.8) == 1.8
    assert longest_gap(times, [0.5] * 9, 1.8) == 0


def test_smooth_dead_zone_ignores_small_jitter() -> None:
    track: list[float | None] = [0.5, 0.51, 0.49, 0.505, 0.5]
    out = smooth(track, alpha=0.5, dead_zone=0.1, crop_frac=0.5)
    assert all(abs(x - 0.5) < 1e-9 for x in out)


def test_smooth_follows_big_moves_gradually() -> None:
    track: list[float | None] = [0.3] + [0.7] * 20
    out = smooth(track, alpha=0.3, dead_zone=0.1, crop_frac=0.3)
    assert out[1] < 0.7 and out[1] > 0.3  # eased, not jumped
    assert abs(out[-1] - 0.7) < 0.01
    assert out == sorted(out)


def test_sendcmd_interpolates_and_dedupes() -> None:
    path = CropPath(crop_w=606, crop_h=1080, times=[0.0, 1.0, 2.0], xs=[100, 200, 200])
    script = sendcmd_script(path, fps=10)
    lines = [ln for ln in script.splitlines() if ln]
    assert lines[0] == "0.0000 crop@fc x 100;"
    xs = [int(ln.split()[-1].rstrip(";")) for ln in lines]
    assert xs == sorted(xs) and xs[-1] == 200
    assert all(x % 2 == 0 for x in xs)
    assert len(lines) <= 11  # no repeats once x stops changing
