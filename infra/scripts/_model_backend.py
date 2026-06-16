"""Pluggable local-inference backend for the model-validation harnesses.

The harnesses drive whichever local server hosts the model under test. The inference call itself is
OpenAI-compatible (`/v1/chat/completions`) and portable; the only backend-specific part is model
*lifecycle orchestration* — start the server, list installed models, load/unload one at a time. This
module isolates that behind `ModelBackend` so no harness shells out to a specific tool.

`LmStudioBackend` is the only implementation today (LM Studio's `lms` CLI + server on port 1234).
Select a backend with the `MODEL_BACKEND` env var (default `lmstudio`). Future `OllamaBackend` /
`LlamaCppBackend` land as new classes here without touching any harness:

  - Ollama serves the same `/v1` shape on port 11434, auto-loads a model on first request, and
    evicts by keep-alive — so `load`/`unload_all` are effectively no-ops and `list_installed` shells
    `ollama list`.
  - llama.cpp's `llama-server` hosts one model per process — `load` would spawn/swap a process (or
    defer to llama-swap) rather than load into a running server.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

#: Env var selecting the local-inference backend.
MODEL_BACKEND_ENV: Final = "MODEL_BACKEND"
#: Default backend when `MODEL_BACKEND` is unset.
DEFAULT_BACKEND: Final = "lmstudio"


class ModelInfo(BaseModel):
    """An installed model and its headline metadata, as the backend reports it."""

    model_config = ConfigDict(frozen=True)

    key: str
    size_bytes: int = 0
    params: str = ""
    arch: str = ""


@runtime_checkable
class ModelBackend(Protocol):
    """Orchestrates a local OpenAI-compatible inference server hosting one model at a time."""

    @property
    def chat_url(self) -> str:
        """Return the OpenAI-compatible chat-completions endpoint URL."""
        ...

    def ensure_server(self) -> None:
        """Start the inference server if it is not already running (idempotent)."""
        ...

    def list_installed(self) -> list[str]:
        """Return the model keys available locally on this backend."""
        ...

    def list_installed_details(self) -> list[ModelInfo]:
        """Return installed models with size/params/arch metadata."""
        ...

    def load(self, model: str) -> None:
        """Make `model` the single loaded model (unloading any others first)."""
        ...

    def unload_all(self) -> None:
        """Unload every loaded model, freeing memory for the next one."""
        ...


class LmStudioBackend:
    """`ModelBackend` backed by LM Studio's `lms` CLI and local server on port 1234."""

    #: LM Studio's default OpenAI-compatible server port.
    PORT: Final = 1234

    @property
    def chat_url(self) -> str:
        """Return LM Studio's chat-completions endpoint."""
        return f"http://localhost:{self.PORT}/v1/chat/completions"

    def ensure_server(self) -> None:
        """Start `lms server` if not already up (idempotent)."""
        subprocess.run(["lms", "server", "start"], capture_output=True, check=False)

    def list_installed(self) -> list[str]:
        """Return model keys from `lms ls --json` (empty list if the call fails)."""
        return [info.key for info in self.list_installed_details()]

    def list_installed_details(self) -> list[ModelInfo]:
        """Return installed models with metadata from `lms ls --json` (empty list if the call fails)."""
        proc = subprocess.run(["lms", "ls", "--json"], capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not proc.stdout.strip():
            return []
        try:
            raw = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return []
        if not isinstance(raw, list):
            return []
        models: list[ModelInfo] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            key = entry.get("modelKey")
            if not isinstance(key, str) or not key:
                continue
            size = entry.get("sizeBytes")
            params = entry.get("paramsString") or entry.get("params")
            arch = entry.get("architecture") or entry.get("arch")
            models.append(
                ModelInfo(
                    key=key,
                    size_bytes=size if isinstance(size, int) else 0,
                    params=params if isinstance(params, str) else "",
                    arch=arch if isinstance(arch, str) else "",
                )
            )
        return models

    def load(self, model: str) -> None:
        """Unload everything, then load `model` (one instance — avoids ambiguous-id 400s)."""
        self.unload_all()
        subprocess.run(["lms", "load", model, "--gpu", "max", "--ttl", "3600", "-y"], capture_output=True, check=False)

    def unload_all(self) -> None:
        """Unload all loaded models."""
        subprocess.run(["lms", "unload", "--all"], capture_output=True, check=False)


#: Registry of backend factories by `MODEL_BACKEND` value.
_BACKENDS: Final[dict[str, Callable[[], ModelBackend]]] = {"lmstudio": LmStudioBackend}


def get_backend(name: str | None = None) -> ModelBackend:
    """Return the configured `ModelBackend` (default LM Studio).

    Resolution order: explicit `name` arg, then `MODEL_BACKEND` env, then `lmstudio`.
    Raises `ValueError` for an unknown backend name.
    """
    key = (name or os.environ.get(MODEL_BACKEND_ENV, DEFAULT_BACKEND)).strip().lower()
    factory = _BACKENDS.get(key)
    if factory is None:
        raise ValueError(f"unknown {MODEL_BACKEND_ENV}={key!r}; known backends: {sorted(_BACKENDS)}")
    return factory()


if __name__ == "__main__":
    # Run directly to list the installed models with size/params/arch, largest first.
    _models = get_backend().list_installed_details()
    if not _models:
        print("(no models found — is the backend running?)", file=sys.stderr)
        sys.exit(1)
    _key_width = max(len("MODEL"), max(len(_m.key) for _m in _models))
    _header = f"{'MODEL':<{_key_width}}  {'SIZE':>9}  {'PARAMS':<8} ARCH"
    print(_header)
    print("-" * len(_header))
    for _m in sorted(_models, key=lambda info: -info.size_bytes):
        _size = f"{_m.size_bytes / 1e9:6.2f} GB" if _m.size_bytes else "        ?"
        print(f"{_m.key:<{_key_width}}  {_size}  {_m.params:<8} {_m.arch}")
