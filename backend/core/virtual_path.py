"""
Virtual Path System: tool isolation with path masking.

Provides a virtual filesystem layer where tools see a sandboxed view
of paths, preventing access to sensitive areas while allowing controlled
operations within designated directories.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VirtualPathError(Exception):
    pass


class VirtualPathSystem:
    """Manages virtual paths for tool isolation."""

    def __init__(self, base_dir: str = "/tmp/ninko_sandbox"):
        self._base = Path(base_dir).resolve()
        self._base.mkdir(parents=True, exist_ok=True)
        self._mounts: dict[str, Path] = {}

    def mount(self, virtual_prefix: str, real_path: str) -> None:
        real = Path(real_path).resolve()
        if not real.exists():
            real.mkdir(parents=True, exist_ok=True)
        self._mounts[virtual_prefix] = real
        logger.info("Mounted %s → %s", virtual_prefix, real)

    def resolve(self, virtual_path: str) -> Path:
        if not virtual_path.startswith("/"):
            virtual_path = "/" + virtual_path

        for prefix, real in sorted(self._mounts.items(), key=lambda x: -len(x[0])):
            if virtual_path.startswith(prefix):
                relative = virtual_path[len(prefix) :].lstrip("/")
                resolved = (real / relative).resolve()

                if not str(resolved).startswith(str(real)):
                    raise VirtualPathError(f"Path traversal detected: {virtual_path}")
                return resolved

        resolved = (self._base / virtual_path.lstrip("/")).resolve()

        if not str(resolved).startswith(str(self._base)):
            raise VirtualPathError(f"Path traversal detected: {virtual_path}")
        return resolved

    def virtualize(self, real_path: str) -> str:
        real = Path(real_path).resolve()

        for prefix, mount_real in sorted(
            self._mounts.items(), key=lambda x: -len(x[0])
        ):
            try:
                relative = real.relative_to(mount_real)
                return f"{prefix}/{relative}"
            except ValueError:
                continue

        try:
            relative = real.relative_to(self._base)
            return f"/{relative}"
        except ValueError:
            return str(real)

    def list_dir(self, virtual_path: str) -> list[str]:
        resolved = self.resolve(virtual_path)
        if not resolved.is_dir():
            raise VirtualPathError(f"Not a directory: {virtual_path}")
        return [self.virtualize(str(p)) for p in resolved.iterdir()]

    def read_file(self, virtual_path: str) -> bytes:
        resolved = self.resolve(virtual_path)
        if not resolved.is_file():
            raise VirtualPathError(f"File not found: {virtual_path}")
        return resolved.read_bytes()

    def write_file(self, virtual_path: str, content: bytes) -> None:
        resolved = self.resolve(virtual_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(content)


_vps_instance: VirtualPathSystem | None = None


def get_virtual_path_system() -> VirtualPathSystem:
    global _vps_instance
    if _vps_instance is None:
        _vps_instance = VirtualPathSystem()
    return _vps_instance
