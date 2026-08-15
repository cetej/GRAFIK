"""Async video job layer — task 1.7, architecture A4 ("Video joby jako async
fronta s persistencí", docs/plans/2026-08-14-unified-editor.md).

No request in this module ever waits for a video to finish generating (fal
generation takes minutes). `submit_video_job` returns as soon as fal.ai hands
back a `request_id`; that id is persisted onto the project immediately, so a
later `refresh_video_job` call can recover an in-flight job even after a
process restart (A4 falsifier: "fal queue API nedava stabilni job-id napric
restarty -> lokalni mapping file" -- the mapping file IS project.json here,
since ClipRecord already lives on LayerProject.clips).

All fal.ai network I/O is isolated behind five module-level functions
(_upload, _submit, _status, _result, _download) so tests can monkeypatch
each one individually and exercise submit_video_job/refresh_video_job fully
offline -- mirrors the isolation pattern in
grafik.providers.qwen_inpaint.QwenInpaintProvider._run_remote.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import fal_client
import httpx

from grafik.core.composer import compose
from grafik.core.costs import record_paid_call
from grafik.core.motion import ClipRecord, MotionSpec
from grafik.core.project import LayerProject
from grafik.motion.compiler import build_video_payload, compile_motion_prompt
from grafik.providers.registry import RegistryEntry, get_provider


def _upload(path: Path) -> str:
    """Upload a local file to the fal CDN, return its URL. Isolated for monkeypatching."""
    return fal_client.upload_file(str(path))


def _submit(endpoint: str, payload: dict) -> str:
    """Submit a job to the fal queue, return its request_id. Isolated for monkeypatching."""
    handle = fal_client.submit(endpoint, arguments=payload)
    return handle.request_id


def _status(endpoint: str, request_id: str) -> fal_client.Status:
    """Poll one job's queue status (Queued | InProgress | Completed). Isolated for monkeypatching."""
    return fal_client.status(endpoint, request_id, with_logs=False)


def _result(endpoint: str, request_id: str) -> dict:
    """Fetch a completed job's result payload. Isolated for monkeypatching."""
    return fal_client.result(endpoint, request_id)


