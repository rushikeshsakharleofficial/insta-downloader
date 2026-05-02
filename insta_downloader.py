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

SUPPORTED_HOST_SUFFIXES = (
    ".fbcdn.net",
    ".cdninstagram.com",
)

CONTENT_TYPE_EXTENSIONS = {
    "video/mp4": ".mp4",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def is_instagram_cdn_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host == "cdninstagram.com" or host.endswith(SUPPORTED_HOST_SUFFIXES)


def guess_media_kind(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".mp4"):
        return "video"
    if path.endswith((".jpg", ".jpeg", ".png", ".webp")):
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

    suffix = pathlib.Path(urlparse(url).path).suffix
    return suffix or ".bin"


def resolve_output_path(url: str, output: Optional[str], response: requests.Response) -> pathlib.Path:
    if output:
        return pathlib.Path(output)

    ext = extension_from_response(url, response)
    return pathlib.Path(f"instagram_media{ext}")


def download_file(url: str, output: Optional[str] = None, headers: Optional[dict] = None) -> pathlib.Path:
    """Download a direct Instagram CDN media URL to disk."""
    if not is_instagram_cdn_url(url):
        raise ValueError("URL does not look like a common Instagram CDN URL")

    request_headers = headers_for_url(url)
    if headers:
        request_headers.update(headers)

    with requests.get(url, headers=request_headers, stream=True, timeout=60) as response:
        if response.status_code not in (200, 206):
            raise RuntimeError(
                f"Download failed: HTTP {response.status_code}\n"
                f"Response: {response.text[:500]}"
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download a direct Instagram CDN media URL, including videos and images."
    )
    parser.add_argument("url", help="Direct Instagram CDN media URL")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output filename. If omitted, extension is detected from response content-type.",
    )

    args = parser.parse_args()

    try:
        download_file(args.url, args.output)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
