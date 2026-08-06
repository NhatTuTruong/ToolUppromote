"""Mã hóa/giải mã secret cục bộ (Windows DPAPI). Chỉ giải mã được trên cùng user/máy."""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

DPAPI_PREFIX = "dpapi:"
PLAIN_PREFIX = "plain:"


def _dpapi_available() -> bool:
    return sys.platform.startswith("win")


def _dpapi_encrypt(raw: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    blob_in = DATA_BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw, len(raw)), ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptProtectData thất bại")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _dpapi_decrypt(raw: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    blob_in = DATA_BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw, len(raw)), ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptUnprotectData thất bại")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def encrypt_local_secret(plaintext: str) -> str:
    raw = (plaintext or "").encode("utf-8")
    if not raw:
        return ""
    if not _dpapi_available():
        raise RuntimeError("Mã hóa DPAPI chỉ hỗ trợ Windows.")
    enc = _dpapi_encrypt(raw)
    return DPAPI_PREFIX + base64.urlsafe_b64encode(enc).decode("ascii")


def decrypt_local_secret(stored: str) -> str:
    value = (stored or "").strip()
    if not value:
        return ""
    if value.startswith(DPAPI_PREFIX):
        if not _dpapi_available():
            raise RuntimeError("Không giải mã được secret dpapi: trên hệ điều hành này.")
        blob = base64.urlsafe_b64decode(value[len(DPAPI_PREFIX) :].encode("ascii"))
        return _dpapi_decrypt(blob).decode("utf-8")
    if value.startswith(PLAIN_PREFIX):
        return value[len(PLAIN_PREFIX) :]
    return value


def is_encrypted_local_secret(stored: str) -> bool:
    return (stored or "").strip().startswith(DPAPI_PREFIX)


def resolve_uppromote_password(raw: str | None = None) -> str:
    pwd, _err = resolve_uppromote_password_with_error(raw)
    return pwd


def resolve_uppromote_password_with_error(raw: str | None = None) -> tuple[str, str | None]:
    """Trả (password, lỗi). Lỗi None nếu OK."""
    value = (raw if raw is not None else os.getenv("UPPROMOTE_PASSWORD", "")).strip()
    if not value:
        return "", "UPPROMOTE_PASSWORD trống trong .env (cạnh file .exe)."
    if is_encrypted_local_secret(value):
        try:
            return decrypt_local_secret(value), None
        except Exception:
            return (
                "",
                "UPPROMOTE_PASSWORD dạng dpapi: không giải mã được trên máy Windows này "
                "(chỉ dùng được trên đúng máy/user đã mã hóa). "
                "Sửa .env cạnh file .exe: ghi lại mật khẩu plain text, hoặc chạy "
                "python scripts/encrypt_uppromote_password.py trên máy mới.",
            )
    try:
        return decrypt_local_secret(value), None
    except Exception as exc:
        return "", f"Không đọc được UPPROMOTE_PASSWORD: {exc}"


def _parse_env_password(env_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not env_path.is_file():
        return out
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] == '"':
            v = v[1:-1]
        out[k] = v
    return out


def migrate_uppromote_password_in_env(env_path: Path | None = None) -> bool:
    """Nếu UPPROMOTE_PASSWORD đang plain text → mã hóa dpapi và ghi lại .env."""
    if not _dpapi_available():
        return False
    if os.getenv("UPPROMOTE_SKIP_DPAPI", "").strip().lower() in ("1", "true", "yes", "on"):
        return False

    if env_path is None:
        from runtime_paths import app_dir

        env_path = app_dir() / ".env"
    path = Path(env_path)
    if not path.is_file():
        return False

    env = _parse_env_password(path)
    current = str(env.get("UPPROMOTE_PASSWORD") or "").strip()
    if not current or is_encrypted_local_secret(current):
        return False

    try:
        plain = decrypt_local_secret(current)
        if not plain:
            return False
        env["UPPROMOTE_PASSWORD"] = encrypt_local_secret(plain)
    except Exception:
        return False

    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    found = False
    for line in lines:
        if line.strip().startswith("UPPROMOTE_PASSWORD="):
            out.append(f'UPPROMOTE_PASSWORD="{env["UPPROMOTE_PASSWORD"]}"')
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f'UPPROMOTE_PASSWORD="{env["UPPROMOTE_PASSWORD"]}"')
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ["UPPROMOTE_PASSWORD"] = env["UPPROMOTE_PASSWORD"]
    return True
