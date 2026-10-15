"""Twitch batch downloader.

Chunk 4 downloads each saved link in order, using the one quality
chosen for the whole batch.
"""

import shutil
import sys
from pathlib import Path

import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import RerunException, StopException
from streamlit.runtime.scriptrunner_utils.script_requests import ScriptRequestType
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

from downloader import DOWNLOADS, download_one
# Named link_extractor, not extractor: yt-dlp puts its own extractor package
# on sys.path, and that name would hide this file after the first download.
from link_extractor import ExtractionError, extract_twitch_links
from formats import DEFAULT_QUALITY, QUALITIES, quality_by_label


PROJECT_ROOT = Path(__file__).resolve().parent


def ffmpeg_location() -> str | None:
    """Return the FFmpeg executable path, or None when it is not on PATH."""
    return shutil.which("ffmpeg")


def save_folder_error(raw: str) -> str | None:
    """Reject an empty path or any folder inside this project."""
    text = raw.strip()
    if not text:
        return "Enter a folder on this computer. The starting point is the Downloads folder of whoever is logged in."
    try:
        resolved = Path(text).expanduser().resolve()
    except OSError:
        return "That folder path is not valid on this computer."
    if resolved == PROJECT_ROOT or PROJECT_ROOT in resolved.parents:
        return "Pick a folder outside this project. Videos are not stored in the repo."
    return None


def page_is_leaving() -> bool:
    """True after the browser refreshes or closes while a download is still running."""
    ctx = get_script_run_ctx(suppress_warning=True)
    requests = None if ctx is None else ctx.script_requests
    if requests is None:
        return False
    # Pending refresh/stop lives on the script request. Worker threads that
    # report download progress cannot see it through a normal widget call.
    return requests._state in (ScriptRequestType.STOP, ScriptRequestType.RERUN)


def _read_upload(uploaded) -> None:
    """Parse a new file once, and clear the list when the file is removed."""
    if uploaded is None:
        st.session_state.links = []
        st.session_state.source_token = None
        st.session_state.source_name = None
        st.session_state.extract_error = None
        st.session_state.download_rows = []
        return

    token = f"{uploaded.name}:{uploaded.size}"
    if token == st.session_state.source_token:
        return

    if not uploaded.name.lower().endswith(".docx"):
        st.session_state.links = []
        st.session_state.extract_error = (
            "Only .docx files are supported. Save the document as .docx and upload it again."
        )
    else:
        try:
            uploaded.seek(0)
            st.session_state.links = extract_twitch_links(uploaded)
            st.session_state.extract_error = None
        except ExtractionError as exc:
            st.session_state.links = []
            st.session_state.extract_error = str(exc)

        st.session_state.source_token = token
        st.session_state.source_name = uploaded.name
        st.session_state.download_rows = []


def _show_links() -> None:
    """Render the count and the URL list stored in session state."""
    if st.session_state.extract_error:
        st.error(st.session_state.extract_error)
        return

    if st.session_state.source_name is None:
        st.caption("Choose a .docx to scan for Twitch links.")
        return

    links = st.session_state.links
    st.metric("Twitch links", len(links), border=True)
    st.caption(st.session_state.source_name)

    if not links:
        st.info("No Twitch video or clip links were found in this document.")
        return

    st.dataframe(
        {"#": list(range(1, len(links) + 1)), "URL": links},
        hide_index=True,
        width="stretch",
        alt="Twitch links found in the uploaded document",
    )


def _show_quality() -> None:
    """One quality control for the whole list. Nothing is downloaded here."""
    labels = [item.label for item in QUALITIES]
    with st.container(border=True):
        st.subheader("Quality")
        st.segmented_control(
            "Quality for every video",
            labels,
            key="quality",
            required=True,
        )
        chosen = quality_by_label(st.session_state.quality)
        count = len(st.session_state.links)
        video_word = "video" if count == 1 else "videos"
        st.caption(
            f"{chosen.label} applies to all {count} {video_word}. "
            "It is not asked again for each link. "
            f"{chosen.note}"
        )


def _show_download() -> None:
    """Download the stored links one by one. One failure does not stop the rest."""
    ffmpeg = ffmpeg_location()
    with st.container(border=True):
        st.subheader("Download")
        st.text_input(
            "Save folder",
            key="save_folder",
            help="Starts as the Downloads folder of the person using this computer. Not a path inside the project.",
        )
        folder_error = save_folder_error(st.session_state.save_folder)
        if folder_error:
            st.error(folder_error)
        else:
            st.caption(
                "Videos save in that folder, named by video id. "
                "A video that is already there is skipped. "
                "Refresh the page to stop a long video or a live stream. "
                "Download only videos you have the right to keep."
            )
        if not ffmpeg:
            st.warning(
                "FFmpeg is not on PATH, so video and audio cannot be merged into MP4. "
                "Install FFmpeg, restart the terminal, then run the app again."
            )

        if st.session_state.download_rows:
            st.dataframe(
                st.session_state.download_rows,
                hide_index=True,
                width="stretch",
                alt="Status of each video in the last download batch",
            )

        if st.button(
            "Download all",
            type="primary",
            disabled=not ffmpeg or folder_error is not None,
            icon=":material/download:",
        ):
            _run_batch(Path(st.session_state.save_folder).expanduser())


