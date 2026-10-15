"""Read a .docx and return the Twitch video and clip URLs inside it.

Visible text and clickable hyperlink targets are both scanned. A Word
file often shows "watch this" while the real URL lives only in the link.
"""

import re
from urllib.parse import urlsplit, urlunsplit
from zipfile import BadZipFile

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn

# Query strings are ignored on purpose. ?t=2203s and ?sr=a still point at the
# same video, so they must not become a second row.
# /channel/v/123 and /videos/123 are the same VOD written two ways.
_TWITCH_URL = re.compile(
    r"https?://(?:"
    r"(?:www\.|m\.)?twitch\.tv/videos/\d+"
    r"|(?:www\.|m\.)?twitch\.tv/[^/\s<>\"']+/v/\d+"
    r"|(?:www\.|m\.)?twitch\.tv/[^/\s<>\"']+/clip/[A-Za-z0-9_-]+"
    r"|(?:www\.|m\.)?twitch\.tv/clip/[A-Za-z0-9_-]+"
    r"|clips\.twitch\.tv/[A-Za-z0-9_-]+"
    r")",
    re.IGNORECASE,
)
_VOD_ID = re.compile(r"/(?:videos|[^/]+/v)/(\d+)$", re.IGNORECASE)


class ExtractionError(Exception):
    """The upload could not be read as a .docx."""


def extract_twitch_links(source) -> list[str]:
    """Return unique Twitch URLs in the order they first appear.

    `source` is a filesystem path or a readable binary file, such as a
    Streamlit upload.
    """
    document = _open_docx(source)
    found: list[str] = []
    for part in _document_parts(document):
        found.extend(_part_text_and_links(part))
    return _unique(
        _canonical(match.group(0))
        for piece in found
        for match in _TWITCH_URL.finditer(piece)
    )


def _open_docx(source):
    try:
        return Document(source)
    except (PackageNotFoundError, BadZipFile, ValueError) as exc:
        raise ExtractionError(
            "This file is not a readable .docx. Old .doc files need to be "
            "opened in Word and saved as .docx before upload."
        ) from exc


def _document_parts(document):
    """Body, plus headers and footers, without visiting the same part twice."""
    seen: set[int] = set()
    parts = [document.part]
    for section in document.sections:
        for name in (
            "header",
            "footer",
            "first_page_header",
            "first_page_footer",
            "even_page_header",
            "even_page_footer",
        ):
            header_or_footer = getattr(section, name)
            parts.append(header_or_footer.part)

    for part in parts:
        marker = id(part)
        if marker in seen:
            continue
        seen.add(marker)
        yield part


def _part_text_and_links(part) -> list[str]:
    """Walk paragraphs in document order.

    Each paragraph's text runs are joined first. A clickable link is recorded
    where it sits in that paragraph, not dumped at the end of the file.
    """
    pieces_in_order: list[str] = []
    for paragraph in part.element.iter(qn("w:p")):
        text_parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == qn("w:hyperlink"):
                target = _hyperlink_target(part, node)
                if target:
                    pieces_in_order.append(target)
            if node.tag == qn("w:t") and node.text:
                text_parts.append(node.text)
            elif node.tag == qn("w:tab"):
                text_parts.append(" ")
        if text_parts:
            pieces_in_order.append("".join(text_parts))
    return pieces_in_order


def _hyperlink_target(part, node) -> str | None:
    relationship_id = node.get(qn("r:id"))
    if not relationship_id or relationship_id not in part.rels:
        return None
    rel = part.rels[relationship_id]
    if rel.reltype == RT.HYPERLINK and rel.is_external:
        return rel.target_ref
    return None


def _canonical(value: str) -> str | None:
    """Return one clean https URL, or None when the text is not a Twitch link."""
    match = _TWITCH_URL.search(value)
    if match is None:
        return None

    parts = urlsplit(match.group(0))
    host = parts.netloc.lower()
    if host in {"twitch.tv", "www.twitch.tv", "m.twitch.tv"}:
        host = "www.twitch.tv"
    path = parts.path.rstrip("/")
    vod = _VOD_ID.search(path)
    if vod and host == "www.twitch.tv":
        path = f"/videos/{vod.group(1)}"
    return urlunsplit(("https", host, path, "", ""))


def _unique(urls) -> list[str]:
    """Drop empty values and repeats, keeping the first occurrence."""
    ordered: dict[str, None] = {}
    for url in urls:
        if url:
            ordered.setdefault(url, None)
    return list(ordered)
