---
name: run-runninghub-workflows
description: Execute authenticated RunningHub ComfyUI workflows through the API, including binary input upload, Load Image or other node-field overrides, task submission, status polling, output download, and artifact validation. Use when Codex needs to automate, schedule, reproduce, or batch a RunningHub workflow without operating the browser canvas; inspect a workflow's API-format JSON; replace image, video, audio, prompt, seed, or model node values; or diagnose RunningHub API task failures.
---

# Run RunningHub Workflows

Use `scripts/runninghub_workflow.py` for the full API lifecycle. Prefer it to browser automation once a workflow is saved in RunningHub and its workflow ID is known.

## Core workflow

1. Confirm the exact workflow ID and input files. Resolve every local path before uploading.
2. Obtain an authorized API key from `https://www.runninghub.cn/enterprise-api/consumerApi`. For ordinary personal workflows, select **消费级-会员** and copy the existing default key. Reuse it when appropriate; creating or resetting a key changes persistent account access and requires the user's explicit authorization.
3. Keep the key out of source files, command arguments, logs, screenshots, and assistant messages. Supply it only through `RUNNINGHUB_API_KEY`. If copied from a browser, inject it directly from the clipboard and clear the clipboard after the command.
4. Inspect the workflow when node IDs or field names are uncertain:

   ```bash
   RUNNINGHUB_API_KEY="$(pbpaste)" python scripts/runninghub_workflow.py inspect \
     --workflow-id WORKFLOW_ID \
     --output workflow_api.json
   pbcopy </dev/null
   ```

   On systems without `pbpaste`, export the value through a hidden prompt, run the command, then `unset RUNNINGHUB_API_KEY`. Never place the literal key in the command line.

5. Run the workflow. Use `--upload NODE:FIELD:PATH` for local assets; the script uploads each asset first and substitutes RunningHub's returned `fileName`. Use `--set NODE:FIELD:VALUE` for text or scalar overrides.

   ```bash
   RUNNINGHUB_API_KEY="$(pbpaste)" python scripts/runninghub_workflow.py run \
     --workflow-id WORKFLOW_ID \
     --upload 2:image:/absolute/path/target.png \
     --upload 3:image:/absolute/path/identity.png \
     --set 6:text:'photorealistic studio portrait' \
     --output-dir /absolute/path/outputs \
     --expect-size 1536x2048
   pbcopy </dev/null
   ```

6. Report the task ID, terminal status, downloaded paths, dimensions when available, and any quality limitations found by visual inspection. A `SUCCESS` response proves execution, not visual correctness.

## Node overrides

- Read `references/api.md` when determining endpoints, request fields, instance types, or error handling.
- Match the node ID and field name in RunningHub's API-format prompt, not the visual position of a node.
- For a standard ComfyUI `LoadImage` node, use field `image`.
- Upload every local input through the media endpoint. Never place a local filesystem path directly into `fieldValue`.
- Keep a stable seed and unchanged sampler settings when comparing identity or lighting variants.
- Run one known-good input before scheduling a batch.

## Validation

- Treat `QUEUED` and `RUNNING` as nonterminal; continue polling within the requested time budget.
- Treat `FAILED`, `ERROR`, `CANCELED`, and `CANCELLED` as failures and surface the API error without exposing the key.
- Require at least one result for a successful generative workflow unless it is intentionally output-free.
- Verify that every downloaded file is nonempty. For PNG or JPEG results, inspect pixel dimensions; use `--expect-size` when the workflow promises an exact resolution.
- Visually compare identity, pose, camera, anatomy, clothing, geometry, lighting, and artifacts against the supplied controls.
- Preserve the generated `manifest.json`; it records the task and outputs but never the API key.

## Credential safety

- Never commit API keys or write them into `.env`, workflow JSON, manifests, shell history, or documentation.
- Do not print clipboard contents or environment values while checking whether a key exists.
- Prefer an existing key over resetting it. Reset only when explicitly requested or when compromise is established.
- Clear temporary clipboard content after use. Unset or discard the process environment when the run finishes.
- If no authorized key exists, stop immediately before the account action and request confirmation to create one.

## Failure recovery

- **401 or key verification failure:** confirm the key type and account context without printing it. Workflow APIs accept consumer-member, enterprise-shared, or enterprise-dedicated keys according to account entitlements.
- **Node validation failure:** run `inspect`, confirm the node exists, and use its exact input field name.
- **Load node cannot find a file:** replace the local path with the `fileName` returned by the upload endpoint; do not use `download_url` for ComfyUI nodes.
- **Task succeeds with no result:** confirm that a reachable Save/Preview output node executes. Inspect `promptTips` and the API-format prompt.
- **Resolution mismatch:** verify the upscale node is connected to the saved output and that its scale/tile settings were not overridden.
- **Long queue:** continue polling; do not resubmit unless duplicate billing and duplicate outputs are acceptable.
- **Browser UI and API disagree:** use the task ID as the reconciliation key and query the V2 result endpoint.
