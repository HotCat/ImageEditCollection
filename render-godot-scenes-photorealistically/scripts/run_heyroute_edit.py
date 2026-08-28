#!/usr/bin/env python3
"""Run one ordered HeyRoute gpt-image-2 edit request and save its SSE result."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
import uuid


DEFAULT_BASE_URL = "https://heyroute.ai/v1"
DEFAULT_MODEL = "gpt-image-2"
MAX_INPUT_BYTES = 30 * 1024 * 1024


def sse_events(response):
    event = None
    data_lines: list[str] = []
    for raw_line in response:
        line = raw_line.decode("utf-8", "replace").rstrip("\r\n")
        if not line:
            if event is not None or data_lines:
                yield event, "\n".join(data_lines)
            event = None
            data_lines = []
        elif line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data_lines.append(line[6:])
    if event is not None or data_lines:
        yield event, "\n".join(data_lines)


def build_multipart(fields: dict[str, str], images: list[Path]) -> tuple[bytes, str]:
    boundary = "----GodotPhotoreal" + uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")
    for index, image in enumerate(images):
        content_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image[{index}]"; '
            f'filename="{image.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        body += image.read_bytes()
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def error_message(payload: str) -> str:
    try:
        parsed = json.loads(payload)
        return str(parsed.get("error", {}).get("message") or parsed.get("message") or payload)
    except json.JSONDecodeError:
        return payload[:1000]


def read_result(response, output: Path) -> None:
    for event, data in sse_events(response):
        if event == "started":
            print("Generation started", file=sys.stderr)
        elif event == "heartbeat":
            print("Generation heartbeat", file=sys.stderr)
        elif event == "error":
            raise RuntimeError("HeyRoute generation failed: " + error_message(data))
        elif event == "completed":
            parsed = json.loads(data)
            item = parsed["data"][0]
            output.parent.mkdir(parents=True, exist_ok=True)
            if item.get("b64_json"):
                output.write_bytes(base64.b64decode(item["b64_json"]))
            elif item.get("url"):
                request = urllib.request.Request(
                    str(item["url"]), headers={"User-Agent": "godot-photoreal-skill/1.0"}
                )
                with urllib.request.urlopen(request, timeout=300) as download_response:
                    output.write_bytes(download_response.read())
            else:
                raise RuntimeError("completed event contained no image data")
            if not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError("HeyRoute returned an empty output")
            print(f"Saved: {output}")
            return
    raise RuntimeError("SSE stream ended without completed or error event")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    prompt_source = parser.add_mutually_exclusive_group(required=True)
    prompt_source.add_argument("--prompt")
    prompt_source.add_argument("--prompt-file")
    parser.add_argument("--image", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", default="3840x2160")
    parser.add_argument("--quality", choices=["low", "medium", "high", "auto"], default="high")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=os.environ.get("HEYROUTE_BASE_URL", DEFAULT_BASE_URL))
    args = parser.parse_args()

    key = os.environ.get("HEYROUTE_API_KEY", "").strip()
    if not key:
        sys.exit("HEYROUTE_API_KEY is not set")
    prompt = (
        Path(args.prompt_file).expanduser().resolve().read_text(encoding="utf-8")
        if args.prompt_file
        else args.prompt
    )
    if not prompt.strip():
        sys.exit("prompt is empty")

    images = [Path(value).expanduser().resolve() for value in args.image]
    for image in images:
        if not image.is_file() or image.stat().st_size == 0:
            sys.exit(f"missing or empty input image: {image}")
    total_input_bytes = sum(image.stat().st_size for image in images)
    if total_input_bytes >= MAX_INPUT_BYTES:
        sys.exit(
            f"input images total {total_input_bytes / 1024 / 1024:.2f} MiB; "
            "compact appearance references below 30 MiB before submitting"
        )

    fields = {
        "model": args.model,
        "prompt": prompt,
        "n": "1",
        "size": args.size,
        "quality": args.quality,
        "stream": "true",
    }
    body, content_type = build_multipart(fields, images)
    endpoint = args.base_url.rstrip("/") + "/images/edits"
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": content_type,
            "Accept": "text/event-stream",
            "User-Agent": "godot-photoreal-skill/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            read_result(response, Path(args.output).expanduser().resolve())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        sys.exit(f"HeyRoute HTTP {exc.code}: {error_message(detail)}")
    except urllib.error.URLError as exc:
        sys.exit(f"HeyRoute network error: {exc.reason}")
    except (RuntimeError, KeyError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
