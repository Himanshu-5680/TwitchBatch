"""Download one Twitch URL at a time with yt-dlp.

The page owns the progress bar. This module only downloads and reports
a fraction from 0 to 1, or None when the file size is still unknown.
"""

import shutil
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from formats import MERGE_FORMAT, Quality

ProgressHook = Callable[[float | None, str], None]

# Whoever runs the app. Not a path typed for one person, and not the repo.
DOWNLOADS = Path.home() / "Downloads"


class FFmpegMissingError(Exception):
    """Video and audio cannot be merged into MP4 without FFmpeg."""


@dataclass(frozen=True)
class DownloadResult:
    """A finished MP4, either just saved or already on disk."""

    path: Path
    already_saved: bool = False


def _human_size(amount: float | None) -> str:
    if not amount:
        return ""
    value = float(amount)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return ""


def _progress_label(update: dict) -> str:
    """One line a person can read: percent, size, speed, and time left."""
    parts: list[str] = ["Downloading"]
    fraction = progress_fraction(update)
    if fraction is not None:
        parts.append(f"{round(fraction * 100)}%")
    got = _human_size(update.get("downloaded_bytes"))
    total = _human_size(update.get("total_bytes") or update.get("total_bytes_estimate"))
    if got and total:
        parts.append(f"{got} of {total}")
    elif got:
        parts.append(got)
    speed = update.get("speed")
    if speed:
        parts.append(f"{_human_size(speed)}/s")
    eta = update.get("eta")
    if isinstance(eta, (int, float)) and eta >= 0:
        minutes, seconds = divmod(int(eta), 60)
        parts.append(f"{minutes}m {seconds}s left" if minutes else f"{seconds}s left")
    return " · ".join(parts)


def progress_fraction(update: dict) -> float | None:
    """Turn a yt-dlp progress event into a 0..1 fraction."""
    downloaded = update.get("downloaded_bytes") or 0
    total = update.get("total_bytes") or update.get("total_bytes_estimate")
    if not total:
        return None
    return max(0.0, min(1.0, downloaded / total))


def completed_file(video_id: str, destination: Path) -> Path | None:
    """Return the finished MP4 for this id, or None if it still needs a download.

    A `.part` or `.ytdl` file means the last attempt stopped in the middle.
    That video is not treated as saved, so the next run can resume it.
    """
    if not video_id:
        return None
    candidate = destination / f"{video_id}.mp4"
    if not candidate.is_file() or candidate.stat().st_size <= 0:
        return None
    leftovers = [
        *destination.glob(f"{video_id}*.part"),
        *destination.glob(f"{video_id}*.ytdl"),
    ]
    if leftovers:
        return None
    return candidate


def download_one(
    url: str,
    quality: Quality,
    on_progress: ProgressHook,
    destination: Path = DOWNLOADS,
) -> DownloadResult:
    """Download `url` and return the saved file.

    If that video's MP4 is already in `destination`, it is not downloaded again.
    Raises DownloadError when yt-dlp rejects the link, and
    FFmpegMissingError when the merger is not installed.
    KeyboardInterrupt is left alone so a refresh can stop a long download.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegMissingError(
            "FFmpeg is not on PATH. Install it, then restart the terminal and the app."
        )

    destination.mkdir(parents=True, exist_ok=True)
    saved: dict[str, str] = {}

    def hook(update: dict) -> None:
        try:
            status = update.get("status")
            if status == "downloading":
                on_progress(progress_fraction(update), _progress_label(update))
            elif status == "finished":
                filename = update.get("filename")
                if filename:
                    saved["path"] = filename
                on_progress(1.0, "Merging into MP4")
        except Exception:
            # A progress-bar glitch must not cancel the file itself.
            # KeyboardInterrupt and Streamlit's stop signal are not Exception,
            # so a refresh still aborts the download.
            return

    options = {
        "format": quality.selector,
        "merge_output_format": MERGE_FORMAT,
        "outtmpl": str(destination / "%(id)s.%(ext)s"),
        "restrictfilenames": True,
        "windowsfilenames": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "continuedl": True,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 30,
        "ffmpeg_location": str(Path(ffmpeg).parent),
        "progress_hooks": [hook],
        # A second pass puts the movie header at the start, so players can seek.
        "postprocessor_args": {"ffmpeg": ["-movflags", "+faststart"]},
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise DownloadError("yt-dlp returned no video information.")
        video_id = str(info.get("id") or "")
        existing = completed_file(video_id, destination)
        if existing is not None:
            return DownloadResult(existing, already_saved=True)
        if info.get("is_live"):
            on_progress(None, "Live stream")
        ydl.process_info(info)

    path = _finished_file(info, saved.get("path"), destination)
    if path is None:
        raise DownloadError("yt-dlp finished without writing a file.")
    return DownloadResult(path)


def _ffmpeg_headers(headers: dict) -> str:
    lines = []
    for key, value in headers.items():
        key_text = str(key)
        value_text = str(value)
        if not key_text or any(char in key_text or char in value_text for char in "\r\n"):
            continue
        lines.append(f"{key_text}: {value_text}")
    if not lines:
        return ""
    return "\r\n".join(lines) + "\r\n"


def parse_playlist(text: str, base: str) -> tuple[str | None, list[tuple[float, float]]]:
    """Read one HLS playlist.

    A master playlist returns the chosen variant URL and no segments.
    A media playlist returns each segment's start time and duration.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if any(line.startswith("#EXT-X-STREAM-INF") for line in lines):
        chosen = ""
        for index, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF") and index + 1 < len(lines):
                chosen = lines[index + 1]
        if not chosen or chosen.startswith("#"):
            raise DownloadError("The playlist has no media stream.")
        return (chosen if chosen.startswith("http") else base + chosen), []

    segments: list[tuple[float, float]] = []
    clock = 0.0
    pending: float | None = None
    for line in lines:
        if line.startswith("#EXTINF:"):
            raw = line.split(":", 1)[1].split(",", 1)[0]
            try:
                pending = float(raw)
            except ValueError:
                pending = 4.0
        elif not line.startswith("#") and pending is not None:
            segments.append((clock, pending))
            clock += pending
            pending = None
    if not segments:
        raise DownloadError("The playlist has no segments.")
    return None, segments


