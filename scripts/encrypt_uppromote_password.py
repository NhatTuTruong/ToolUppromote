#!/usr/bin/env python3
"""Mã hóa UPPROMOTE_PASSWORD trong .env (Windows DPAPI)."""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from local_secret import encrypt_local_secret, is_encrypted_local_secret, migrate_uppromote_password_in_env
from runtime_paths import app_dir


def main() -> int:
    env_path = app_dir() / ".env"
    if len(sys.argv) > 1:
        plain = sys.argv[1]
    else:
        plain = getpass.getpass("Uppromote password: ")

    if not plain.strip():
        print("Password trống.")
        return 1

    enc = encrypt_local_secret(plain.strip())
    print(f"Encrypted value:\nUPPROMOTE_PASSWORD=\"{enc}\"")

    if env_path.is_file():
        ok = migrate_uppromote_password_in_env(env_path)
        if ok:
            print(f"\nĐã cập nhật {env_path}")
        elif is_encrypted_local_secret(plain):
            print("\n.env đã có password mã hóa.")
        else:
            print(f"\nDán dòng trên vào {env_path} (thay UPPROMOTE_PASSWORD cũ).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
