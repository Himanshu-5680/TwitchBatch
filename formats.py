"""Quality choices for the whole batch.

The label is what the page shows. The selector is the yt-dlp format
string Chunk 4 will pass through unchanged. A height ceiling means
"this quality or the closest one below it", so a 720p-only video still
downloads when 1080p is selected.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Quality:
    label: str
    selector: str
    note: str


MERGE_FORMAT = "mp4"
DEFAULT_QUALITY = "1080p MP4"

QUALITIES: tuple[Quality, ...] = (
    Quality(
        label="1080p MP4",
        selector="bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        note="Up to 1080p. A video without 1080p uses the closest lower quality.",
    ),
    Quality(
        label="720p MP4",
        selector="bestvideo[height<=720]+bestaudio/best[height<=720]",
        note="Up to 720p. Smaller than 1080p, and still sharp on a laptop.",
    ),
    Quality(
        label="480p MP4",
        selector="bestvideo[height<=480]+bestaudio/best[height<=480]",
        note="Up to 480p. The smallest of the three files.",
    ),
)


def quality_by_label(label: str) -> Quality:
    """Return the matching quality, or the default when the label is unknown."""
    for item in QUALITIES:
        if item.label == label:
            return item
    return QUALITIES[0]
