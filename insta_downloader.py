import argparse
import mimetypes
import pathlib
import sys
from typing import Optional
from urllib.parse import urlparse

import requests


INSTAGRAM_REFERER = "https://www.instagram.com/"

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Referer": INSTAGRAM_REFERER,
    "Origin": "https://www.instagram.com",
    "Accept-Language": "en-US,en;q=0.9",
}

VIDEO_HEADERS = {
    **COMMON_HEADERS,
    "Accept": "*/*",
    "Accept-Encoding": "identity",
    "Range": "bytes=0-",
}

IMAGE_HEADERS = {
    **COMMON_HEADERS,
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}

CONTENT_TYPE_EXTENSIONS = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

MEDIA_EXTENSIONS = (
    ".mp4",
    ".webm",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
)


def is_instagram_page_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host in {"instagram.com", "www.instagram.com"}


def guess_media_kind(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith((".mp4", ".webm")) or "/o1/" in path:
        return "video"
    if path.endswith((".jpg", ".jpeg", ".png", ".webp")) or "/v/t51" in path:
        return "image"
    return "media"


def headers_for_url(url: str) -> dict:
    kind = guess_media_kind(url)
    if kind == "video":
        return dict(VIDEO_HEADERS)
    if kind == "image":
        return dict(IMAGE_HEADERS)
    return {**COMMON_HEADERS, "Accept": "*/*"}


def extension_from_response(url: str, response: requests.Response) -> str:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type in CONTENT_TYPE_EXTENSIONS:
        return CONTENT_TYPE_EXTENSIONS[content_type]

    guessed = mimetypes.guess_extension(content_type) if content_type else None
    if guessed:
        return guessed

    suffix = pathlib.Path(urlparse(url).path).suffix.lower()
    if suffix in MEDIA_EXTENSIONS:
        return suffix

    return ".bin"


def unique_path(path: pathlib.Path) -> pathlib.Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1

    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def resolve_output_path(url: str, output: Optional[str], response: requests.Response) -> pathlib.Path:
    if output:
        output_path = pathlib.Path(output)
        if output_path.suffix:
            return output_path
        return output_path.with_suffix(extension_from_response(url, response))

    ext = extension_from_response(url, response)
    return unique_path(pathlib.Path(f"instagram_media{ext}"))


def download_direct_cdn(url: str, output: Optional[str] = None, headers: Optional[dict] = None, debug: bool = False) -> pathlib.Path:
    """Download a direct Instagram CDN media URL to disk."""
    request_headers = headers_for_url(url)
    if headers:
        request_headers.update(headers)

    if debug:
        parsed = urlparse(url)
        print(f"Host: {parsed.hostname}")
        print(f"Detected kind: {guess_media_kind(url)}")

    with requests.get(url, headers=request_headers, stream=True, timeout=60) as response:
        content_type = response.headers.get("content-type", "unknown")

        if debug:
            print(f"HTTP status: {response.status_code}")
            print(f"Content-Type: {content_type}")
            print(f"Content-Length: {response.headers.get('content-length', 'unknown')}")

        if response.status_code not in (200, 206):
            raise RuntimeError(
                f"Download failed: HTTP {response.status_code}\n"
                f"Content-Type: {content_type}\n"
                f"Response: {response.text[:500]}"
            )

        if not (content_type.startswith("video/") or content_type.startswith("image/") or content_type == "application/octet-stream"):
            raise RuntimeError(
                f"Unsupported response content-type: {content_type}. "
                "This looks like a page URL, so use the normal command again after installing yt-dlp."
            )

        output_path = resolve_output_path(url, output, response)
        total = int(response.headers.get("content-length", 0))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        downloaded = 0
        with output_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue

                file.write(chunk)
                downloaded += len(chunk)

                if total:
                    percent = downloaded * 100 / total
                    print(f"\rDownloading... {percent:.1f}%", end="")
                else:
                    print(f"\rDownloaded {downloaded / 1024 / 1024:.2f} MB", end="")

    print(f"\nSaved to: {output_path}")
    return output_path


def download_instagram_page(url: str, output: Optional[str] = None) -> None:
    import yt_dlp

    output_path = pathlib.Path(output or "%(title).80s.%(ext)s")

    ydl_opts = {
        "outtmpl": str(output_path),
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": False,
        "quiet": False,
        "no_warnings": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def download(url: str, output: Optional[str] = None, debug: bool = False) -> None:
    if is_instagram_page_url(url):
        download_instagram_page(url, output)
    else:
        download_direct_cdn(url, output, debug=debug)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Instagram media from a share URL or direct CDN media URL."
    )
    parser.add_argument("url", help="Instagram share URL or direct CDN media URL")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output filename. Example: video.mp4. If omitted, filename is auto-generated.",
    )
    parser.add_argument("--debug", action="store_true", help="Show request diagnostics for direct CDN URLs")

    args = parser.parse_args()

    try:
        download(args.url, args.output, debug=args.debug)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