def _fetch_text(url: str, headers: dict) -> str:
    clean = {
        str(key): str(value)
        for key, value in headers.items()
        if str(key) and "\r" not in str(key) and "\n" not in str(key) + str(value)
    }
    clean.setdefault("User-Agent", "Mozilla/5.0")
    request = urllib.request.Request(url, headers=clean)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "replace")


def timeline_from_info(info: dict) -> list[tuple[float, float]]:
    """Segment start times for an exact progress count. Falls back to 15-minute blocks."""
    formats = info.get("requested_formats") or []
    source = formats[0] if formats else info
    media = str(source.get("url") or "")
    headers = source.get("http_headers") or info.get("http_headers") or {}
    protocol = str(source.get("protocol") or info.get("protocol") or "")
    if "m3u8" in media or "m3u8" in protocol:
        url = media
        for _ in range(4):
            base = url.rsplit("/", 1)[0] + "/"
            variant, segments = parse_playlist(_fetch_text(url, headers), base)
            if variant is None:
                return segments
            url = variant
    duration = float(info.get("duration") or 0)
    if duration <= 0:
        return [(0.0, 900.0)]
    blocks: list[tuple[float, float]] = []
    cursor = 0.0
    while cursor < duration:
        span = min(900.0, duration - cursor)
        blocks.append((cursor, span))
        cursor += span
    return blocks


def chunk_command(info: dict, start: float, length: float) -> list[str]:
    """Mux one time window to stdout as MPEG-TS.

    MPEG-TS can be appended on disk. A second fragmented MP4 cannot.
    `-c copy` does not re-encode, so a 15-minute window stays a short transfer.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegMissingError(
            "FFmpeg is not on PATH. Install it, then restart TwitchBatch."
        )
    formats = info.get("requested_formats") or []
    inputs = formats[:2] if len(formats) >= 2 else [info]
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
    ]
    for fmt in inputs:
        media = fmt.get("url")
        if not media:
            raise DownloadError("yt-dlp did not return a stream URL.")
        if start > 0:
            command.extend(["-ss", f"{start:.3f}"])
        if length > 0:
            command.extend(["-t", f"{length:.3f}"])
        blob = _ffmpeg_headers(fmt.get("http_headers") or info.get("http_headers") or {})
        if blob:
            command.extend(["-headers", blob])
        command.extend(["-i", media])
    command.extend(["-c", "copy", "-f", "mpegts", "pipe:1"])
    return command


def ts_pipe_command(info: dict) -> list[str]:
    """Stream the whole file as MPEG-TS.

    A piped MP4 has no finished moov index, so players cannot seek it.
    MPEG-TS carries timestamps in the stream, and VLC can seek the saved .ts file.
    """
    return chunk_command(info, 0, 0)


def ts_pipe_command(info: dict) -> list[str]:
    """Mux a whole video to stdout as MPEG-TS. Nothing is written on this machine.

    A piped MP4 has no sample index, so players cannot seek it. MPEG-TS carries
    timestamps in the stream itself, which is why VLC can seek the saved .ts file.
    """
    return chunk_command(info, 0, 0)


def pipe_command(info: dict) -> list[str]:
    """Build an ffmpeg command that muxes to stdout and does not write an MP4.

    `-c copy` keeps Twitch's H.264 and AAC as they are. The frag flags let the
    browser play the file while it is still arriving.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegMissingError(
            "FFmpeg is not on PATH. Install it, then restart TwitchBatch."
        )
    formats = info.get("requested_formats") or []
    inputs = formats[:2] if len(formats) >= 2 else [info]
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    for fmt in inputs:
        media = fmt.get("url")
        if not media:
            raise DownloadError("yt-dlp did not return a stream URL.")
        blob = _ffmpeg_headers(fmt.get("http_headers") or info.get("http_headers") or {})
        command.extend(["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"])
        if blob:
            command.extend(["-headers", blob])
        command.extend(["-i", media])
    command.extend(
        [
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "-f", "mp4",
            "pipe:1",
        ]
    )
    return command


def _located(filepath: str, destination: Path) -> Path:
    path = Path(filepath)
    if path.is_absolute() or path.exists():
        return path
    return destination / path


def _finished_file(info: dict | None, hook_path: str | None, destination: Path) -> Path | None:
    """Prefer the merged MP4 over a temporary video-only file."""
    candidates: list[Path] = []
    if info:
        for item in info.get("requested_downloads") or []:
            filepath = item.get("filepath")
            if filepath:
                candidates.append(_located(filepath, destination))
    if hook_path:
        candidates.append(_located(hook_path, destination))

    mp4_files = [
        path
        for path in candidates
        if path.suffix.lower() == ".mp4" and path.exists() and ".f" not in path.stem
    ]
    if mp4_files:
        return mp4_files[-1]

    existing = [path for path in candidates if path.exists()]
    return existing[-1] if existing else None
