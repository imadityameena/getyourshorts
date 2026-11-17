import { describe, expect, it } from "vitest";
import { clampLengths } from "../components/SettingsPanel";
import { parseHash } from "../hooks/useHashRoute";
import { errorMessage, looksLikeYouTubeUrl } from "./api";
import { formatTime, scorePercent, stageIndex, stageLabel } from "./format";
import { forgetJob, loadRecent, rememberJob, updateRecentTitle } from "./recent";

describe("looksLikeYouTubeUrl", () => {
  it.each([
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "youtube.com/watch?v=dQw4w9WgXcQ&t=1",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    "https://m.youtube.com/watch?feature=share&v=dQw4w9WgXcQ",
  ])("accepts %s", (url) => expect(looksLikeYouTubeUrl(url)).toBe(true));

  it.each(["", "hello", "https://vimeo.com/123", "https://www.youtube.com/playlist?list=PL1"])(
    "rejects %s",
    (url) => expect(looksLikeYouTubeUrl(url)).toBe(false),
  );
});

describe("errorMessage", () => {
  it("reads string detail", () => expect(errorMessage({ detail: "Nope" }, "x")).toBe("Nope"));
  it("reads FastAPI validation detail", () =>
    expect(errorMessage({ detail: [{ msg: "Value error, min_len must be <= max_len" }] }, "x")).toBe(
      "min_len must be <= max_len",
    ));
  it("falls back", () => expect(errorMessage(null, "fallback")).toBe("fallback"));
});

describe("format", () => {
  it("formats times", () => {
    expect(formatTime(0)).toBe("0:00");
    expect(formatTime(75.4)).toBe("1:15");
    expect(formatTime(3725)).toBe("1:02:05");
  });
  it("clamps score percent", () => {
    expect(scorePercent(0.734)).toBe(73);
    expect(scorePercent(1.4)).toBe(100);
    expect(scorePercent(-1)).toBe(0);
  });
  it("maps stages", () => {
    expect(stageIndex("transcribing", "running")).toBe(1);
    expect(stageIndex("packaging", "done")).toBe(6);
    expect(stageLabel("queued", "queued")).toBe("Waiting in queue…");
    expect(stageLabel("rendering", "running")).toBe("Rendering…");
    expect(stageLabel("retrying", "running")).toMatch(/Retrying/);
  });
});

describe("clampLengths", () => {
  it("keeps valid ranges", () => expect(clampLengths(30, 60, "min")).toEqual([30, 60]));
  it("pushes max when min overtakes it", () => expect(clampLengths(58, 60, "min")).toEqual([58, 63]));
  it("pushes min when max drops below it", () => expect(clampLengths(30, 32, "max")).toEqual([27, 32]));
  it("respects absolute bounds", () => {
    expect(clampLengths(5, 200, "min")).toEqual([15, 90]);
    expect(clampLengths(90, 90, "min")).toEqual([85, 90]);
    expect(clampLengths(15, 15, "max")).toEqual([15, 20]);
    expect(clampLengths(Number.NaN, 60, "min")).toEqual([15, 60]);
  });
});

describe("parseHash", () => {
  it("routes", () => {
    expect(parseHash("")).toEqual({ page: "home" });
    expect(parseHash("#/")).toEqual({ page: "home" });
    expect(parseHash("#/jobs/abc123")).toEqual({ page: "job", jobId: "abc123" });
    expect(parseHash("#/jobs/")).toEqual({ page: "home" });
  });
});

describe("recent jobs", () => {
  it("remembers, dedupes, updates and forgets", () => {
    rememberJob({ id: "a", url: "u1", title: null, createdAt: "2026-01-01" });
    rememberJob({ id: "b", url: "u2", title: null, createdAt: "2026-01-02" });
    rememberJob({ id: "a", url: "u1", title: null, createdAt: "2026-01-03" });
    expect(loadRecent().map((j) => j.id)).toEqual(["a", "b"]);
    updateRecentTitle("b", "My video");
    expect(loadRecent()[1]?.title).toBe("My video");
    forgetJob("a");
    expect(loadRecent().map((j) => j.id)).toEqual(["b"]);
  });
  it("survives corrupted storage", () => {
    localStorage.setItem("gys.recentJobs", "{not json");
    expect(loadRecent()).toEqual([]);
  });
});
