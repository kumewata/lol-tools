"""Local credential storage for Sign in with ChatGPT."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO, Iterator

try:  # Unix
    import fcntl
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]
    import msvcrt


def _lock_file(f: IO[str]) -> None:
    if fcntl is not None:
        fcntl.flock(f, fcntl.LOCK_EX)
    else:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)


def _unlock_file(f: IO[str]) -> None:
    if fcntl is not None:
        fcntl.flock(f, fcntl.LOCK_UN)
    else:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def default_config_dir() -> Path:
    override = os.environ.get("LOL_TOOLS_CONFIG_DIR")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "lol-tools"


@dataclass
class Credentials:
    subject: str
    client_id: str
    ext_agent_host_id: str
    id_token: str
    access_token: str
    refresh_token: str
    expires_at: float
    scopes: list[str] = field(default_factory=list)

    def __repr__(self) -> str:  # never leak tokens through repr/logging
        return (
            f"Credentials(subject={self.subject!r}, client_id={self.client_id!r}, "
            f"expires_at={self.expires_at!r}, scopes={self.scopes!r})"
        )


class CredentialStore:
    """Persist one ChatGPT profile as a 0600 JSON file.

    The host id survives logout so that re-registration reuses the same host.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_config_dir() / "chatgpt.json"
        self._lock_path = self.path.with_suffix(".lock")

    def _read_raw(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write_raw(self, data: dict) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".chatgpt.", suffix=".tmp")
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise

    def host_id(self) -> str:
        with self.lock():
            raw = self._read_raw()
            host_id = raw.get("ext_agent_host_id")
            if not host_id:
                host_id = f"urn:uuid:{uuid.uuid4()}"
                raw["ext_agent_host_id"] = host_id
                self._write_raw(raw)
            return host_id

    def load(self) -> Credentials | None:
        raw = self._read_raw()
        if not raw.get("access_token"):
            return None
        return Credentials(**{k: raw[k] for k in Credentials.__dataclass_fields__ if k in raw})

    def save(self, creds: Credentials) -> None:
        self._write_raw(asdict(creds))

    def clear_tokens(self) -> None:
        """Drop tokens but keep the host id (and issued client id for reauth)."""
        raw = self._read_raw()
        keep = {k: raw[k] for k in ("ext_agent_host_id", "client_id") if k in raw}
        self._write_raw(keep)

    def issued_client_id(self) -> str | None:
        return self._read_raw().get("client_id")

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        """Serialize refreshes across processes (refresh tokens rotate)."""
        self._lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(self._lock_path, "a") as f:
            _lock_file(f)
            try:
                yield
            finally:
                _unlock_file(f)