def _download(url: str) -> bytes:
    """Download raw bytes from a URL (the result video, not an image -- unlike
    grafik.fal.upload.download_url, this does not decode through PIL).
    Isolated for monkeypatching.
    """
    resp = httpx.get(url, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def _cost_note(entry: RegistryEntry, duration: str) -> str:
    """Cheap one-line cost estimate for a ClipRecord, e.g.
    "~$0.50 (5 s × $0.10/s, 720p; orientační, sekundární zdroj)". Empty
    string when the provider's per-second rate isn't known (RegistryEntry.
    info.est_cost_usd_per_second, e.g. seedance-25) or duration isn't
    numeric (e.g. seedance-25's "auto") -- never a guess presented as fact.
    """
    per_second = entry.info.est_cost_usd_per_second
    if per_second is None:
        return ""
    try:
        seconds = float(duration)
    except ValueError:
        return ""
    total = per_second * seconds
    resolution = entry.info.payload_defaults.get("resolution")
    suffix = f", {resolution}" if resolution else ""
    return f"~${total:.2f} ({duration} s × ${per_second:.2f}/s{suffix}; orientační, sekundární zdroj)"


def submit_video_job(
    project: LayerProject,
    project_dir: Path,
    spec: MotionSpec,
    provider_id: str,
    prompt_override: str = "",
) -> ClipRecord:
    """Composite the project, submit an async I2V job, persist a "running"
    ClipRecord, and return immediately (no polling here -- see module docstring).

    Args:
        project: loaded LayerProject (mutated in place: a ClipRecord is
            appended to project.clips).
        project_dir: the project's .grafik directory (for compose() and save()).
        spec: per-layer trajectory/static/description + camera intent; compiled
            to a text prompt by grafik.motion.compiler (A3 amendment -- no
            current fal I2V endpoint accepts a structured mask/camera payload).
        provider_id: registry id of a "video"-kind provider (e.g. "kling-26-pro").
        prompt_override: if non-empty (after stripping), used INSTEAD of the
            compiled prompt -- lets a user hand-edit the /video/compile
            preview before submitting. Saved verbatim onto ClipRecord.prompt.

    Returns:
        The new ClipRecord (status="running", request_id set), already
        appended to project.clips and saved to project_dir/project.json.

    Raises:
        KeyError: provider_id is not a registered provider (grafik.providers.registry.get_provider).
        ValueError: provider_id names a provider that is not kind "video", or
            spec.duration is not one of the provider's duration_choices.
    """
    entry = get_provider(provider_id)
    if entry.info.kind != "video":
        raise ValueError(f"Provider {provider_id!r} is kind {entry.info.kind!r}, expected 'video'")

    composite = compose(project, project_dir)
    with tempfile.TemporaryDirectory(prefix="grafik_video_") as tmp:
        tmp_png = Path(tmp) / "composite.png"
        composite.save(tmp_png, "PNG")
        image_url = _upload(tmp_png)

    prompt = prompt_override.strip() or compile_motion_prompt(project, spec)
    payload = build_video_payload(entry, image_url, prompt, spec.duration)
    request_id = _submit(entry.info.endpoint, payload)

    # Cost ledger (M4): async jobs never pass through tracked_subscribe, so the
    # commitment is recorded here at submit time. Non-numeric durations (e.g.
    # seedance "auto") record seconds=None -> est_usd=None, never a guess.
    try:
        seconds: float | None = float(spec.duration)
    except ValueError:
        seconds = None
    record_paid_call(
        entry.info.endpoint,
        "video",
        seconds=seconds,
        note=f"submit {provider_id}, duration={spec.duration}",
        project_dir=project_dir,
    )

    record = ClipRecord(
        provider_id=provider_id,
        endpoint=entry.info.endpoint,
        status="running",
        request_id=request_id,
        prompt=prompt,
        motion=spec,
        cost_note=_cost_note(entry, spec.duration),
    )
    project.clips.append(record)
    project.save(project_dir)
    return record


def refresh_video_job(project: LayerProject, project_dir: Path, clip_id: str) -> ClipRecord:
    """Poll one clip's fal job and update its ClipRecord in place.

    Queued/InProgress leave status="running" untouched. Completed downloads
    the mp4 to `<project_dir>/clips/<clip_id>.mp4` and sets status="completed".
    Any exception (moderation rejection, timeout, malformed result, ...) sets
    status="failed" with the reason in `error` -- the raw fal message is kept
    verbatim, per ideal-state criterion #11 ("Selhani generace (moderace/
    timeout) zobrazi duvod a nepoškodi projekt").

    The project is saved to disk in every branch (running/completed/failed),
    so a failure never leaves project.json in a state that fails to reload.

    Args:
        project: loaded LayerProject (mutated in place).
        project_dir: the project's .grafik directory.
        clip_id: ClipRecord.id to refresh.

    Returns:
        The updated ClipRecord.

    Raises:
        ValueError: no clip with this id exists on project.clips.
    """
    record = next((c for c in project.clips if c.id == clip_id), None)
    if record is None:
        raise ValueError(f"Clip {clip_id} not found in project {project.id}")

    if record.status == "running":
        try:
            status = _status(record.endpoint, record.request_id)
            if isinstance(status, fal_client.Completed):
                result = _result(record.endpoint, record.request_id)
                video_url = (result.get("video") or {}).get("url") or ""
                if not video_url:
                    record.status = "failed"
                    record.error = f"No video URL in result: {result}"
                else:
                    data = _download(video_url)
                    clip_path = project_dir / "clips" / f"{clip_id}.mp4"
                    clip_path.parent.mkdir(parents=True, exist_ok=True)
                    clip_path.write_bytes(data)
                    record.path = f"clips/{clip_id}.mp4"
                    record.status = "completed"
            # Queued / InProgress -> stays "running"; nothing else to do this poll.
        except Exception as exc:  # noqa: BLE001 -- any fal/network failure surfaces as record.error
            record.status = "failed"
            record.error = str(exc)

    project.save(project_dir)
    return record
