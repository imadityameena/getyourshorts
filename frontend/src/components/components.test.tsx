import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Clip, JobSettings } from "../lib/api";
import { ClipCard } from "./ClipCard";
import { ProgressBar } from "./ProgressBar";
import { DEFAULT_SETTINGS, SettingsPanel } from "./SettingsPanel";
import { UrlInput } from "./UrlInput";

const clip: Clip = {
  id: "c1",
  rank: 1,
  start: 61,
  end: 105,
  duration: 42.5,
  score: 0.812,
  score_breakdown: {
    heatmap: null,
    ai_virality: 0.8,
    hook: 0.9,
    audio: 0.5,
    pace: 0.7,
    visual: 0.2,
    weights: { heatmap: 0, ai_virality: 0.615, hook: 0.154, audio: 0.123, pace: 0.062, visual: 0.046 },
  },
  title: "The hardest 100 days",
  hook: "Nobody tells you this",
  reason: "Strong opinion with a clear payoff.",
  ai_ranked: true,
  file_url: "/api/clips/c1/file",
  thumb_url: "/api/clips/c1/thumb",
};

describe("ClipCard", () => {
  it("shows title, score, hook, times and a download link", () => {
    render(<ClipCard clip={clip} />);
    expect(screen.getByRole("heading", { name: clip.title })).toBeInTheDocument();
    expect(screen.getByText("81")).toBeInTheDocument();
    expect(screen.getByText(clip.hook)).toBeInTheDocument();
    expect(screen.getByText("1:01 – 1:45")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download/i })).toHaveAttribute(
      "href",
      "/api/clips/c1/file?download=true",
    );
    expect(screen.getByText(/AI ranked/)).toBeInTheDocument();
  });

  it("reveals the score breakdown and marks missing signals", async () => {
    render(<ClipCard clip={clip} />);
    await userEvent.click(screen.getByRole("button", { name: /why this score/i }));
    expect(screen.getByText("Most replayed")).toBeInTheDocument();
    expect(screen.getByText("not available")).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();
  });

  it("flags clips ranked without AI", () => {
    render(<ClipCard clip={{ ...clip, ai_ranked: false }} />);
    expect(screen.getByText("AI ranking unavailable")).toBeInTheDocument();
  });
});

describe("ProgressBar", () => {
  it("shows the current stage and percentage", () => {
    render(<ProgressBar stage="transcribing" status="running" progress={33} />);
    expect(screen.getByText("Transcribing…")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "33");
  });
});

describe("SettingsPanel", () => {
  it("changes crop mode and length preset", async () => {
    let value: JobSettings = DEFAULT_SETTINGS;
    const onChange = vi.fn((v: JobSettings) => {
      value = v;
    });
    const { rerender } = render(<SettingsPanel value={value} onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: /blurred fill/i }));
    expect(value.crop_mode).toBe("blur");
    rerender(<SettingsPanel value={value} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "15–30s" }));
    expect(value).toMatchObject({ min_len: 15, max_len: 30, crop_mode: "blur" });
  });
});

describe("UrlInput", () => {
  it("reports typing and shows errors accessibly", async () => {
    const onChange = vi.fn();
    render(<UrlInput value="" onChange={onChange} error="Bad link" />);
    await userEvent.type(screen.getByLabelText(/youtube video link/i), "x");
    expect(onChange).toHaveBeenCalledWith("x");
    expect(screen.getByRole("alert")).toHaveTextContent("Bad link");
    expect(screen.getByLabelText(/youtube video link/i)).toHaveAttribute("aria-invalid", "true");
  });
});
