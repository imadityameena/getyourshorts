"""Runs the six stages in order. Every stage writes its output to disk and is
skipped when a valid output already exists — that is how caching and resume work.
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from app.core.config import AppConfig, Settings
from app.core.errors import JobCancelled
from app.core.logging import get_logger, log_stage
from app.pipeline import fetch
from app.pipeline.analyze import llm as llm_mod
from app.pipeline.analyze.audio import rms_envelope
from app.pipeline.analyze.scenes import detect_cuts
from app.pipeline.models import (
    Candidate,
    JobSettings,
    LLMResult,
    RenderedClip,
    RenderResult,
    Selection,
    Shortlist,
    Signals,
    Transcript,
    VideoMeta,
)
from app.pipeline.render.clip import render_clip
from app.pipeline.select.selector import select, shortlist
from app.storage.files import (
    JobPaths,
    VideoPaths,
    file_ok,
    job_paths,
    load_valid,
    video_paths,
    write_model,
)

log = get_logger("runner")

ProgressFn = Callable[[str, int], None]
CancelFn = Callable[[], bool]

# (stage, start %, end %)
STAGES = {
    "downloading": (0, 20),
    "transcribing": (20, 45),
    "analyzing": (45, 65),
    "selecting": (65, 70),
    "rendering": (70, 97),
    "packaging": (97, 100),
}

RMS_HOP_S = 0.5


@dataclass
class PipelineResult:
    meta: VideoMeta
    selection: Selection
    render: RenderResult
    vpaths: VideoPaths
    jpaths: JobPaths


@dataclass
class Runner:
    video_id: str
    settings: JobSettings
    settings_hash: str
    env: Settings
    cfg: AppConfig
    report: ProgressFn = lambda stage, pct: None
    cancelled: CancelFn = lambda: False
    providers: list[llm_mod.Provider] | None = None
    _scene_future: Future[list[float]] | None = field(default=None, init=False)

    def _progress(self, stage: str, frac: float = 0.0) -> None:
        if self.cancelled():
            raise JobCancelled(self.video_id)
        lo, hi = STAGES[stage]
        self.report(stage, int(lo + (hi - lo) * max(0.0, min(1.0, frac))))

    def run(self) -> PipelineResult:
        vp = video_paths(self.env.storage_dir, self.video_id)
        jp = job_paths(self.env.storage_dir, self.video_id, self.settings_hash)
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="scenes") as bg:
            meta = self.stage_fetch(vp)
            if load_valid(vp.signals, Signals) is None:
                # scene detection is CPU-bound; overlap it with (GPU) transcription
                self._scene_future = bg.submit(detect_cuts, vp.source)
            transcript = self.stage_transcribe(vp)
            signals = self.stage_signals(vp, meta)
        shortlisted, llm_result = self.stage_ai(jp, transcript, signals, meta)
        selection = self.stage_select(jp, shortlisted, llm_result, transcript, signals)
        render = self.stage_render(vp, jp, meta, transcript, selection)
        self.stage_package(jp, render)
        return PipelineResult(meta, selection, render, vp, jp)

    # 1 ---------------------------------------------------------------------
    def stage_fetch(self, vp: VideoPaths) -> VideoMeta:
        self._progress("downloading")
        cached = load_valid(vp.meta, VideoMeta)
        if cached and file_ok(vp.source) and file_ok(vp.audio):
            return cached
        with log_stage("fetch"):
            meta = fetch.download(self.video_id, vp, self.cfg)
        self._progress("downloading", 1)
        return meta

    # 2 ---------------------------------------------------------------------
    def stage_transcribe(self, vp: VideoPaths) -> Transcript:
        self._progress("transcribing")
        cached = load_valid(vp.transcript, Transcript)
        if cached:
            return cached
        from app.pipeline.transcribe import transcribe

        with log_stage("transcribe"):
            t = transcribe(vp.audio, self.env.resolved_whisper_model, self.env.use_gpu)
            write_model(vp.transcript, t)
        self._progress("transcribing", 1)
        return t

    # 3a --------------------------------------------------------------------
    def stage_signals(self, vp: VideoPaths, meta: VideoMeta) -> Signals:
        self._progress("analyzing")
        cached = load_valid(vp.signals, Signals)
        if cached:
            return cached
        with log_stage("signals"):
            rms = rms_envelope(vp.audio, RMS_HOP_S)
            cuts = self._scene_future.result() if self._scene_future else detect_cuts(vp.source)
            sig = Signals(
                duration=meta.duration or len(rms) * RMS_HOP_S,
                heatmap=meta.heatmap,
                rms_hop_s=RMS_HOP_S,
                rms=rms,
                scene_cuts=cuts,
            )
            write_model(vp.signals, sig)
        return sig

    # 3b --------------------------------------------------------------------
    def stage_ai(
        self, jp: JobPaths, transcript: Transcript, signals: Signals, meta: VideoMeta
    ) -> tuple[list[Candidate], LLMResult]:
        sl = load_valid(jp.candidates, Shortlist)
        if sl is None:
            sl = Shortlist(
                candidates=shortlist(transcript, signals, self.settings, self.cfg.selection)
            )
            write_model(jp.candidates, sl)
        self._progress("analyzing", 0.3)
        cached = load_valid(jp.llm, LLMResult)
        if cached:
            return sl.candidates, cached
        providers = self.providers
        if providers is None:
            providers = llm_mod.build_providers(self.cfg.llm, self.env)
        with log_stage("ai_rank"):
            res = llm_mod.rate_candidates(
                sl.candidates,
                providers,
                video_title=meta.title,
                batch_size=self.cfg.llm.batch_size,
                on_batch=lambda i, n: self._progress("analyzing", 0.3 + 0.7 * i / n),
            )
            write_model(jp.llm, res)
        return sl.candidates, res

    # 4 ---------------------------------------------------------------------
    def stage_select(
        self,
        jp: JobPaths,
        shortlisted: list[Candidate],
        llm_result: LLMResult,
        transcript: Transcript,
        signals: Signals,
    ) -> Selection:
        self._progress("selecting")
        cached = load_valid(jp.selection, Selection)
        if cached:
            return cached
        with log_stage("select"):
            sel = select(
                shortlisted, llm_result, transcript, signals, self.settings, self.cfg.selection
            )
            write_model(jp.selection, sel)
        log.info("selected", clips=len(sel.clips), ai=sel.ai_provider)
        return sel

    # 5 ---------------------------------------------------------------------
    def stage_render(
        self,
        vp: VideoPaths,
        jp: JobPaths,
        meta: VideoMeta,
        transcript: Transcript,
        selection: Selection,
    ) -> RenderResult:
        self._progress("rendering")
        cached = load_valid(jp.render, RenderResult)
        if cached and all(file_ok(jp.root / c.file) for c in cached.clips):
            return cached
        words = transcript.words()
        rc = self.cfg.render
        workers = rc.max_parallel_gpu if self.env.use_gpu else rc.max_parallel_cpu
        results: dict[int, RenderedClip] = {}
        done = 0
        with log_stage("render"), ThreadPoolExecutor(max_workers=workers) as pool:
            futures: dict[Future[RenderedClip], int] = {}
            for clip in selection.clips:
                out, thumb = jp.clip(clip.rank), jp.thumb(clip.rank)
                futures[
                    pool.submit(
                        render_clip,
                        source=vp.source,
                        meta=meta,
                        clip=clip,
                        words=words,
                        out=out,
                        thumb=thumb,
                        crop_mode=self.settings.crop_mode,
                        caption_style=self.settings.caption_style,
                        render_cfg=rc,
                        captions_cfg=self.cfg.captions,
                        use_gpu=self.env.use_gpu,
                        timeout=self.cfg.limits.ffmpeg_timeout_s,
                    )
                ] = clip.rank
            try:
                for fut in as_completed(futures):
                    results[futures[fut]] = fut.result()
                    done += 1
                    self._progress("rendering", done / max(1, len(futures)))
            except BaseException:
                for f in futures:
                    f.cancel()
                raise
        res = RenderResult(clips=[results[k] for k in sorted(results)])
        write_model(jp.render, res)
        return res

    # 6 ---------------------------------------------------------------------
    def stage_package(self, jp: JobPaths, render: RenderResult) -> None:
        self._progress("packaging")
        if file_ok(jp.zip, 1):
            return
        tmp = jp.zip.with_suffix(".tmp")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as z:
            for c in render.clips:
                z.write(jp.root / c.file, arcname=f"short_{c.rank:02d}.mp4")
            sel = jp.selection
            if sel.exists():
                z.write(sel, arcname="selection.json")
        tmp.replace(jp.zip)
        self._progress("packaging", 1)
