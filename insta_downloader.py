import argparse
import pathlib
import sys
from typing import Optional

import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Referer": "https://www.instagram.com/",
    "Accept": "*/*",
    "Accept-Encoding": "identity",
    "Range": "bytes=0-",
}


def download_file(url: str, output: pathlib.Path, headers: Optional[dict] = None) -> None:
    """Download a direct Instagram CDN media URL to disk."""
    request_headers = dict(DEFAULT_HEADERS)
    if headers:
        request_headers.update(headers)

    with requests.get(url, headers=request_headers, stream=True, timeout=60) as response:
        if response.status_code not in (200, 206):
            raise RuntimeError(
                f"Download failed: HTTP {response.status_code}\n"
                f"Response: {response.text[:500]}"
            )

        total = int(response.headers.get("content-length", 0))
        output.parent.mkdir(parents=True, exist_ok=True)

        downloaded = 0
        with output.open("wb") as file:
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

    print(f"\nSaved to: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download an Instagram direct CDN .mp4 URL."
    )
    parser.add_argument("url", help="Direct Instagram CDN video URL")
    parser.add_argument(
        "-o",
        "--output",
        default="video.mp4",
        help="Output filename, default: video.mp4",
    )

    args = parser.parse_args()

    try:
        download_file(args.url, pathlib.Path(args.output))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
