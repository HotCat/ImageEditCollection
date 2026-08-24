# Local environment

Use Python 3.12 on Apple Silicon. `scripts/bootstrap_environment.py` creates a virtual environment, installs the pinned packages in `scripts/requirements-macos.txt`, and checks out the tested CrossView-Warp revision. It does not download model weights during bootstrap.

Required system commands:

- `git`
- `ffmpeg`
- `ffprobe`
- a Python 3.12 interpreter with `venv`

Depth Anything downloads its checkpoint into the normal Hugging Face cache on first preprocessing. Expect roughly 1 GB for the Python environment plus model cache and hundreds of MB of temporary depth tensors for a 241-frame clip. Keep the runtime and working output outside the skill repository.

On Apple Silicon, preprocessing selects MPS automatically. On other hosts it falls back to CUDA when available, then CPU. CPU works but can be slow. Use `--device` to override selection.

Do not commit the runtime directory or Hugging Face cache. The repository stores the exact dependency manifest and pinned CrossView revision instead of a machine-specific binary environment.
