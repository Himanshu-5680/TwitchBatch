"""TwitchBatch local server.

Serves the page and downloads one Twitch link at a time.
Run: python server.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from downloader import DOWNLOADS, download_one
from formats import quality_by_label
from link_extractor import ExtractionError, extract_twitch_links

MAX_UPLOAD = 25 * 1024 * 1024

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


job = Job()


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
            "rows": [dict(row) for row in job.rows],
        }


def wait_if_paused() -> None:
    """Block while Pause is on. Refresh still stops the download."""
    while not job.hold.is_set():
        if job.cancel.is_set():
            raise KeyboardInterrupt
        job.hold.wait(0.4)


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
                    "folder": str(DOWNLOADS),
                }
            )
        elif path == "/api/job":
            self._send_json(job_view())
        elif path == "/api/file":
            self._send_download()
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/extract":
            self._extract()
        elif path == "/api/download":
            self._start()
        elif path == "/api/cancel":
            job.cancel.set()
            job.hold.set()
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
            job.folder = str(destination)
            job.message = "Starting…"
            job.rows = [
                {"n": index + 1, "url": url, "status": "waiting", "detail": ""}
                for index, url in enumerate(urls)
            ]
        threading.Thread(
            target=run_batch,
            args=(list(urls), str(payload.get("quality") or "1080p MP4"), destination),
            daemon=True,
        ).start()
        self._send_json({"ok": True})

    def _send_download(self) -> None:
        name = Path(unquote(parse_qs(urlsplit(self.path).query).get("name", [""])[0])).name
        with job.lock:
            folder = job.folder
        if not name or not folder:
            self.send_error(404)
            return
        target = (Path(folder) / name).resolve()
        if target.parent != Path(folder).resolve() or not target.is_file():
            self.send_error(404)
            return
        self._send_file(target, "video/mp4", download_name=name)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, path: Path, content_type: str, download_name: str | None = None) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(256 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break

    def log_message(self, fmt: str, *args) -> None:
        print(f"[TwitchBatch] {self.address_string()} {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TwitchBatch")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    shown_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    page = f"http://{shown_host}:{args.port}"
    print(f"TwitchBatch is at {page}")
    if getattr(sys, "frozen", False):
        threading.Timer(0.8, lambda: __import__("webbrowser").open(page)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
