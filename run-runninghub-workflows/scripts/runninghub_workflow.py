#!/usr/bin/env python3
"""Inspect and run RunningHub ComfyUI workflows without browser automation."""

from __future__ import annotations

import argparse
import getpass
import json
import mimetypes
import os
from pathlib import Path
import re
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid


# Prefer the host OS trust store when available. Some Conda Python builds carry
# a relocated OpenSSL path that cannot validate certificates Safari and curl
# already trust, which otherwise breaks every RunningHub request before auth.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass


TERMINAL_FAILURES = {"FAILED", "ERROR", "CANCELED", "CANCELLED"}


class RunningHubError(RuntimeError):
    pass


def api_key(prompt: bool) -> str:
    value = os.environ.get("RUNNINGHUB_API_KEY", "").strip()
    if not value and prompt and sys.stdin.isatty():
        value = getpass.getpass("RunningHub API key: ").strip()
    if not value:
        raise RunningHubError(
            "RUNNINGHUB_API_KEY is not set; provide it through the environment "
            "or use --prompt-key in an interactive terminal"
        )
    return value


def request_json(
    base_url: str,
    endpoint: str,
    key: str,
    payload: dict,
    timeout: float = 60,
) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "run-runninghub-workflows/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        raise RunningHubError(f"HTTP {exc.code} from {endpoint}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RunningHubError(f"request to {endpoint} failed: {exc}") from None


def upload_file(base_url: str, key: str, path: Path) -> str:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise RunningHubError(f"upload input does not exist: {path}")

    boundary = "----RunningHubSkill" + uuid.uuid4().hex
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode()
    body = prefix + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/openapi/v2/media/upload/binary",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "User-Agent": "run-runninghub-workflows/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        raise RunningHubError(f"upload failed with HTTP {exc.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RunningHubError(f"upload failed: {exc}") from None

    if data.get("code", 0) != 0:
        raise RunningHubError(
            "upload rejected: " + str(data.get("message") or data.get("msg") or data)
        )
    try:
        return data["data"]["fileName"]
    except (KeyError, TypeError):
        raise RunningHubError("upload response did not contain data.fileName") from None


def parse_override(value: str) -> tuple[str, str, str]:
    parts = value.split(":", 2)
    if len(parts) != 3 or not parts[0] or not parts[1]:
        raise argparse.ArgumentTypeError("expected NODE_ID:FIELD:VALUE")
    return parts[0], parts[1], parts[2]


def parse_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)[xX](\d+)", value.strip())
    if not match:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, for example 1536x2048")
    return int(match.group(1)), int(match.group(2))


