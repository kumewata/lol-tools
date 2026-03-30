"""YouTube subtitle and storyboard fetcher using yt-dlp."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from PIL import Image

from lol_vod_analyzer.models import TranscriptSegment, VideoSource

_ALLOWED_SCHEMES = {"https", "http"}
_ALLOWED_HOST_SUFFIXES = (
    ".googlevideo.com", ".youtube.com", ".ytimg.com",
    ".google.com", ".googleapis.com",
)
_MAX_RESPONSE_BYTES = 50 * 1024 * 1024  # 50 MB


def _validate_url(url: str) -> None:
    """Validate URL scheme and hostname to prevent SSRF."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"Disallowed URL scheme: {parsed.scheme}")
    hostname = parsed.hostname or ""
    if not any(hostname.endswith(suffix) for suffix in _ALLOWED_HOST_SUFFIXES):
        raise ValueError(f"Disallowed host: {hostname}")


def _safe_read(resp: urllib.request.addinfourl, max_bytes: int = _MAX_RESPONSE_BYTES) -> bytes:
    """Read response with a size limit."""
    data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"Response exceeded maximum allowed size ({max_bytes} bytes)")
    return data


def fetch_video_metadata(
    url: str, use_cookies: bool = True
) -> tuple[VideoSource, dict]:
    ydl_opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignore_no_formats_error": True,
    }
    if use_cookies:
        ydl_opts["cookiesfrombrowser"] = ("chrome",)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    source = VideoSource(
        url=url,
        title=info["title"],
        duration=info["duration"],
        source_type="youtube",
    )
    return source, info


def parse_caption_events(caption_data: dict) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    events = caption_data.get("events", [])

    for event in events:
        segs = event.get("segs", [])
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text:
            continue

        start_ms = event.get("tStartMs", 0)
        duration_ms = event.get("dDurationMs", 0)
        end_ms = start_ms + duration_ms

        segments.append(
            TranscriptSegment(start_ms=start_ms, end_ms=end_ms, text=text)
        )
    return segments


def fetch_transcript(info: dict, lang: str = "ja") -> list[TranscriptSegment]:
    auto_captions = info.get("automatic_captions", {})
    lang_captions = auto_captions.get(lang, [])
    json3_cap = next((c for c in lang_captions if c["ext"] == "json3"), None)

    if json3_cap is None:
        return []

    for attempt in range(3):
        try:
            caption_url = json3_cap["url"]
            _validate_url(caption_url)
            req = urllib.request.Request(caption_url)
            with urllib.request.urlopen(req) as resp:
                caption_data = json.loads(_safe_read(resp))
            return parse_caption_events(caption_data)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def download_video(url: str, output_dir: Path) -> Path | None:
    """Download YouTube video as 360p mp4 using android client.

    Returns the path to the downloaded file, or None if download fails.
    """
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    outtmpl = str(output_dir / "%(id)s.%(ext)s")

    ydl_opts: dict = {
        "format": "18",  # 360p pre-muxed mp4
        "outtmpl": outtmpl,
        "quiet": True,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return Path(filename)
    except Exception:
        return None


def find_storyboard_format(formats: list[dict]) -> dict | None:
    sb_formats = [
        f for f in formats if f.get("format_id", "").startswith("sb")
    ]
    if not sb_formats:
        return None
    sb_formats.sort(key=lambda f: f.get("format_id", ""), reverse=False)
    return sb_formats[0]


def download_storyboard_sprites(
    sb_format: dict, output_dir: Path
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fragments = sb_format.get("fragments", [])
    columns = sb_format.get("columns", 5)
    rows = sb_format.get("rows", 5)

    frame_paths: list[Path] = []
    frame_index = 0

    for frag in fragments:
        url = frag.get("url")
        if not url:
            continue

        _validate_url(url)
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            sprite_data = _safe_read(resp)

        sprite_img = Image.open(BytesIO(sprite_data))
        sprite_w, sprite_h = sprite_img.size
        tile_w = sprite_w // columns
        tile_h = sprite_h // rows

        for row in range(rows):
            for col in range(columns):
                left = col * tile_w
                top = row * tile_h
                right = left + tile_w
                bottom = top + tile_h

                tile = sprite_img.crop((left, top, right, bottom))

                if _is_blank_tile(tile):
                    continue

                frame_path = output_dir / f"frame_{frame_index:04d}.jpg"
                tile.save(frame_path, "JPEG", quality=85)
                frame_paths.append(frame_path)
                frame_index += 1

    return frame_paths


def _is_blank_tile(img: Image.Image, threshold: int = 10) -> bool:
    grayscale = img.convert("L")
    pixels = list(grayscale.getdata())
    avg = sum(pixels) / len(pixels) if pixels else 0
    return avg < threshold
