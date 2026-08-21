# RunningHub workflow API reference

## Endpoints

| Operation | Method | CN endpoint |
|---|---|---|
| Upload binary media | POST multipart | `/openapi/v2/media/upload/binary` |
| Start ComfyUI workflow | POST JSON | `/task/openapi/create` |
| Inspect API-format workflow | POST JSON | `/api/openapi/getJsonApiFormat` |
| Query task and results | POST JSON | `/openapi/v2/query` |
| Cancel task | POST JSON | `/task/openapi/cancel` |

The default origin is `https://www.runninghub.cn`. Pass `--base-url` to the bundled script when an account uses another official RunningHub origin.

## Authentication

Send `Authorization: Bearer API_KEY`. The legacy workflow create and inspect requests also accept or require `apiKey` in their JSON body; the bundled script supplies both without logging either.

Workflow APIs support consumer-member, enterprise-shared, and enterprise-dedicated keys subject to the user's RunningHub plan. Standard model and LLM endpoints have different key restrictions and are outside this skill.

## Upload response

Upload a file as multipart field `file`. A successful response resembles:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "type": "image",
    "download_url": "https://temporary.example/result.png",
    "fileName": "openapi/hash.png",
    "size": "3490"
  }
}
```

Use `data.fileName` for a ComfyUI node override. `download_url` is intended for standard-model APIs and is temporary.

## Create request

```json
{
  "apiKey": "API_KEY",
  "workflowId": "WORKFLOW_ID",
  "retainSeconds": 60,
  "instanceType": "plus",
  "nodeInfoList": [
    {"nodeId": "2", "fieldName": "image", "fieldValue": "openapi/hash.png"},
    {"nodeId": "6", "fieldName": "text", "fieldValue": "prompt text"}
  ]
}
```

`retainSeconds` and `instanceType` are optional. Omit `instanceType` for the account/workflow default. Use `plus` only when the requested execution tier supports it.

A successful create response returns `data.taskId` and a status such as `QUEUED` or `RUNNING`. Preserve the task ID immediately.

## Query request and response

Request:

```json
{"taskId": "TASK_ID"}
```

Successful terminal response:

```json
{
  "taskId": "TASK_ID",
  "status": "SUCCESS",
  "errorCode": "",
  "errorMessage": "",
  "results": [
    {"url": "https://temporary.example/output.png", "outputType": "png"}
  ],
  "promptTips": ""
}
```

Download result URLs promptly because availability can be time-limited.

## Inspect request

```json
{"apiKey": "API_KEY", "workflowId": "WORKFLOW_ID"}
```

The response's `data.prompt` is a JSON-encoded ComfyUI API prompt. Parse it once more as JSON before inspecting node IDs, `class_type`, inputs, and `_meta.title`.

## Confirmed integration example

The workflow `2090693736601837569` was successfully run with uploaded inputs overriding nodes `2:image` and `3:image`. Task `2090711299486076930` returned one 1536×2048 PNG. This confirms the endpoint sequence and override format; it is not a public workflow and must not be used as a default in unrelated accounts.