def image_dimensions(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as handle:
        head = handle.read(32)
        if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
            return struct.unpack(">II", head[16:24])
        if head[:2] != b"\xff\xd8":
            return None
        handle.seek(2)
        while True:
            marker_start = handle.read(1)
            if not marker_start:
                return None
            if marker_start != b"\xff":
                continue
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if not marker or marker in {b"\xd8", b"\xd9"}:
                continue
            length_bytes = handle.read(2)
            if len(length_bytes) != 2:
                return None
            length = struct.unpack(">H", length_bytes)[0]
            if marker[0] in {
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            }:
                frame = handle.read(5)
                if len(frame) != 5:
                    return None
                height, width = struct.unpack(">HH", frame[1:5])
                return width, height
            handle.seek(max(0, length - 2), 1)


def safe_extension(value: object) -> str:
    extension = re.sub(r"[^a-zA-Z0-9]", "", str(value or "bin")).lower()
    return extension or "bin"


def download(url: str, destination: Path) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "run-runninghub-workflows/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise RunningHubError(f"download failed for {url}: {exc}") from None
    if not data:
        raise RunningHubError(f"download returned an empty file: {url}")
    destination.write_bytes(data)
    return len(data)


def command_inspect(args: argparse.Namespace, key: str) -> int:
    response = request_json(
        args.base_url,
        "/api/openapi/getJsonApiFormat",
        key,
        {"apiKey": key, "workflowId": args.workflow_id},
    )
    if response.get("code", 0) != 0:
        raise RunningHubError(
            "workflow inspection failed: "
            + str(response.get("message") or response.get("msg") or response)
        )
    prompt = response.get("data", {}).get("prompt")
    if isinstance(prompt, str):
        prompt = json.loads(prompt)
    if not isinstance(prompt, dict):
        raise RunningHubError("inspection response did not contain a workflow prompt")
    rendered = json.dumps(prompt, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"Workflow API prompt: {output}")
    else:
        print(rendered, end="")
    return 0


def command_run(args: argparse.Namespace, key: str) -> int:
    node_info: list[dict[str, str]] = []
    for node_id, field_name, value in args.set_values:
        node_info.append(
            {"nodeId": node_id, "fieldName": field_name, "fieldValue": value}
        )
    for node_id, field_name, local_path in args.uploads:
        print(f"Uploading {Path(local_path).name} for node {node_id}:{field_name}...")
        server_name = upload_file(args.base_url, key, Path(local_path))
        node_info.append(
            {"nodeId": node_id, "fieldName": field_name, "fieldValue": server_name}
        )

    payload: dict[str, object] = {
        "apiKey": key,
        "workflowId": args.workflow_id,
        "nodeInfoList": node_info,
    }
    if args.retain_seconds is not None:
        payload["retainSeconds"] = args.retain_seconds
    if args.instance_type:
        payload["instanceType"] = args.instance_type

    response = request_json(args.base_url, "/task/openapi/create", key, payload, timeout=120)
    if response.get("code", 0) != 0:
        raise RunningHubError(
            "task creation failed: "
            + str(response.get("message") or response.get("msg") or response)
        )
    task_id = str(response.get("data", {}).get("taskId") or "")
    if not task_id:
        raise RunningHubError("task creation response did not contain data.taskId")
    print(f"Task ID: {task_id}")

    deadline = time.monotonic() + args.timeout
    query: dict = {}
    last_status = None
    while time.monotonic() < deadline:
        query = request_json(
            args.base_url,
            "/openapi/v2/query",
            key,
            {"taskId": task_id},
        )
        if query.get("code", 0) not in {0, "0", None}:
            raise RunningHubError(
                "task query failed: "
                + str(query.get("message") or query.get("msg") or query)
            )
        status = str(query.get("status") or query.get("data", {}).get("status") or "UNKNOWN")
        if status != last_status:
            print(f"Status: {status}")
            last_status = status
        if status == "SUCCESS":
            break
        if status in TERMINAL_FAILURES:
            message = query.get("errorMessage") or query.get("message") or query.get("msg")
            raise RunningHubError(f"task {task_id} ended as {status}: {message or 'unknown error'}")
        time.sleep(args.poll_interval)
    else:
        raise RunningHubError(f"timed out waiting for task {task_id}")

    results = query.get("results") or query.get("data", {}).get("results") or []
    if not results and not args.allow_no_results:
        raise RunningHubError(f"task {task_id} succeeded but returned no results")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "taskId": task_id,
        "status": "SUCCESS",
        "workflowId": args.workflow_id,
        "outputs": [],
        "promptTips": query.get("promptTips") or "",
    }
    for index, result in enumerate(results, 1):
        url = result.get("url") or result.get("fileUrl")
        if not url:
            raise RunningHubError(f"result {index} has no download URL")
        extension = safe_extension(result.get("outputType") or result.get("fileType"))
        destination = output_dir / f"runninghub_{task_id}_{index}.{extension}"
        byte_count = download(str(url), destination)
        dimensions = image_dimensions(destination)
        if args.expect_size and dimensions != args.expect_size:
            raise RunningHubError(
                f"resolution mismatch for {destination}: expected "
                f"{args.expect_size[0]}x{args.expect_size[1]}, got {dimensions}"
            )
        item = {"path": str(destination), "bytes": byte_count}
        if dimensions:
            item["width"], item["height"] = dimensions
        manifest["outputs"].append(item)
        detail = f" ({dimensions[0]}x{dimensions[1]})" if dimensions else ""
        print(f"Downloaded: {destination}{detail}")

    manifest_path = output_dir / f"runninghub_{task_id}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest: {manifest_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="https://www.runninghub.cn",
        help="official RunningHub origin (default: %(default)s)",
    )
    parser.add_argument(
        "--prompt-key",
        action="store_true",
        help="prompt for a key when RUNNINGHUB_API_KEY is absent",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="save API-format workflow JSON")
    inspect_parser.add_argument("--workflow-id", required=True)
    inspect_parser.add_argument("--output", help="output JSON path; stdout when omitted")
    inspect_parser.set_defaults(handler=command_inspect)

    run_parser = subparsers.add_parser("run", help="upload inputs, run, poll, and download")
    run_parser.add_argument("--workflow-id", required=True)
    run_parser.add_argument(
        "--upload",
        dest="uploads",
        action="append",
        default=[],
        type=parse_override,
        metavar="NODE:FIELD:PATH",
        help="upload a local file and override a node field; repeatable",
    )
    run_parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        default=[],
        type=parse_override,
        metavar="NODE:FIELD:VALUE",
        help="override a node field with a literal value; repeatable",
    )
    run_parser.add_argument("--output-dir", required=True)
    run_parser.add_argument("--expect-size", type=parse_size, metavar="WIDTHxHEIGHT")
    run_parser.add_argument("--instance-type", help="optional RunningHub tier, e.g. plus")
    run_parser.add_argument("--retain-seconds", type=int)
    run_parser.add_argument("--poll-interval", type=float, default=10.0)
    run_parser.add_argument("--timeout", type=float, default=2700.0)
    run_parser.add_argument("--allow-no-results", action="store_true")
    run_parser.set_defaults(handler=command_run)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        key = api_key(args.prompt_key)
        return args.handler(args, key)
    except (RunningHubError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
