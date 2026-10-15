"""TwitchBatch local server.

Serves the page and downloads one Twitch link at a time.
Run: python server.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from downloader import DOWNLOADS, chunk_command, download_one, pipe_command, timeline_from_info, ts_pipe_command
from formats import DEFAULT_QUALITY, quality_by_label
from link_extractor import ExtractionError, extract_twitch_links, one_twitch_url
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

MAX_UPLOAD = 25 * 1024 * 1024
# Render's disk is ephemeral. Videos are built here, sent to the browser, then deleted.
TEMP_DIR = Path(tempfile.gettempdir()) / "twitchbatch"

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
    WEB = Path(getattr(sys, "_MEIPASS")) / "web"
else:
    ROOT = Path(__file__).resolve().parent
    WEB = ROOT / "web"


class Job:
    def __init__(self) -> None:
        self.cancel = threading.Event()
        self.hold = threading.Event()
        self.hold.set()
        self.lock = threading.Lock()
        self.rows: list[dict] = []
        self.running = False
        self.message = ""
        self.fraction: float | None = None
        self.folder = ""
        self.quality = DEFAULT_QUALITY
        self.streaming = False
        self.proc: subprocess.Popen | None = None
        self.plans: dict[int, tuple[list[str], str, int | None]] = {}


job = Job()
stream_gate = threading.Lock()
# One FFmpeg at a time. A 512 MB instance cannot run two muxes.
ffmpeg_slots = threading.Semaphore(1)
WINDOW_SECONDS = 900
# Render sets RENDER=true. Local exe and `python server.py` stay on this PC.
IS_CLOUD = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID") or os.environ.get("CLOUD_MODE"))
# A short clip can sit in the temp folder long enough for a real faststart MP4.
# A multi-GB VOD cannot. Those stay a MPEG-TS pipe.
CLIP_DISK_MAX_SECONDS = 180
CLIP_DISK_MAX_BYTES = 400 * 1024 * 1024
PLAN_TTL = 6 * 60 * 60
vod_plans: dict[str, dict] = {}


def folder_error(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return "Enter a folder on this computer."
    try:
        resolved = Path(text).expanduser().resolve()
    except OSError:
        return "That folder path is not valid on this computer."
    if resolved == ROOT or ROOT in resolved.parents:
        return "Pick a folder outside this project. Videos are not stored in the repo."
    return None


def job_view() -> dict:
    with job.lock:
        return {
            "running": job.running,
            "paused": not job.hold.is_set(),
            "message": job.message,
            "fraction": job.fraction,
            "streaming": job.streaming,
            "rows": [dict(row) for row in job.rows],
        }


def wait_if_paused() -> None:
    """Block while Pause is on. Refresh still stops the download."""
    while not job.hold.is_set():
        if job.cancel.is_set():
            raise KeyboardInterrupt
        job.hold.wait(0.4)


def _safe_name(video_id: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]", "", video_id)
    return clean or "video"


def _ydl_options(quality_label: str) -> dict:
    """yt-dlp options. The Twitch client id stays the one shipped with yt-dlp.

    The old public web client id is rejected by Twitch now. Retrying does not
    move the GQL call off this machine's IP address.
    """
    return {
        "format": quality_by_label(quality_label).selector,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 5,
        "extractor_retries": 3,
        "socket_timeout": 30,
    }


def _media_info(page: str, quality_label: str) -> dict:
    with YoutubeDL(_ydl_options(quality_label)) as ydl:
        info = ydl.extract_info(page, download=False)
    if not info:
        raise DownloadError("yt-dlp returned no video information.")
    return info


def _public_meta(info: dict) -> dict:
    duration = float(info.get("duration") or 0)
    estimated = info.get("filesize") or info.get("filesize_approx")
    formats = info.get("requested_formats") or []
    if not estimated and formats:
        estimated = sum(item.get("filesize") or item.get("filesize_approx") or 0 for item in formats) or None
    if not estimated and duration:
        estimated = int(duration * 350000)
    return {
        "filename": f"v{_safe_name(str(info.get('id') or 'video'))}.ts",
        "duration": duration,
        "est_bytes": int(estimated or 0),
    }


def _stream_plan(page: str, quality_label: str) -> tuple[list[str], str, int | None]:
    """Resolve media URLs. yt-dlp is told not to download."""
    info = _media_info(page, quality_label)
    meta = _public_meta(info)
    filename = meta["filename"]
    total = meta["est_bytes"] or None
    return pipe_command(info), filename, int(total) if total else None


def clip_fits_temp(url: str, duration: float, est_bytes: int) -> bool:
    """True only for a short Twitch clip that can be built on disk, then deleted."""
    lowered = url.lower()
    if "/clip/" not in lowered and "clips.twitch.tv" not in lowered:
        return False
    if duration > CLIP_DISK_MAX_SECONDS:
        return False
    if est_bytes > CLIP_DISK_MAX_BYTES:
        return False
    return True


def short_error(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    message = text[-1] if text else exc.__class__.__name__
    return message[:300]


def run_batch(urls: list[str], quality_label: str, destination: Path) -> None:
    quality = quality_by_label(quality_label)
    saved = skipped = failed = 0
    try:
        for index, url in enumerate(urls):
            if job.cancel.is_set():
                break
            try:
                wait_if_paused()
            except KeyboardInterrupt:
                break
            with job.lock:
                job.rows[index]["status"] = "downloading"
                job.fraction = None
                job.message = f"Video {index + 1} of {len(urls)}"

            def on_progress(fraction: float | None, label: str, current: int = index) -> None:
                wait_if_paused()
                if job.cancel.is_set():
                    raise KeyboardInterrupt
                with job.lock:
                    job.fraction = None if fraction is None else max(0.0, min(1.0, float(fraction)))
                    job.message = f"Video {current + 1} of {len(urls)} — {label}"

            try:
                result = download_one(url, quality, on_progress, destination)
            except KeyboardInterrupt:
                with job.lock:
                    job.rows[index]["status"] = "stopped"
                    job.rows[index]["detail"] = "Stopped. The partial file can resume."
                break
            except Exception as exc:
                failed += 1
                with job.lock:
                    job.rows[index]["status"] = "failed"
                    job.rows[index]["detail"] = short_error(exc)
            else:
                if result.already_saved:
                    skipped += 1
                    status = "already saved"
                else:
                    saved += 1
                    status = "done"
                with job.lock:
                    job.fraction = 1.0
                    job.rows[index]["status"] = status
                    job.rows[index]["detail"] = result.path.name
                    job.rows[index]["file"] = result.path.name
        with job.lock:
            if job.cancel.is_set():
                job.message = "Stopped. A partial file stays in the save folder and can resume."
            else:
                job.message = f"Finished. {saved} saved, {skipped} already saved, {failed} failed."
    finally:
        with job.lock:
            job.running = False


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._send_file(WEB / "index.html", "text/html; charset=utf-8")
        elif path == "/api/health":
            self._send_json(
                {
                    "ffmpeg": shutil.which("ffmpeg") is not None,
                    "cloud": IS_CLOUD,
                    "folder": "Downloads" if IS_CLOUD else str(DOWNLOADS),
                }
            )
        elif path == "/api/job":
            self._send_json(job_view())
        elif path == "/api/file":
            self._send_download()
        elif path == "/api/stream":
            self._stream()
        elif path == "/api/meta":
            self._meta()
        elif path == "/api/stream_chunk":
            self._stream_chunk()
        elif path == "/api/vod_manifest":
            self._vod_manifest()
        elif path == "/api/segment_window":
            self._segment_window()
        elif path == "/api/cloud_stream":
            self._cloud_stream()
        else:
            self.send_error(404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _cors(self) -> None:
        """Let a page ask this server. File downloads stay same-origin."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Filename")
        self.send_header("Access-Control-Expose-Headers", "X-Video-Filename, X-Duration-Ms, X-Est-Bytes")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/extract":
            self._extract()
        elif path == "/api/download":
            self._start()
        elif path == "/api/open":
            self._open_stream()
        elif path == "/api/fail":
            self._fail_row()
        elif path == "/api/cancel":
            job.cancel.set()
            job.hold.set()
            self._stop_ffmpeg()
            self._send_json({"ok": True})
        elif path == "/api/pause":
            job.hold.clear()
            with job.lock:
                if job.running:
                    job.message = "Paused. Resume to continue this video."
            self._send_json({"ok": True})
        elif path == "/api/resume":
            job.hold.set()
            self._send_json({"ok": True})
        else:
            self.send_error(404)

    def _extract(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD:
            self._send_json({"error": "Upload a .docx under 25 MB."}, 400)
            return
        name = unquote(self.headers.get("X-Filename") or "upload.docx")
        if not name.lower().endswith(".docx"):
            self._send_json(
                {"error": "Only .docx files are supported. Save the document as .docx and upload it again."},
                400,
            )
            return
        raw = self.rfile.read(length)
        try:
            links = extract_twitch_links(BytesIO(raw))
        except ExtractionError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        self._send_json({"links": links})

    def _start(self) -> None:
        if shutil.which("ffmpeg") is None:
            self._send_json(
                {"error": "FFmpeg is not on PATH. Install it, then restart TwitchBatch."},
                400,
            )
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD:
            self._send_json({"error": "The request was empty."}, 400)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "The request was not valid."}, 400)
            return
        urls = payload.get("urls")
        if not isinstance(urls, list) or not urls or not all(isinstance(item, str) for item in urls):
            self._send_json({"error": "Upload a .docx with Twitch links first."}, 400)
            return
        clean = []
        for item in urls:
            page = one_twitch_url(item)
            if not page:
                self._send_json({"error": "Only Twitch video and clip links can be streamed."}, 400)
                return
            clean.append(page)
        if not IS_CLOUD:
            problem = folder_error(str(payload.get("folder") or ""))
            if problem:
                self._send_json({"error": problem}, 400)
                return
            destination = Path(str(payload["folder"])).expanduser().resolve()
            with job.lock:
                if job.running:
                    self._send_json({"error": "A batch is already running."}, 409)
                    return
                job.cancel.clear()
                job.hold.set()
                job.running = True
                job.streaming = False
                job.quality = str(payload.get("quality") or DEFAULT_QUALITY)
                job.folder = str(destination)
                job.message = "Starting…"
                job.fraction = 0
                job.rows = [
                    {"n": index + 1, "url": url, "status": "waiting", "detail": ""}
                    for index, url in enumerate(clean)
                ]
            threading.Thread(
                target=run_batch,
                args=(clean, job.quality, destination),
                daemon=True,
            ).start()
            self._send_json({"ok": True})
            return
        with job.lock:
            if job.streaming:
                self._send_json({"error": "A video is still streaming to your PC."}, 409)
                return
            job.cancel.clear()
            job.hold.set()
            job.running = True
            job.streaming = False
            job.quality = str(payload.get("quality") or DEFAULT_QUALITY)
            job.plans.clear()
            job.folder = "Downloads"
            job.message = "Ready to save on this PC."
            job.fraction = 0
            job.rows = [
                {"n": index + 1, "url": url, "status": "waiting", "detail": "Queued"}
                for index, url in enumerate(clean)
            ]
        self._send_json({"ok": True})

    def _row_url(self, index: int) -> str | None:
        with job.lock:
            if index < 0 or index >= len(job.rows):
                return None
            return str(job.rows[index]["url"])

    def _set_row(self, index: int, **fields) -> None:
        with job.lock:
            if index < 0 or index >= len(job.rows):
                return
            job.rows[index].update(fields)

    def _finish_batch_if_done(self) -> None:
        with job.lock:
            if not job.rows or job.streaming:
                return
            pending = [row for row in job.rows if row["status"] in {"waiting", "downloading"}]
            if pending:
                return
            failed = sum(1 for row in job.rows if row["status"] == "failed")
            saved = sum(1 for row in job.rows if row["status"] == "done")
            job.running = False
            job.fraction = 1
            job.message = f"Finished. {saved} sent to this PC, {failed} failed."

    def _stop_ffmpeg(self) -> None:
        with job.lock:
            proc = job.proc
        if proc is not None and proc.poll() is None:
            proc.kill()

    def _open_stream(self) -> None:
        """Resolve the media URLs. Nothing is written to disk."""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD:
            self._send_json({"error": "The request was empty."}, 400)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            index = int(payload.get("n"))
        except (json.JSONDecodeError, TypeError, ValueError):
            self._send_json({"error": "The request was not valid."}, 400)
            return
        page = self._row_url(index)
        if not page:
            self._send_json({"error": "That video is not in this batch."}, 400)
            return
        if shutil.which("ffmpeg") is None:
            self._send_json({"error": "FFmpeg is not on PATH. Install it, then restart TwitchBatch."}, 400)
            return
        self._set_row(index, status="downloading", detail="Opening the stream…")
        with job.lock:
            job.message = f"Video {index + 1} of {len(job.rows)} — opening"
            job.fraction = None
        try:
            plan = _stream_plan(page, job.quality)
        except Exception as exc:
            self._set_row(index, status="failed", detail=short_error(exc))
            self._finish_batch_if_done()
            self._send_json({"error": short_error(exc)}, 400)
            return
        with job.lock:
            job.plans[index] = plan
        filename = plan[1]
        self._set_row(index, status="downloading", detail="Starting the PC download…")
        self._send_json({"ok": True, "file": filename})

    def _stream(self) -> None:
        """Pipe ffmpeg stdout to the browser. The MP4 is not stored on the server."""
        if not stream_gate.acquire(blocking=False):
            self._send_json({"error": "Another video is still streaming to your PC."}, 409)
            return
        try:
            self._stream_body()
        finally:
            stream_gate.release()

    def _stream_body(self) -> None:
        query = parse_qs(urlsplit(self.path).query)
        index: int | None
        try:
            index = int(query.get("n", [""])[0])
        except ValueError:
            index = None
        with job.lock:
            plan = job.plans.pop(index, None) if index is not None else None
            quality = job.quality
        if plan is None:
            if index is not None:
                page = self._row_url(index)
            else:
                page = one_twitch_url(unquote(query.get("url", [""])[0]))
                quality = unquote(query.get("quality", [DEFAULT_QUALITY])[0])
            if not page:
                self._send_json({"error": "Only a Twitch video or clip link can be streamed."}, 400)
                return
            try:
                plan = _stream_plan(page, quality)
            except Exception as exc:
                if index is not None:
                    self._set_row(index, status="failed", detail=short_error(exc))
                    self._finish_batch_if_done()
                self._send_json({"error": short_error(exc)}, 400)
                return
        command, filename, total = plan
        if index is not None:
            self._set_row(index, status="downloading", detail="Streaming to your PC…")
        self._pipe(index, command, filename, total)

    def _pipe(self, index: int | None, command: list[str], filename: str, total: int | None) -> None:
        if not ffmpeg_slots.acquire(blocking=False):
            self._send_json({"error": "Another video is still streaming."}, 409)
            return
        try:
            self._pipe_locked(index, command, filename, total)
        finally:
            ffmpeg_slots.release()

    def _pipe_locked(self, index: int | None, command: list[str], filename: str, total: int | None) -> None:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            bufsize=0,
        )
        errors: list[str] = []

        def drain() -> None:
            if proc.stderr is None:
                return
            try:
                data = proc.stderr.read()
            except OSError:
                return
            if data:
                errors.append(data.decode("utf-8", "replace")[-400:])

        drainer = threading.Thread(target=drain, daemon=True)
        drainer.start()
        with job.lock:
            job.proc = proc
            job.streaming = True
            job.message = f"Streaming {filename} to this PC"
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        sent = 0
        stopped = False
        try:
            assert proc.stdout is not None
            while True:
                if job.cancel.is_set():
                    stopped = True
                    break
                chunk = proc.stdout.read(64 * 1024)
                if not chunk:
                    break
                sent += len(chunk)
                if index is not None and total:
                    with job.lock:
                        job.fraction = max(0.0, min(0.99, sent / total))
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    stopped = True
                    break
        finally:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            drainer.join(timeout=2)
            with job.lock:
                job.proc = None
                job.streaming = False
            if index is None:
                return
            if sent > 0 and not stopped and not job.cancel.is_set() and proc.returncode in (0, None):
                self._set_row(index, status="done", detail="Saved to PC Downloads")
                with job.lock:
                    job.fraction = 1
            elif stopped or job.cancel.is_set():
                self._set_row(index, status="stopped", detail="Stopped before the file finished.")
            else:
                lines = (errors[0].strip().splitlines() if errors else []) or ["FFmpeg did not send a video."]
                self._set_row(index, status="failed", detail=lines[-1][:300])
            self._finish_batch_if_done()

    def _forget_old_plans(self) -> None:
        now = time.time()
        for token, plan in list(vod_plans.items()):
            if now - plan["created"] > PLAN_TTL:
                del vod_plans[token]

    def _vod_manifest(self) -> None:
        """Count HLS segments. The segment addresses stay on the server."""
        query = parse_qs(urlsplit(self.path).query)
        page = one_twitch_url(unquote(query.get("url", [""])[0]))
        if not page:
            self._send_json({"error": "Only a Twitch video or clip link can be streamed."}, 400)
            return
        quality = unquote(query.get("quality", [DEFAULT_QUALITY])[0])
        try:
            info = _media_info(page, quality)
            segments = timeline_from_info(info)
        except Exception as exc:
            self._send_json({"error": short_error(exc)}, 400)
            return
        self._forget_old_plans()
        token = secrets.token_urlsafe(18)
        meta = _public_meta(info)
        vod_plans[token] = {
            "info": info,
            "segments": segments,
            "filename": meta["filename"],
            "created": time.time(),
        }
        kind = "hls" if len(segments) > 1 else "direct"
        self._send_json(
            {
                "manifest": token,
                "filename": meta["filename"],
                "type": kind,
                "total_segments": len(segments),
            }
        )

    def _segment_window(self) -> None:
        query = parse_qs(urlsplit(self.path).query)
        token = query.get("manifest", [""])[0]
        plan = vod_plans.get(token)
        if not plan:
            self._send_json({"error": "That download session expired. Start it again."}, 400)
            return
        try:
            index = int(query.get("index", ["-1"])[0])
        except ValueError:
            self._send_json({"error": "The segment number is not valid."}, 400)
            return
        segments = plan["segments"]
        if index < 0 or index >= len(segments):
            self._send_json({"error": "That segment is outside this video."}, 400)
            return
        if shutil.which("ffmpeg") is None:
            self._send_json({"error": "FFmpeg is not on PATH. Install it, then restart TwitchBatch."}, 400)
            return
        if not ffmpeg_slots.acquire(blocking=False):
            self._send_json({"error": "Another video is still streaming."}, 409)
            return
        start, length = segments[index]
        try:
            try:
                command = chunk_command(plan["info"], start, length if length > 0 else 4)
            except Exception as exc:
                self._send_json({"error": short_error(exc)}, 400)
                return
            self._write_media(
                command,
                {
                    "Content-Type": "video/mp2t",
                    "Cache-Control": "no-store",
                    "X-Segment": str(index),
                    "X-Total-Segments": str(len(segments)),
                },
            )
        finally:
            ffmpeg_slots.release()

    def _cloud_stream(self) -> None:
        """Send one Twitch video without keeping it.

        A short clip is built as a faststart MP4 in the temp folder, sent, then deleted.
        A long VOD is piped as MPEG-TS. VLC can seek that file. A piped MP4 cannot.
        """
        query = parse_qs(urlsplit(self.path).query)
        page = one_twitch_url(unquote(query.get("url", [""])[0]))
        if not page:
            self._send_json({"error": "Only a Twitch video or clip link can be streamed."}, 400)
            return
        quality = unquote(query.get("quality", [DEFAULT_QUALITY])[0])
        if shutil.which("ffmpeg") is None:
            self._send_json({"error": "FFmpeg is not on PATH. Install it, then restart TwitchBatch."}, 400)
            return
        if not ffmpeg_slots.acquire(blocking=False):
            self._send_json({"error": "Another video is still streaming."}, 409)
            return
        try:
            try:
                info = _media_info(page, quality)
                meta = _public_meta(info)
            except Exception as exc:
                self._send_json({"error": short_error(exc)}, 400)
                return
            duration = float(meta["duration"] or 0)
            if clip_fits_temp(page, duration, int(meta["est_bytes"] or 0)):
                self._send_faststart_clip(page, quality, meta)
                return
            filename = meta["filename"]
            self._write_media(
                ts_pipe_command(info),
                {
                    "Content-Type": "video/mp2t",
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Cache-Control": "no-store",
                    "X-Video-Filename": filename,
                    "X-Duration-Ms": str(int(duration * 1000)),
                    "X-Est-Bytes": str(meta["est_bytes"]),
                    "X-Container": "mpegts",
                },
            )
        finally:
            ffmpeg_slots.release()

    def _send_faststart_clip(self, page: str, quality: str, meta: dict) -> None:
        """Write one short clip with +faststart, send it, then remove the temp folder."""
        work = TEMP_DIR / secrets.token_hex(8)
        work.mkdir(parents=True, exist_ok=True)
        try:
            try:
                result = download_one(page, quality_by_label(quality), lambda *_args: None, work)
            except Exception as exc:
                self._send_json({"error": short_error(exc)}, 400)
                return
            path = result.path
            if not path.is_file() or path.stat().st_size <= 0:
                self._send_json({"error": "The clip finished without a file."}, 400)
                return
            filename = path.name.replace('"', "")
            self._send_file(
                path,
                "video/mp4",
                download_name=filename,
                extra_headers={
                    "Cache-Control": "no-store",
                    "X-Video-Filename": filename,
                    "X-Duration-Ms": str(int(float(meta["duration"] or 0) * 1000)),
                    "X-Est-Bytes": str(path.stat().st_size),
                    "X-Container": "mp4",
                },
            )
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _meta(self) -> None:
        query = parse_qs(urlsplit(self.path).query)
        page = one_twitch_url(unquote(query.get("url", [""])[0]))
        if not page:
            self._send_json({"error": "Only a Twitch video or clip link can be streamed."}, 400)
            return
        quality = unquote(query.get("quality", [DEFAULT_QUALITY])[0])
        try:
            info = _media_info(page, quality)
        except Exception as exc:
            self._send_json({"error": short_error(exc)}, 400)
            return
        self._send_json(_public_meta(info))

    def _stream_chunk(self) -> None:
        """Send one 15-minute MPEG-TS window. The file is not stored here."""
        query = parse_qs(urlsplit(self.path).query)
        page = one_twitch_url(unquote(query.get("url", [""])[0]))
        if not page:
            self._send_json({"error": "Only a Twitch video or clip link can be streamed."}, 400)
            return
        try:
            start = max(0.0, float(query.get("start", ["0"])[0] or 0))
            length = float(query.get("length", [str(WINDOW_SECONDS)])[0] or WINDOW_SECONDS)
        except ValueError:
            self._send_json({"error": "The time window is not valid."}, 400)
            return
        length = min(float(WINDOW_SECONDS), max(1.0, length))
        quality = unquote(query.get("quality", [DEFAULT_QUALITY])[0])
        if shutil.which("ffmpeg") is None:
            self._send_json({"error": "FFmpeg is not on PATH. Install it, then restart TwitchBatch."}, 400)
            return
        if not ffmpeg_slots.acquire(blocking=False):
            self._send_json({"error": "Another video is still streaming."}, 409)
            return
        try:
            try:
                info = _media_info(page, quality)
                command = chunk_command(info, start, length)
                meta = _public_meta(info)
            except Exception as exc:
                self._send_json({"error": short_error(exc)}, 400)
                return
            self._write_media(
                command,
                {
                    "Content-Type": "video/mp2t",
                    "Cache-Control": "no-store",
                    "X-Duration": str(meta["duration"]),
                    "X-Est-Bytes": str(meta["est_bytes"]),
                    "X-Start": f"{start:.3f}",
                },
            )
        finally:
            ffmpeg_slots.release()

    def _write_media(self, command: list[str], headers: dict[str, str]) -> None:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            bufsize=0,
        )
        with job.lock:
            job.proc = proc
            job.streaming = True

        def drain() -> None:
            if proc.stderr is None:
                return
            try:
                proc.stderr.read()
            except OSError:
                return

        threading.Thread(target=drain, daemon=True).start()
        self.close_connection = True
        self.send_response(200)
        self._cors()
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            assert proc.stdout is not None
            while True:
                if job.cancel.is_set():
                    break
                chunk = proc.stdout.read(64 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
        finally:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            with job.lock:
                job.proc = None
                job.streaming = False

    def _fail_row(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            index = int(payload.get("n"))
        except (json.JSONDecodeError, TypeError, ValueError):
            self._send_json({"error": "The request was not valid."}, 400)
            return
        detail = str(payload.get("detail") or "The browser blocked this download.")[:300]
        with job.lock:
            if index < 0 or index >= len(job.rows):
                self._send_json({"error": "That video is not in this batch."}, 400)
                return
            job.rows[index].update({"status": "failed", "detail": detail})
            for row in job.rows[index + 1:]:
                if row["status"] == "waiting":
                    row.update({"status": "stopped", "detail": "Not started."})
            job.running = False
            job.streaming = False
            job.message = detail
        self._send_json({"ok": True})

    def _send_download(self) -> None:
        name = Path(unquote(parse_qs(urlsplit(self.path).query).get("name", [""])[0])).name
        if not name or name in {".", ".."}:
            self.send_error(404)
            return
        with job.lock:
            folder_text = job.folder
        if folder_text and folder_text != "Downloads":
            try:
                root = Path(folder_text).expanduser().resolve()
                target = (root / name).resolve()
            except OSError:
                target = None
            if target is not None and target.parent == root and target.is_file():
                media = "video/mp2t" if target.suffix.lower() == ".ts" else "video/mp4"
                self._send_file(target, media, download_name=name, delete_after=False)
                return
        target = (TEMP_DIR / name).resolve()
        if target.parent != TEMP_DIR.resolve() or not target.is_file():
            self.send_error(404)
            return
        self._send_file(target, "video/mp4", download_name=name, delete_after=True)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(
        self,
        path: Path,
        content_type: str,
        download_name: str | None = None,
        delete_after: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        self.send_response(200)
        if extra_headers:
            self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        sent = True
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(256 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    sent = False
                    break
        if sent and delete_after:
            self._delete_temp(path)

    def _delete_temp(self, path: Path) -> None:
        """Remove the served video only after every byte was written."""
        try:
            resolved = path.resolve()
            if resolved.parent != TEMP_DIR.resolve():
                return
            resolved.unlink(missing_ok=True)
            print(f"Server storage freed: {resolved.name} deleted.")
        except OSError as exc:
            print(f"Error removing file: {exc}")

    def log_message(self, fmt: str, *args) -> None:
        print(f"[TwitchBatch] {self.address_string()} {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TwitchBatch")
    parser.add_argument("--host", default="0.0.0.0" if IS_CLOUD else "127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8787")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    shown_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    page = f"http://{shown_host}:{args.port}"
    print(f"TwitchBatch is at {page}")
    # The exe opens its own page. A public HTTPS site cannot call this HTTP address.
    if getattr(sys, "frozen", False):
        threading.Timer(1.5, lambda: __import__("webbrowser").open_new(page)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
