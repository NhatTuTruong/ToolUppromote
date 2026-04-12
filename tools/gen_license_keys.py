#!/usr/bin/env python3
"""
Chỉ chạy trên máy bạn (vendor): sinh key bán — AFF_LICENSE_HMAC_SECRET lấy từ:

  • file .env ở thư mục gốc project (cùng cấp với filter.py), hoặc
  • biến môi trường (PowerShell: $env:AFF_LICENSE_HMAC_SECRET="...") — ưu tiên hơn .env nếu đã set.

  python tools/gen_license_keys.py 50
  python tools/gen_license_keys.py 5 --append   # nối thêm 5 key, không xóa key cũ trong file

Ghi file vendor_keys_AFL1.txt ở thư mục gốc project; đồng thời in key ra stderr (luôn thấy trên terminal).
File có thể bị .gitignore — nếu IDE không refresh, đóng tab file rồi mở lại.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

KEY_PREFIX = "AFL1"
KEY_VERSION = b"AFL1v1|"


def _load_secret_from_project_env() -> None:
    """Thêm thư mục gốc project vào sys.path rồi import filter → nạp .env (load_env_file)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import filter as _filter  # noqa: F401 — side effect: load_env_file(BASE_DIR / ".env")


def make_key(secret: bytes) -> str:
    body = secrets.token_bytes(12)
    body_b32 = base64.b32encode(body).decode("ascii").rstrip("=")
    msg = KEY_VERSION + body
    mac = hmac.new(secret, msg, hashlib.sha256).digest()[:6]
    mac_b32 = base64.b32encode(mac).decode("ascii").rstrip("=")
    return f"{KEY_PREFIX}-{body_b32}-{mac_b32}"


def main() -> int:
    _load_secret_from_project_env()
    n = 50
    append = False
    pos_args: list[str] = []
    for a in sys.argv[1:]:
        if a in ("-h", "--help"):
            print(
                "Usage: python tools/gen_license_keys.py [count] [--append]\n"
                "  count   Số key (1–5000), mặc định 50.\n"
                "  --append  Nối vào cuối vendor_keys_AFL1.txt (mặc định: ghi đè cả file).",
                file=sys.stderr,
            )
            return 0
        if a == "--append":
            append = True
            continue
        pos_args.append(a)
    if pos_args:
        try:
            n = max(1, min(5000, int(pos_args[0])))
        except ValueError:
            print("Usage: python tools/gen_license_keys.py [count] [--append]", file=sys.stderr)
            return 2
    raw = (os.environ.get("AFF_LICENSE_HMAC_SECRET") or "").strip()
    if len(raw) < 16:
        print(
            "Thiếu AFF_LICENSE_HMAC_SECRET (tối thiểu 16 ký tự). "
            "Thêm vào file .env ở thư mục gốc project (AFF_LICENSE_HMAC_SECRET=...) "
            "hoặc đặt biến môi trường rồi chạy lại.",
            file=sys.stderr,
        )
        return 1
    secret = raw.encode("utf-8")
    keys = [make_key(secret) for _ in range(n)]
    out_name = "vendor_keys_AFL1.txt"
    out_path = (ROOT / out_name).resolve()
    block = "\n".join(keys) + ("\n" if keys else "")
    if append and out_path.is_file():
        prev = out_path.read_text(encoding="utf-8")
        if prev and not prev.endswith("\n"):
            prev += "\n"
        out_path.write_text(prev + block, encoding="utf-8")
    else:
        out_path.write_text(block, encoding="utf-8")

    # Luôn in key ra stderr (stdout đôi khi bị nuốt khi pipe/IDE).
    print(block, end="", file=sys.stderr)
    print(f"Đã ghi {n} key → {out_path}", file=sys.stderr)
    if append:
        print("(chế độ --append: đã nối vào file)", file=sys.stderr)
    print(block, end="", file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