def _run_batch(destination: Path) -> None:
    links = list(st.session_state.links)
    quality = quality_by_label(st.session_state.quality)
    rows = [
        {"#": index + 1, "URL": url, "Status": "waiting", "Detail": ""}
        for index, url in enumerate(links)
    ]
    table = st.empty()
    bar = st.progress(0.0, text="Waiting to start")

    def paint() -> None:
        table.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            alt="Live status for each Twitch link in this batch",
        )

    def finish_quietly() -> None:
        """A refresh stopped the batch. Let Streamlit rerun instead of showing an error."""
        st.session_state.download_rows = rows
        st.empty()

    paint()
    try:
        for index, url in enumerate(links):
            rows[index]["Status"] = "checking"
            paint()
            bar.progress(0.0, text=f"Video {index + 1} of {len(links)}")

            def on_progress(fraction: float | None, label: str, current: int = index) -> None:
                # Refresh does not reach a worker thread through the progress bar,
                # so look at the pending request and stop yt-dlp on purpose.
                if page_is_leaving():
                    raise KeyboardInterrupt
                value = 0.0 if fraction is None else fraction
                try:
                    bar.progress(value, text=f"Video {current + 1} of {len(links)} — {label}")
                except (StopException, RerunException):
                    raise KeyboardInterrupt

            try:
                saved = download_one(url, quality, on_progress, destination)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                rows[index]["Status"] = "failed"
                rows[index]["Detail"] = _short_error(exc)
            else:
                rows[index]["Status"] = "already saved" if saved.already_saved else "done"
                rows[index]["Detail"] = saved.path.name
            paint()
    except KeyboardInterrupt:
        finish_quietly()
        return

    saved_count = sum(1 for row in rows if row["Status"] == "done")
    skipped_count = sum(1 for row in rows if row["Status"] == "already saved")
    failed_count = sum(1 for row in rows if row["Status"] == "failed")
    bar.progress(
        1.0,
        text=(
            f"Finished. {saved_count} saved, "
            f"{skipped_count} already saved, {failed_count} failed."
        ),
    )
    st.session_state.download_rows = rows


def _short_error(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    message = text[-1] if text else exc.__class__.__name__
    return message[:300]


# set_page_config must run before any other Streamlit output.
st.set_page_config(
    page_title="Twitch batch downloader",
    page_icon=":material/video_library:",
    layout="centered",
)

st.title("Twitch batch downloader", icon=":material/video_library:")
st.markdown(
    "Upload a Word document. The page lists every Twitch video and clip URL it finds."
)
st.caption("Pick one quality, then download the whole list in order.")

# These survive a rerun. A normal variable would reset every time you click.
# `quality` is also the segmented control key, so set it before that widget.
st.session_state.setdefault("links", [])
st.session_state.setdefault("source_token", None)
st.session_state.setdefault("source_name", None)
st.session_state.setdefault("extract_error", None)
st.session_state.setdefault("quality", DEFAULT_QUALITY)
st.session_state.setdefault("download_rows", [])
st.session_state.setdefault("save_folder", str(DOWNLOADS))

with st.container(border=True):
    st.subheader("Document")
    uploaded = st.file_uploader(
        "Word document",
        type=["docx"],
        help="Save older .doc files as .docx first. The uploader rejects other types.",
    )
    _read_upload(uploaded)
    _show_links()

if st.session_state.links and not st.session_state.extract_error:
    _show_quality()
    _show_download()

python_version = sys.version.split()[0]
python_ready = sys.version_info >= (3, 10)
ffmpeg_path = ffmpeg_location()

with st.expander("Environment"):
    if python_ready:
        st.badge(
            f"Python {python_version}",
            icon=":material/check:",
            color="green",
        )
    else:
        st.badge(
            f"Python {python_version} is too old",
            icon=":material/error:",
            color="red",
        )
        st.caption("Install Python 3.10 or newer, then recreate the virtual environment.")

    st.badge(
        f"Streamlit {st.__version__}",
        icon=":material/check:",
        color="green",
    )

    if ffmpeg_path:
        st.badge("FFmpeg found", icon=":material/check:", color="green")
        st.caption(ffmpeg_path)
    else:
        st.badge("FFmpeg not found", icon=":material/warning:", color="orange")
        st.caption(
            "Needed on PATH to merge video and audio into one MP4. "
            "The Download button stays off until FFmpeg is found."
        )
