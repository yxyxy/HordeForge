from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

import requests

from cli import repo_store

logger = logging.getLogger(__name__)


class QwenOAuthTokenManager:
    _TOKEN_ENDPOINT = "https://chat.qwen.ai/api/v1/oauth2/token"
    _CLIENT_ID = "f0304373b74a44d2b584a3fb70ca9e56"
    _TOKEN_REFRESH_BUFFER_MS = 30_000
    _LOCK_TIMEOUT_MS = 35_000
    _LOCK_STALE_MS = 120_000
    _CACHE_CHECK_INTERVAL_MS = 5_000

    _refresh_locks: dict[str, Lock] = {}
    _locks_guard = Lock()
    _memory_cache: dict[str, dict[str, Any]] = {}

    def __init__(
        self,
        *,
        oauth_credentials_json: str,
        credentials_secret_ref: str | None = None,
        storage_dir: str | Path | None = None,
    ):
        self._credentials = self._parse_credentials(oauth_credentials_json)
        self._secret_ref = (
            credentials_secret_ref.strip()
            if isinstance(credentials_secret_ref, str) and credentials_secret_ref.strip()
            else None
        )
        self._key = self._build_key(self._credentials)
        self._storage_dir = self._resolve_storage_dir(storage_dir)
        self._credentials_path = self._storage_dir / f"{self._key}.oauth_creds.json"
        self._lock_path = self._storage_dir / f"{self._key}.oauth_creds.lock"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._reload_if_changed(force=True)

    @staticmethod
    def _build_key(credentials: dict[str, Any]) -> str:
        refresh_token = str(credentials.get("refresh_token") or "")
        digest = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
        return digest[:24]

    @staticmethod
    def _parse_credentials(raw_json: str) -> dict[str, Any]:
        try:
            credentials = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid Qwen OAuth credentials JSON") from exc
        if not isinstance(credentials, dict):
            raise ValueError("Invalid Qwen OAuth credentials payload")
        if not isinstance(credentials.get("refresh_token"), str) or not credentials.get(
            "refresh_token"
        ):
            raise ValueError("Qwen OAuth refresh_token is missing")
        access_token = credentials.get("access_token")
        if access_token is None:
            credentials["access_token"] = ""
        elif not isinstance(access_token, str):
            raise ValueError("Qwen OAuth access_token must be string")
        return credentials

    @staticmethod
    def _resolve_storage_dir(storage_dir: str | Path | None) -> Path:
        if isinstance(storage_dir, (str, Path)):
            return Path(storage_dir)
        home = os.getenv("HORDEFORGE_HOME", "").strip()
        if home:
            return Path(home).expanduser() / "qwen_oauth"
        return Path.home() / ".hordeforge" / "qwen_oauth"

    @staticmethod
    def _is_token_valid(credentials: dict[str, Any]) -> bool:
        access_token = credentials.get("access_token")
        expiry = credentials.get("expiry_date")
        if not isinstance(access_token, str) or not access_token:
            return False
        if not isinstance(expiry, int):
            return False
        return int(time.time() * 1000) < (expiry - QwenOAuthTokenManager._TOKEN_REFRESH_BUFFER_MS)

    def get_current_credentials(self) -> dict[str, Any]:
        return dict(self._credentials)

    def get_valid_credentials(self, *, force_refresh: bool = False) -> dict[str, Any]:
        self._reload_if_changed(force=False)
        if not force_refresh and self._is_token_valid(self._credentials):
            return dict(self._credentials)

        lock = self._get_refresh_lock(self._key)
        with lock:
            self._reload_if_changed(force=True)
            if not force_refresh and self._is_token_valid(self._credentials):
                return dict(self._credentials)

            self._refresh_with_file_lock()
            return dict(self._credentials)

    @classmethod
    def _get_refresh_lock(cls, key: str) -> Lock:
        with cls._locks_guard:
            lock = cls._refresh_locks.get(key)
            if lock is None:
                lock = Lock()
                cls._refresh_locks[key] = lock
            return lock

    def _reload_if_changed(self, *, force: bool) -> None:
        now = int(time.time() * 1000)
        state = self._memory_cache.get(self._key)
        if state is None:
            state = {"credentials": None, "file_mtime": 0.0, "last_check_ms": 0}
            self._memory_cache[self._key] = state

        if not force and (now - int(state.get("last_check_ms", 0))) < self._CACHE_CHECK_INTERVAL_MS:
            cached = state.get("credentials")
            if isinstance(cached, dict):
                self._credentials = dict(cached)
            return

        state["last_check_ms"] = now
        if not self._credentials_path.exists():
            state["file_mtime"] = 0.0
            return

        try:
            mtime = self._credentials_path.stat().st_mtime
            if force or mtime > float(state.get("file_mtime", 0.0)):
                file_creds = self._parse_credentials(
                    self._credentials_path.read_text(encoding="utf-8")
                )
                self._credentials = file_creds
                state["credentials"] = dict(file_creds)
                state["file_mtime"] = mtime
        except Exception:
            return

    def _refresh_with_file_lock(self) -> None:
        lock_acquired = False
        lock_fd: int | None = None
        started = time.time()
        while (time.time() - started) * 1000 < self._LOCK_TIMEOUT_MS:
            try:
                lock_fd = os.open(
                    str(self._lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.write(lock_fd, str(os.getpid()).encode("utf-8"))
                lock_acquired = True
                break
            except FileExistsError:
                self._maybe_break_stale_file_lock()
                time.sleep(0.05 + random.random() * 0.05)
            except Exception:
                time.sleep(0.05 + random.random() * 0.05)

        if not lock_acquired:
            self._maybe_break_stale_file_lock(force=True)
            try:
                lock_fd = os.open(
                    str(self._lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.write(lock_fd, str(os.getpid()).encode("utf-8"))
                lock_acquired = True
            except Exception as exc:
                logger.warning(
                    "qwen_oauth_refresh_without_file_lock reason=%s",
                    str(exc)[:300],
                )
                self._refresh_without_file_lock()
                return

        try:
            self._refresh_and_persist_if_needed()
        finally:
            try:
                if lock_fd is not None:
                    os.close(lock_fd)
            except Exception:
                pass
            try:
                self._lock_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _refresh_without_file_lock(self) -> None:
        self._refresh_and_persist_if_needed()

    def _refresh_and_persist_if_needed(self) -> None:
        self._reload_if_changed(force=True)
        if self._is_token_valid(self._credentials):
            return
        refreshed = self._refresh_access_token()
        self._credentials = refreshed
        try:
            self._save_credentials(refreshed)
        except Exception as exc:
            logger.warning("qwen_oauth_save_credentials_failed error=%s", str(exc)[:300])
        try:
            self._persist_secret(refreshed)
        except Exception as exc:
            logger.warning("qwen_oauth_persist_secret_failed error=%s", str(exc)[:300])
        self._memory_cache[self._key] = {
            "credentials": dict(refreshed),
            "file_mtime": self._credentials_path.stat().st_mtime
            if self._credentials_path.exists()
            else 0.0,
            "last_check_ms": int(time.time() * 1000),
        }

    def _maybe_break_stale_file_lock(self, *, force: bool = False) -> None:
        try:
            stat = self._lock_path.stat()
        except FileNotFoundError:
            return
        except Exception:
            return

        age_ms = (time.time() - stat.st_mtime) * 1000
        if not force and age_ms < self._LOCK_STALE_MS:
            return

        try:
            self._lock_path.unlink(missing_ok=True)
            logger.warning(
                "qwen_oauth_stale_lock_removed path=%s age_ms=%.0f force=%s",
                self._lock_path,
                age_ms,
                force,
            )
        except Exception:
            return

    def _refresh_access_token(self) -> dict[str, Any]:
        refresh_token = self._credentials.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise RuntimeError("Qwen OAuth refresh_token is missing")
        refresh_tail = refresh_token[-6:] if len(refresh_token) >= 6 else "***"
        logger.info(
            "qwen_oauth_refresh_request endpoint=%s refresh_tail=%s",
            self._TOKEN_ENDPOINT,
            refresh_tail,
        )

        response = requests.post(
            self._TOKEN_ENDPOINT,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                # Qwen token endpoint may return WAF HTML for generic python-requests UA.
                # Match Qwen Code behavior closer (Node/undici-like client fingerprint).
                "User-Agent": "undici",
                "x-request-id": str(uuid.uuid4()),
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._CLIENT_ID,
            },
            timeout=20,
        )
        text = response.text or ""
        content_type = response.headers.get("Content-Type", "")
        logger.info(
            "qwen_oauth_refresh_response status=%s content_type=%s body_head=%s",
            response.status_code,
            content_type,
            text[:240].replace("\n", " "),
        )
        if response.status_code == 400:
            logger.warning(
                "qwen_oauth_refresh_mode mode=http_400_invalid_request content_type=%s",
                content_type,
            )
            self._clear_persisted_credentials()
            raise RuntimeError(
                "Qwen OAuth refresh token expired or invalid. "
                "Please re-authenticate and update credentials."
            )
        if response.status_code != 200:
            logger.warning(
                "qwen_oauth_refresh_mode mode=http_error status=%s content_type=%s",
                response.status_code,
                content_type,
            )
            raise RuntimeError(
                f"Qwen OAuth refresh failed: status={response.status_code} body={text[:1000]}"
            )

        try:
            token_data = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            logger.warning(
                "qwen_oauth_refresh_mode mode=non_json_waf status=%s content_type=%s body_head=%s",
                response.status_code,
                content_type,
                text[:240].replace("\n", " "),
            )
            raise RuntimeError(
                "Qwen OAuth refresh returned non-JSON response: "
                f"status={response.status_code} "
                f"content_type={content_type} "
                f"body={text[:1000]}"
            ) from exc

        if isinstance(token_data, dict) and token_data.get("error"):
            logger.warning(
                "qwen_oauth_refresh_mode mode=json_error error=%s error_description=%s",
                token_data.get("error"),
                token_data.get("error_description", ""),
            )
            raise RuntimeError(
                f"Qwen OAuth refresh failed: {token_data.get('error')} "
                f"{token_data.get('error_description', '')}".strip()
            )
        if not isinstance(token_data, dict):
            raise RuntimeError("Qwen OAuth refresh returned invalid payload")

        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in")
        token_type = token_data.get("token_type")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Qwen OAuth refresh did not return access_token")
        if not isinstance(expires_in, int):
            raise RuntimeError("Qwen OAuth refresh did not return expires_in")

        refreshed = dict(self._credentials)
        refreshed["access_token"] = access_token
        refreshed["refresh_token"] = token_data.get("refresh_token") or self._credentials.get(
            "refresh_token"
        )
        refreshed["token_type"] = token_type if isinstance(token_type, str) else "Bearer"
        refreshed["resource_url"] = token_data.get("resource_url") or self._credentials.get(
            "resource_url"
        )
        refreshed["expiry_date"] = int(time.time() * 1000) + expires_in * 1000
        logger.info(
            "qwen_oauth_refresh_mode mode=success expires_in=%s access_tail=%s",
            expires_in,
            access_token[-6:] if len(access_token) >= 6 else "***",
        )
        return refreshed

    def _save_credentials(self, credentials: dict[str, Any]) -> None:
        tmp_path = self._credentials_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(credentials, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self._credentials_path)

    def _persist_secret(self, credentials: dict[str, Any]) -> None:
        if not self._secret_ref:
            return
        try:
            repo_store.set_secret_value(
                self._secret_ref, json.dumps(credentials, ensure_ascii=False)
            )
        except Exception:
            return

    def _clear_persisted_credentials(self) -> None:
        try:
            self._credentials_path.unlink(missing_ok=True)
        except Exception:
            pass
        self._memory_cache.pop(self._key, None)
