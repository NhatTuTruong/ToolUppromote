"""
Bản quyền: key HMAC (AFF_LICENSE_HMAC_SECRET) để xác thực key bán;
tối đa 2 máy / key. Chưa kích hoạt: tối đa 10 record Uppromote + 10 record Goaffpro trọn đời trên máy
(không reset theo ngày). Đã kích hoạt: quota record / ngày / máy (hằng LICENSED_EXPORTS_PER_DAY), reset 23h05 giờ Việt Nam (UTC+7).
Không có secret: vẫn giới hạn dùng thử; kích hoạt key cần secret trong .env.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

KEY_PREFIX = "AFL1"
KEY_VERSION = b"AFL1v1|"
FREE_TRIAL_UP_LIMIT = 10
FREE_TRIAL_GP_LIMIT = 10
LICENSED_EXPORTS_PER_DAY = 500
MAX_MACHINES_PER_KEY = 2
# Chu kỳ quota theo VN: mỗi “ngày quota” là [D 23:05, D+1 23:05).
_QUOTA_RESET_HOUR = 23
_QUOTA_RESET_MINUTE = 5


def normalize_free_source(source: str) -> str:
    """Nhánh quota dùng thử: uppromote | goaffpro."""
    return "goaffpro" if (source or "").strip().lower() == "goaffpro" else "uppromote"


# Giờ Việt Nam cố định UTC+7 (không DST).
_TZ_VN = timezone(timedelta(hours=7), "UTC+7")

_LICENSE_PATH: Path | None = None
_FREE_USAGE_PATH: Path | None = None
_LICENSED_USAGE_PATH: Path | None = None


def calendar_day_vietnam() -> str:
    """Mã ngày quota YYYY-MM-DD (giờ VN UTC+7): đổi chu kỳ lúc 23:05 mỗi ngày lịch."""
    now = datetime.now(_TZ_VN)
    boundary = now.replace(
        hour=_QUOTA_RESET_HOUR,
        minute=_QUOTA_RESET_MINUTE,
        second=0,
        microsecond=0,
    )
    if now < boundary:
        return (now.date() - timedelta(days=1)).isoformat()
    return now.date().isoformat()


def set_paths(base_dir: Path) -> None:
    global _LICENSE_PATH, _FREE_USAGE_PATH, _LICENSED_USAGE_PATH
    _LICENSE_PATH = base_dir / ".aff_license.json"
    _FREE_USAGE_PATH = base_dir / ".aff_free_usage.json"
    _LICENSED_USAGE_PATH = base_dir / ".aff_licensed_usage.json"


def _paths_ok() -> bool:
    return (
        _LICENSE_PATH is not None
        and _FREE_USAGE_PATH is not None
        and _LICENSED_USAGE_PATH is not None
    )


def license_hmac_secret() -> bytes | None:
    """Secret vendor: dùng xác thực key AFL1 và ký file usage (nếu có). None = không bán key nhưng vẫn giới hạn dùng thử."""
    raw = (os.getenv("AFF_LICENSE_HMAC_SECRET") or "").strip()
    if not raw:
        return None
    return raw.encode("utf-8")


def _usage_hmac_key() -> bytes:
    """Ký số lần xuất dùng thử: dùng secret vendor nếu có, không thì khóa phụ cố định theo fingerprint máy."""
    s = license_hmac_secret()
    if s:
        return s
    mfp = machine_fingerprint().encode("ascii", errors="replace")
    return hashlib.sha256(b"AFF_TRIAL_USAGE_LOCAL_v1|" + mfp).digest()


def _creationflags_no_window() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(subprocess.CREATE_NO_WINDOW)
    except AttributeError:
        return 0


def _machine_guid_windows() -> str:
    try:
        out = subprocess.check_output(
            [
                "reg",
                "query",
                r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography",
                "/v",
                "MachineGuid",
            ],
            stderr=subprocess.DEVNULL,
            timeout=6,
            text=True,
            creationflags=_creationflags_no_window(),
        )
        for line in out.splitlines():
            line = line.strip()
            if line.lower().startswith("machineguid"):
                parts = line.split(None, 2)
                if len(parts) >= 3:
                    return parts[2].strip("{} ").strip()
    except Exception:
        pass
    return ""


def _machine_id_linux() -> str:
    for p in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            t = p.read_text(encoding="utf-8").strip()
            if t:
                return t
        except OSError:
            continue
    return ""


def machine_fingerprint() -> str:
    """Chuỗi ổn định theo máy (Windows: MachineGuid; Linux: /etc/machine-id)."""
    g = ""
    if sys.platform == "win32":
        g = _machine_guid_windows()
    elif sys.platform.startswith("linux"):
        g = _machine_id_linux()
    if not g:
        import uuid

        g = str(uuid.getnode())
    raw = f"{sys.platform}|{g}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def normalize_license_key(key: str) -> str:
    s = (key or "").upper().replace(" ", "").replace("\n", "").replace("\r", "")
    s = s.replace("—", "-").replace("–", "-")
    return s


_KEY_RE = re.compile(rf"^{KEY_PREFIX}-([A-Z2-7]+)-([A-Z2-7]+)$")


def verify_license_key_shape(secret: bytes, key: str) -> bool:
    """Key hợp lệ khi HMAC(secret, AFL1v1|body) khớp phần checksum (chống giả mạo không có secret)."""
    norm = normalize_license_key(key)
    m = _KEY_RE.match(norm)
    if not m:
        return False
    body_b32, mac_b32 = m.group(1), m.group(2)
    try:
        pad = "=" * ((8 - len(body_b32) % 8) % 8)
        body = base64.b32decode(body_b32 + pad, casefold=True)
        pad2 = "=" * ((8 - len(mac_b32) % 8) % 8)
        expect = base64.b32decode(mac_b32 + pad2, casefold=True)
    except Exception:
        return False
    if len(body) < 10 or len(expect) < 4:
        return False
    msg = KEY_VERSION + body
    mac = hmac.new(secret, msg, hashlib.sha256).digest()[: len(expect)]
    return hmac.compare_digest(mac, expect)


def binding_id_for_key(secret: bytes, normalized_key: str) -> str:
    return hashlib.sha256(hmac.new(secret, normalized_key.encode("utf-8"), hashlib.sha256).digest()).hexdigest()


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_license_state() -> dict:
    if not _paths_ok():
        return {}
    return _load_json(_LICENSE_PATH)


def save_license_state(data: dict) -> None:
    if not _paths_ok():
        return
    _atomic_write(_LICENSE_PATH, data)


def is_licensed_on_this_machine() -> bool:
    secret = license_hmac_secret()
    if not secret:
        return False
    st = load_license_state()
    inst = st.get("this_install") or {}
    bid = inst.get("binding_id")
    if not bid:
        return False
    mfp = machine_fingerprint()
    machines = (st.get("per_key_machines") or {}).get(bid) or []
    return mfp in machines


def activate_key(key: str) -> tuple[bool, str]:
    secret = license_hmac_secret()
    if not secret:
        return (
            False,
            "Thiếu AFF_LICENSE_HMAC_SECRET trong .env — không thể xác thực key. "
            "Thêm secret (trùng lúc sinh key) rồi khởi động lại app.",
        )
    norm = normalize_license_key(key)
    if not verify_license_key_shape(secret, norm):
        return False, "Key không hợp lệ hoặc đã nhập sai."
    bid = binding_id_for_key(secret, norm)
    mfp = machine_fingerprint()
    st = load_license_state()
    per = dict(st.get("per_key_machines") or {})
    lst = list(per.get(bid) or [])
    if mfp in lst:
        pass
    elif len(lst) >= MAX_MACHINES_PER_KEY:
        return False, f"Key này đã kích hoạt trên {MAX_MACHINES_PER_KEY} máy khác."
    else:
        lst.append(mfp)
    per[bid] = lst
    st["per_key_machines"] = per
    st["this_install"] = {
        "binding_id": bid,
        "key_hint": norm[-8:] if len(norm) >= 8 else norm,
        "activated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    st["v"] = 1
    save_license_state(st)
    return True, "Kích hoạt thành công."


def deactivate_on_this_machine() -> tuple[bool, str]:
    """
    Gỡ kích hoạt trên máy này: xóa khỏi danh sách máy của key, xóa this_install,
    giải phóng 1 slot (tối đa 2 máy/key). Giữ file .aff_licensed_usage.json để kích hoạt lại cùng key
    không reset quota 400/ngày trong cùng ngày.
    """
    if not is_licensed_on_this_machine():
        return False, "Máy này chưa được kích hoạt."
    if not _paths_ok():
        return False, "Không ghi được trạng thái license."
    st = load_license_state()
    inst = st.get("this_install") or {}
    bid = inst.get("binding_id")
    if not bid:
        return False, "Không có thông tin kích hoạt trên máy này."
    mfp = machine_fingerprint()
    per = dict(st.get("per_key_machines") or {})
    lst = [x for x in (per.get(bid) or []) if x != mfp]
    if lst:
        per[bid] = lst
    else:
        per.pop(bid, None)
    st["per_key_machines"] = per
    st["this_install"] = {}
    st["v"] = int(st.get("v") or 1)
    save_license_state(st)
    return True, "Đã hủy kích hoạt trên máy này. Slot máy trên key được giải phóng (có thể kích hoạt lại hoặc dùng máy khác)."


def _sign_free_v1(secret: bytes, mfp: str, day: str, n: int) -> str:
    msg = f"FREv1|{mfp}|{day}|{n}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _sign_free_v3(secret: bytes, mfp: str, day: str, n_up: int, n_gp: int) -> str:
    msg = f"FREv3|{mfp}|{day}|{n_up}|{n_gp}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _sign_licensed_daily(secret: bytes, mfp: str, day: str, n: int) -> str:
    msg = f"LICv1|{mfp}|{day}|{n}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _free_v1_valid(secret: bytes, mfp: str, day: str, n: int, sig: str) -> bool:
    if not day or n < 0:
        return False
    if hmac.compare_digest(_sign_free_v1(secret, mfp, day, n), sig):
        return True
    legacy = f"{mfp}|{day}|{n}".encode("utf-8")
    return hmac.compare_digest(hmac.new(secret, legacy, hashlib.sha256).hexdigest(), sig)


def _free_v3_valid(secret: bytes, mfp: str, day: str, n_up: int, n_gp: int, sig: str) -> bool:
    if not day or n_up < 0 or n_gp < 0:
        return False
    return hmac.compare_digest(_sign_free_v3(secret, mfp, day, n_up, n_gp), sig)


def _sign_free_v4(secret: bytes, mfp: str, n_up: int, n_gp: int) -> str:
    msg = f"FREv4|{mfp}|{n_up}|{n_gp}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _free_v4_valid(secret: bytes, mfp: str, n_up: int, n_gp: int, sig: str) -> bool:
    if n_up < 0 or n_gp < 0:
        return False
    return hmac.compare_digest(_sign_free_v4(secret, mfp, n_up, n_gp), sig)


def _parse_free_trial_counts(data: dict) -> tuple[int, int]:
    """Đã dùng (uppromote, goaffpro) trong đời dùng thử; file hợp lệ v1/v3 được giữ số liệu khi nâng quota."""
    if not data:
        return 0, 0
    key = _usage_hmac_key()
    mfp = machine_fingerprint()
    v = int(data.get("v") or 0)
    if v == 4:
        n_up = int(data.get("n_up", 0))
        n_gp = int(data.get("n_gp", 0))
        sig = str(data.get("sig") or "")
        if _free_v4_valid(key, mfp, n_up, n_gp, sig):
            return min(FREE_TRIAL_UP_LIMIT, n_up), min(FREE_TRIAL_GP_LIMIT, n_gp)
        return FREE_TRIAL_UP_LIMIT, FREE_TRIAL_GP_LIMIT
    if v == 3:
        day = str(data.get("day") or "")
        n_up = int(data.get("n_up", 0))
        n_gp = int(data.get("n_gp", 0))
        sig = str(data.get("sig") or "")
        if day and _free_v3_valid(key, mfp, day, n_up, n_gp, sig):
            return min(FREE_TRIAL_UP_LIMIT, n_up), min(FREE_TRIAL_GP_LIMIT, n_gp)
        return FREE_TRIAL_UP_LIMIT, FREE_TRIAL_GP_LIMIT
    day = str(data.get("day") or "")
    n_old = int(data.get("n") or 0)
    sig_old = str(data.get("sig") or "")
    if day and _free_v1_valid(key, mfp, day, n_old, sig_old):
        return min(FREE_TRIAL_UP_LIMIT, n_old), 0
    return FREE_TRIAL_UP_LIMIT, FREE_TRIAL_GP_LIMIT


def _load_licensed_usage() -> tuple[str, int, str]:
    if not _paths_ok():
        return "", 0, ""
    data = _load_json(_LICENSED_USAGE_PATH)
    return (str(data.get("day") or ""), int(data.get("n") or 0), str(data.get("sig") or ""))


def _licensed_usage_valid(secret: bytes, mfp: str, day: str, n: int, sig: str) -> bool:
    if not day or n < 0:
        return False
    return hmac.compare_digest(_sign_licensed_daily(secret, mfp, day, n), sig)


def free_branch_used_today(source: str) -> int:
    """Số record đã xuất trên nhánh dùng thử (uppromote | goaffpro), trọn đời trên máy."""
    if is_licensed_on_this_machine():
        return 0
    data = _load_json(_FREE_USAGE_PATH) if _paths_ok() else {}
    n_up, n_gp = _parse_free_trial_counts(data)
    return n_gp if normalize_free_source(source) == "goaffpro" else n_up


def free_exports_remaining_today(source: str) -> int:
    if is_licensed_on_this_machine():
        return 10**9
    lim = (
        FREE_TRIAL_GP_LIMIT
        if normalize_free_source(source) == "goaffpro"
        else FREE_TRIAL_UP_LIMIT
    )
    return max(0, lim - free_branch_used_today(source))


def licensed_exports_used_today() -> int:
    if not is_licensed_on_this_machine():
        return 0
    key = _usage_hmac_key()
    mfp = machine_fingerprint()
    today = calendar_day_vietnam()
    day, n, sig = _load_licensed_usage()
    if day != today:
        return 0
    if not _licensed_usage_valid(key, mfp, day, n, sig):
        return LICENSED_EXPORTS_PER_DAY
    return min(n, LICENSED_EXPORTS_PER_DAY)


def licensed_exports_remaining_today() -> int:
    if not is_licensed_on_this_machine():
        return 10**9
    return max(0, LICENSED_EXPORTS_PER_DAY - licensed_exports_used_today())


def record_free_export_rows(count: int, source: str) -> None:
    if count <= 0 or is_licensed_on_this_machine() or not _paths_ok():
        return
    key = _usage_hmac_key()
    mfp = machine_fingerprint()
    data = _load_json(_FREE_USAGE_PATH)
    n_up, n_gp = _parse_free_trial_counts(data)
    br = normalize_free_source(source)
    if br == "goaffpro":
        n_gp = min(FREE_TRIAL_GP_LIMIT, n_gp + count)
    else:
        n_up = min(FREE_TRIAL_UP_LIMIT, n_up + count)
    out = {
        "v": 4,
        "n_up": n_up,
        "n_gp": n_gp,
        "sig": _sign_free_v4(key, mfp, n_up, n_gp),
    }
    _atomic_write(_FREE_USAGE_PATH, out)


def record_licensed_export_rows(count: int) -> None:
    if count <= 0 or not is_licensed_on_this_machine() or not _paths_ok():
        return
    key = _usage_hmac_key()
    mfp = machine_fingerprint()
    today = calendar_day_vietnam()
    day, n, sig = _load_licensed_usage()
    if day != today or not _licensed_usage_valid(key, mfp, day, n, sig):
        n = 0
        day = today
    n2 = min(LICENSED_EXPORTS_PER_DAY, n + count)
    out = {"day": day, "n": n2, "sig": _sign_licensed_daily(key, mfp, day, n2)}
    _atomic_write(_LICENSED_USAGE_PATH, out)


def record_one_exported_row(source: str) -> None:
    """Mỗi dòng đã ghi vào Excel trong pipeline (đếm quota free hoặc licensed)."""
    if is_licensed_on_this_machine():
        record_licensed_export_rows(1)
    else:
        record_free_export_rows(1, source)


def export_offer_cap(total_offers: int, source: str) -> int:
    """Số offer được xuất tối đa trong lần chạy (theo quota còn lại: dùng thử trọn đời / bản quyền theo ngày VN)."""
    if is_licensed_on_this_machine():
        return min(total_offers, licensed_exports_remaining_today())
    return min(total_offers, free_exports_remaining_today(source))


def assert_can_start_pipeline(source: str) -> tuple[bool, str]:
    """Trước khi chạy pipeline: chặn nếu hết quota (dùng thử trọn đời hoặc bản quyền theo ngày VN)."""
    if is_licensed_on_this_machine():
        if licensed_exports_remaining_today() <= 0:
            return False, (
                f"Đã kích hoạt nhưng đã dùng hết {LICENSED_EXPORTS_PER_DAY} record hôm nay "
                "(theo giờ Việt Nam UTC+7, reset lúc 23h05). Thử lại sau."
            )
        return True, ""
    if free_exports_remaining_today(source) <= 0:
        lab = "Goaffpro" if normalize_free_source(source) == "goaffpro" else "Uppromote"
        cap = FREE_TRIAL_GP_LIMIT if normalize_free_source(source) == "goaffpro" else FREE_TRIAL_UP_LIMIT
        return False, (
            f"Bản chưa kích hoạt: đã dùng hết {cap} record dùng thử {lab} trên máy này "
            f"(tối đa {FREE_TRIAL_UP_LIMIT} Uppromote + {FREE_TRIAL_GP_LIMIT} Goaffpro, không reset). "
            "Thử nguồn còn lại hoặc kích hoạt key."
        )
    return True, ""


def zero_export_cap_log_message(source: str) -> str:
    """Thông báo khi cap == 0 trước pipeline."""
    if is_licensed_on_this_machine():
        return (
            f"Đã dùng hết {LICENSED_EXPORTS_PER_DAY} record hôm nay (giờ Việt Nam UTC+7, reset 23h05). "
            "Thử lại ngày mai."
        )
    lab = "Goaffpro" if normalize_free_source(source) == "goaffpro" else "Uppromote"
    cap = FREE_TRIAL_GP_LIMIT if normalize_free_source(source) == "goaffpro" else FREE_TRIAL_UP_LIMIT
    return (
        f"Đã hết {cap} record dùng thử {lab} trên máy này (không reset theo thời gian). "
        "Thử nguồn còn lại hoặc kích hoạt key."
    )


def export_cap_partial_log(total_offers: int, cap: int, source: str) -> str:
    if cap >= total_offers:
        return ""
    if is_licensed_on_this_machine():
        return (
            f"Giới hạn bản đã kích hoạt: chỉ xử lý {cap}/{total_offers} offer trong lần chạy này "
            f"(tối đa {LICENSED_EXPORTS_PER_DAY} record / ngày / máy, reset 23h05 giờ Việt Nam UTC+7; "
            f"lần này chỉ còn quota {cap} record)."
        )
    lab = "Goaffpro" if normalize_free_source(source) == "goaffpro" else "Uppromote"
    br_cap = FREE_TRIAL_GP_LIMIT if normalize_free_source(source) == "goaffpro" else FREE_TRIAL_UP_LIMIT
    return (
        f"Giới hạn bản dùng thử ({lab}): chỉ xử lý {cap}/{total_offers} offer trong lần chạy này "
        f"(tối đa {br_cap} record {lab} trên máy, không reset)."
    )


def license_status_payload() -> dict:
    secret = license_hmac_secret()
    mfp = machine_fingerprint()
    licensed = is_licensed_on_this_machine()
    rem_up = free_exports_remaining_today("uppromote")
    rem_gp = free_exports_remaining_today("goaffpro")
    used_up = free_branch_used_today("uppromote")
    used_gp = free_branch_used_today("goaffpro")
    lic_used = licensed_exports_used_today() if licensed else 0
    lic_rem = licensed_exports_remaining_today() if licensed else None
    if licensed:
        msg = (
            f"Đã kích hoạt — còn {lic_rem}/{LICENSED_EXPORTS_PER_DAY} record hôm nay "
            "(giờ Việt Nam UTC+7, reset 23h05)."
        )
    elif not secret:
        msg = (
            f"Chưa kích hoạt — dùng thử trọn đời: Uppromote còn {rem_up}/{FREE_TRIAL_UP_LIMIT}, "
            f"Goaffpro còn {rem_gp}/{FREE_TRIAL_GP_LIMIT} record (không reset). "
            "Thêm AFF_LICENSE_HMAC_SECRET vào .env để khách nhập key đã mua."
        )
    else:
        msg = (
            f"Chưa kích hoạt — dùng thử: Uppromote còn {rem_up}/{FREE_TRIAL_UP_LIMIT}, "
            f"Goaffpro còn {rem_gp}/{FREE_TRIAL_GP_LIMIT} record (không reset theo thời gian)."
        )
    return {
        "enforcement": True,
        "vendor_secret_configured": bool(secret),
        "licensed": licensed,
        "machine_id": mfp,
        "timezone_note": (
            "Bản quyền: ngày quota giờ Việt Nam (UTC+7), đổi chu kỳ 23h05."
            if licensed
            else "Dùng thử: không reset theo ngày; bản kích hoạt có quota theo ngày (VN UTC+7, 23h05)."
        ),
        "free_trial_up_limit": FREE_TRIAL_UP_LIMIT,
        "free_trial_gp_limit": FREE_TRIAL_GP_LIMIT,
        "free_used_uppromote": 0 if licensed else used_up,
        "free_used_goaffpro": 0 if licensed else used_gp,
        "free_remaining_uppromote": None if licensed else rem_up,
        "free_remaining_goaffpro": None if licensed else rem_gp,
        "free_used_trial_total": 0 if licensed else used_up + used_gp,
        "free_used_uppromote_today": 0 if licensed else used_up,
        "free_used_goaffpro_today": 0 if licensed else used_gp,
        "free_remaining_uppromote_today": None if licensed else rem_up,
        "free_remaining_goaffpro_today": None if licensed else rem_gp,
        "free_remaining_today": None if licensed else min(rem_up, rem_gp),
        "licensed_daily_limit": LICENSED_EXPORTS_PER_DAY,
        "licensed_used_today": lic_used if licensed else 0,
        "licensed_remaining_today": lic_rem,
        "max_machines_per_key": MAX_MACHINES_PER_KEY,
        "message": msg,
    }


def should_track_free_usage() -> bool:
    return not is_licensed_on_this_machine()
