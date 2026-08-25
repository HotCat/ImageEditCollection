#!/usr/bin/env python3
"""Generate one identity-preserving body or head view through HeyRoute.

Generate one view per invocation so an agent can inspect identity before using
the result as a geometry or texture reference. The API key is read only from
HEYROUTE_API_KEY and is never written to the manifest.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path


BODY_VIEWS = {
    "front": "front view, camera azimuth 0 degrees",
    "front-left-045": "front-left three-quarter view, camera azimuth 45 degrees",
    "left-profile-090": "exact left profile, camera azimuth 90 degrees",
    "back-180": "exact back view, camera azimuth 180 degrees",
    "right-profile-270": "exact right profile, camera azimuth 270 degrees",
    "front-right-315": "front-right three-quarter view, camera azimuth 315 degrees",
}

HEAD_VIEWS = {
    "front": "straight-on front head view, camera azimuth 0 degrees",
    "front-left-045": "front-left three-quarter head view, camera azimuth 45 degrees",
    "left-profile-090": "exact left head profile, camera azimuth 90 degrees",
    "back-180": "exact back-of-head view, camera azimuth 180 degrees",
    "right-profile-270": "exact right head profile, camera azimuth 270 degrees",
    "front-right-315": "front-right three-quarter head view, camera azimuth 315 degrees",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=("body", "head"), required=True)
    parser.add_argument("--view", required=True)
    parser.add_argument("--size", help="Defaults to 1536x2048 for body and 1536x1536 for head")
    parser.add_argument("--quality", choices=("low", "medium", "high", "auto"), default="high")
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--base-url", default=os.environ.get("HEYROUTE_BASE_URL", "https://heyroute.ai/v1"))
    parser.add_argument("--extra", default="", help="Additional non-conflicting appearance constraint")
    return parser.parse_args()


def prompt_for(kind: str, view: str, extra: str) -> str:
    views = BODY_VIEWS if kind == "body" else HEAD_VIEWS
    if view not in views:
        raise SystemExit(f"Unknown {kind} view {view!r}; choose one of: {', '.join(views)}")
    invariant = (
        "Edit the supplied character reference; do not invent a different person. Preserve the same "
        "facial identity, age, ethnicity, body proportions, skin tone, hairstyle, hair length and color. "
        "Use a neutral expression, even white studio lighting, a plain mid-gray background, no props, "
        "no text, no crop through anatomy, no perspective exaggeration, and no beauty retouching. "
    )
    if kind == "body":
        task = (
            f"Create a full-body {views[view]}. Keep the identical modest fitted reference outfit and "
            "identical A-pose in every view: standing upright, feet flat and hip-width, arms about 35 degrees "
            "from the torso, elbows straight, palms facing forward. Use an orthographic-like 100 mm studio lens. "
            "Show the complete body from hair to bare or flat-shod feet. "
        )
    else:
        task = (
            f"Create a square high-resolution {views[view]}. Frame the complete cranium, face, ears, hair and "
            "upper neck. Keep the head level and do not change expression, makeup, jaw, nose, eyes or hairstyle. "
            "Use an orthographic-like 135 mm studio lens. "
        )
    return invariant + task + extra.strip()


def multipart(fields: dict[str, str], image: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
            f"{value}\r\n"
        ).encode()
    mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
    body += (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
        f"filename=\"{image.name}\"\r\nContent-Type: {mime}\r\n\r\n"
    ).encode()
    body += image.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def events(response):
    event, lines = None, []
    for raw in response:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if not line:
            if event or lines:
                yield event, "\n".join(lines)
            event, lines = None, []
        elif line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            lines.append(line[6:])
    if event or lines:
        yield event, "\n".join(lines)


def main() -> None:
    args = parse_args()
    key = os.environ.get("HEYROUTE_API_KEY", "").strip()
    if not key:
        raise SystemExit("HEYROUTE_API_KEY is not set; do not pass credentials on the command line")
    if not args.reference.is_file():
        raise SystemExit(f"Reference does not exist: {args.reference}")
    size = args.size or ("1536x2048" if args.kind == "body" else "1536x1536")
    prompt = prompt_for(args.kind, args.view, args.extra)
    fields = {
        "model": args.model,
        "prompt": prompt,
        "n": "1",
        "size": size,
        "quality": args.quality,
        "stream": "true",
    }
    payload, content_type = multipart(fields, args.reference)
    request = urllib.request.Request(args.base_url.rstrip("/") + "/images/edits", data=payload, method="POST")
    request.add_header("Authorization", "Bearer " + key)
    request.add_header("Content-Type", content_type)
    request.add_header("Accept", "text/event-stream")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            for event, data in events(response):
                if event == "heartbeat":
                    print("HeyRoute heartbeat", file=sys.stderr)
                elif event == "error":
                    message = json.loads(data).get("error", {}).get("message", data)
                    raise SystemExit(f"HeyRoute generation failed: {message}")
                elif event == "completed":
                    item = json.loads(data)["data"][0]
                    if item.get("b64_json"):
                        args.output.write_bytes(base64.b64decode(item["b64_json"]))
                    elif item.get("url"):
                        urllib.request.urlretrieve(item["url"], args.output)
                    else:
                        raise SystemExit("HeyRoute completed without image data")
                    manifest = {
                        "reference": str(args.reference.resolve()),
                        "output": str(args.output.resolve()),
                        "kind": args.kind,
                        "view": args.view,
                        "size_requested": size,
                        "model": args.model,
                        "prompt": prompt,
                        "identity_review": "pending",
                    }
                    args.output.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                    print(args.output)
                    return
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:1000]
        raise SystemExit(f"HeyRoute HTTP {error.code}: {detail}") from error
    raise SystemExit("HeyRoute stream ended without a completed image")


if __name__ == "__main__":
    main()
