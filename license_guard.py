"""
License guard (Python client):
- Không tự quản lý key shape/HMAC ở Python nữa.
- Kích hoạt / hủy kích hoạt / kiểm tra key qua API Laravel.
- Python chỉ giữ trạng thái activation local + quota local.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time

try:
    import requests
except ImportError:
    requests = None  # type: ignore
from datetime import datetime, timedelta, timezone
from pathlib import Path

FREE_TRIAL_UP_LIMIT = 3
FREE_TRIAL_GP_LIMIT = 3
DEFAULT_LICENSED_EXPORTS_PER_DAY = 500
# Chu kỳ quota theo VN: reset đúng 00:00 mỗi ngày lịch.
SUPPORTED_SOURCES = {"uppromote", "goaffpro", "refersion", "collabs"}
ALL_SOURCES = ["uppromote", "goaffpro", "refersion", "collabs"]
DEFAULT_LICENSED_SOURCES = ["uppromote", "goaffpro"]


def normalize_free_source(source: str) -> str:
    """Nhánh quota dùng thử: uppromote | goaffpro."""
    return "goaffpro" if (source or "").strip().lower() == "goaffpro" else "uppromote"


def normalize_source(source: str) -> str:
    s = (source or "").strip().lower()
    return s if s in SUPPORTED_SOURCES else "uppromote"


def normalize_allowed_sources(raw) -> list[str]:
    if not isinstance(raw, list):
        return list(DEFAULT_LICENSED_SOURCES)
    out: list[str] = []
    for item in raw:
        s = normalize_source(str(item))
        if s in SUPPORTED_SOURCES and s not in out:
            out.append(s)
    return out if out else list(DEFAULT_LICENSED_SOURCES)


def source_label(source: str) -> str:
    s = normalize_source(source)
    return (
        "Goaffpro"
        if s == "goaffpro"
        else ("Refersion" if s == "refersion" else ("Shopify Collabs" if s == "collabs" else "Uppromote"))
    )


# Giờ Việt Nam cố định UTC+7 (không DST).
_TZ_VN = timezone(timedelta(hours=7), "UTC+7")

_LICENSE_PATH: Path | None = None
_FREE_USAGE_PATH: Path | None = None
_LICENSED_USAGE_PATH: Path | None = None


def calendar_day_vietnam() -> str:
    """Mã ngày quota YYYY-MM-DD (giờ VN UTC+7), reset đúng 00:00."""
    return datetime.now(_TZ_VN).date().isoformat()


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


def license_api_base_url() -> str:
    """Ưu tiên AFF_LICENSE_API_BASE_URL; fallback AFF_LICENSE_SERVER_URL để tương thích cũ."""
    return (
        (os.getenv("AFF_LICENSE_API_BASE_URL") or os.getenv("AFF_LICENSE_SERVER_URL") or "")
        .strip()
        .rstrip("/")
    )


def license_api_token() -> str:
    return (os.getenv("AFF_LICENSE_API_TOKEN") or "").strip()


def licensed_exports_per_day() -> int:
    raw = (os.getenv("AFF_LICENSE_DAILY_LIMIT") or "").strip()
    if not raw:
        return DEFAULT_LICENSED_EXPORTS_PER_DAY
    try:
        n = int(raw)
    except ValueError:
        return DEFAULT_LICENSED_EXPORTS_PER_DAY
    return max(1, n)


def _usage_hmac_key() -> bytes:
    """Ký usage local bằng key theo fingerprint máy."""
    mfp = machine_fingerprint().encode("ascii", errors="replace")
    return hashlib.sha256(b"AFF_TRIAL_USAGE_LOCAL_v2|" + mfp).digest()


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


def _license_server_post_json(url: str, payload: dict, timeout_sec: float = 28.0) -> tuple[bool, dict | str]:
    if not requests:
        return False, "Thiếu thư viện requests — cài: pip install requests"
    headers = {"Content-Type": "application/json"}
    token = license_api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=timeout_sec)
    except requests.RequestException as exc:
        return False, f"Không kết nối được máy chủ license: {exc}"
    try:
        data = res.json()
    except Exception:
        return False, f"Máy chủ license trả HTTP {res.status_code} (không phải JSON)."
    if not isinstance(data, dict):
        return False, f"Máy chủ license lỗi HTTP {res.status_code}."
    return True, data


def _activate_via_license_server(norm_key: str) -> tuple[bool, str]:
    base = license_api_base_url()
    if not base:
        return False, "Thiếu AFF_LICENSE_API_BASE_URL (hoặc AFF_LICENSE_SERVER_URL)."
    mfp = machine_fingerprint()
    url = f"{base}/api/v1/licenses/activate"
    ok, data = _license_server_post_json(
        url,
        {
            "license_key": norm_key,
            "machine_fingerprint": mfp,
            "client": "python-filter",
        },
    )
    if not ok:
        assert isinstance(data, str)
        return False, data
    assert isinstance(data, dict)
    if not data.get("ok"):
        return False, str(data.get("error") or "Server từ chối kích hoạt.")
    activation_id = str(data.get("activation_id") or "")
    if not activation_id:
        return False, "Server không trả activation_id."
    hint = str(data.get("key_hint") or (norm_key[-6:] if len(norm_key) >= 6 else norm_key))
    daily_limit = int(data.get("daily_limit") or licensed_exports_per_day())
    expires_at = str(data.get("expires_at") or "")
    usage_day = str(data.get("usage_day") or calendar_day_vietnam())
    used_today = max(0, int(data.get("used_today") or 0))
    st = load_license_state()
    st["this_install"] = {
        "activation_id": activation_id,
        "key_hint": hint,
        "machine_fingerprint": mfp,
        "daily_limit": max(1, daily_limit),
        "allowed_sources": normalize_allowed_sources(data.get("allowed_sources")),
        "expires_at": expires_at,
        "activated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    st["v"] = 1
    save_license_state(st)
    _save_licensed_usage(usage_day, used_today)
    return True, "Kích hoạt thành công (đã đăng ký slot trên server)."


def _deactivate_via_license_server(binding_id: str, machine_fp: str) -> tuple[bool, str]:
    base = license_api_base_url()
    url = f"{base}/api/v1/licenses/deactivate"
    ok, data = _license_server_post_json(
        url, {"activation_id": binding_id, "machine_fingerprint": machine_fp}
    )
    if not ok:
        assert isinstance(data, str)
        return False, data
    assert isinstance(data, dict)
    if not data.get("ok"):
        return False, str(data.get("error") or "Server từ chối hủy kích hoạt.")
    return True, str(data.get("message") or "Đã gỡ slot trên server.")


def _validate_via_license_server(activation_id: str, machine_fp: str) -> tuple[bool, dict | str]:
    base = license_api_base_url()
    if not base:
        return False, "Thiếu AFF_LICENSE_API_BASE_URL (hoặc AFF_LICENSE_SERVER_URL)."
    url = f"{base}/api/v1/licenses/validate"
    return _license_server_post_json(
        url,
        {"activation_id": activation_id, "machine_fingerprint": machine_fp},
    )


def _sync_usage_via_license_server(
    activation_id: str,
    machine_fp: str,
    usage_day: str,
    used_total: int,
) -> tuple[bool, dict | str]:
    base = license_api_base_url()
    if not base:
        return False, "Thiếu AFF_LICENSE_API_BASE_URL (hoặc AFF_LICENSE_SERVER_URL)."
    url = f"{base}/api/v1/licenses/usage/sync"
    return _license_server_post_json(
        url,
        {
            "activation_id": activation_id,
            "machine_fingerprint": machine_fp,
            "usage_day": usage_day,
            "used_total": max(0, int(used_total)),
        },
    )


def _sync_this_install_from_server() -> tuple[bool, str]:
    """
    Đồng bộ trạng thái activation local (đặc biệt daily_limit) từ Laravel server.
    Trả về (ok, message). ok=False khi key không còn hợp lệ hoặc lỗi kết nối/xác thực.
    """
    st = load_license_state()
    inst = st.get("this_install") or {}
    activation_id = str(inst.get("activation_id") or "").strip()
    if not activation_id:
        return False, "Thiếu activation_id local."

    mfp = machine_fingerprint()
    ok_remote, remote_data = _validate_via_license_server(activation_id, mfp)
    if not ok_remote:
        assert isinstance(remote_data, str)
        return False, remote_data
    assert isinstance(remote_data, dict)
    if not remote_data.get("ok"):
        st["this_install"] = {}
        save_license_state(st)
        return False, str(remote_data.get("error") or "Key không còn hiệu lực trên server.")

    daily_limit = int(remote_data.get("daily_limit") or _effective_daily_limit())
    usage_day = str(remote_data.get("usage_day") or calendar_day_vietnam())
    used_today = max(0, int(remote_data.get("used_today") or 0))
    st["this_install"] = {
        **inst,
        "daily_limit": max(1, daily_limit),
        "allowed_sources": normalize_allowed_sources(remote_data.get("allowed_sources") or inst.get("allowed_sources")),
        "expires_at": str(remote_data.get("expires_at") or inst.get("expires_at") or ""),
        "machine_fingerprint": mfp,
    }
    save_license_state(st)
    _save_licensed_usage(usage_day, used_today)
    return True, ""


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
    st = load_license_state()
    inst = st.get("this_install") or {}
    activation_id = str(inst.get("activation_id") or "")
    if not activation_id:
        return False
    mfp = machine_fingerprint()
    if str(inst.get("machine_fingerprint") or "") != mfp:
        return False
    expires_at = str(inst.get("expires_at") or "").strip()
    if not expires_at:
        return True
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return expiry > datetime.now(timezone.utc)


def activate_key(key: str) -> tuple[bool, str]:
    norm = normalize_license_key(key)
    return _activate_via_license_server(norm)


def deactivate_on_this_machine() -> tuple[bool, str]:
    """
    Hủy kích hoạt máy hiện tại trên Laravel API và xóa trạng thái local.
    Giữ file .aff_licensed_usage.json để không reset quota ngày hiện tại khi kích hoạt lại.
    """
    if not _paths_ok():
        return False, "Không ghi được trạng thái license."
    if not is_licensed_on_this_machine():
        return False, "Máy này chưa được kích hoạt."
    st = load_license_state()
    inst = st.get("this_install") or {}
    bid = str(inst.get("activation_id") or "")
    if not bid:
        return False, "Không có thông tin kích hoạt trên máy này."
    mfp = machine_fingerprint()
    ok, msg = _deactivate_via_license_server(bid, mfp)
    if not ok:
        return False, msg
    st["this_install"] = {}
    st["v"] = int(st.get("v") or 1)
    save_license_state(st)
    return True, "Đã hủy kích hoạt trên máy này."


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


def _save_licensed_usage(day: str, used_total: int) -> None:
    if not _paths_ok():
        return
    key = _usage_hmac_key()
    mfp = machine_fingerprint()
    n = max(0, int(used_total))
    out = {"day": day, "n": n, "sig": _sign_licensed_daily(key, mfp, day, n)}
    _atomic_write(_LICENSED_USAGE_PATH, out)


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
    daily_limit = _effective_daily_limit()
    if not _licensed_usage_valid(key, mfp, day, n, sig):
        return daily_limit
    return min(n, daily_limit)


def licensed_exports_remaining_today() -> int:
    if not is_licensed_on_this_machine():
        return 10**9
    return max(0, _effective_daily_limit() - licensed_exports_used_today())


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


def record_licensed_export_rows(count: int, source: str = "") -> None:
    if count <= 0 or not is_licensed_on_this_machine() or not _paths_ok():
        return
    key = _usage_hmac_key()
    mfp = machine_fingerprint()
    today = calendar_day_vietnam()
    day, n, sig = _load_licensed_usage()
    if day != today or not _licensed_usage_valid(key, mfp, day, n, sig):
        n = 0
        day = today
    n2 = min(_effective_daily_limit(), n + count)
    _save_licensed_usage(day, n2)

    st = load_license_state()
    activation_id = str((st.get("this_install") or {}).get("activation_id") or "").strip()
    if not activation_id:
        return
    ok_remote, remote = _sync_usage_via_license_server(activation_id, mfp, day, n2)
    if not ok_remote or not isinstance(remote, dict) or not remote.get("ok"):
        return
    remote_day = str(remote.get("usage_day") or day)
    remote_used = max(0, int(remote.get("used_today") or n2))
    # Đồng bộ lại local theo số liệu server để tránh reset quota khi file local bị xóa/sửa.
    _save_licensed_usage(remote_day, remote_used)


def record_one_exported_row(source: str) -> None:
    """Mỗi dòng đã ghi vào Excel trong pipeline (đếm quota free hoặc licensed)."""
    if is_licensed_on_this_machine():
        record_licensed_export_rows(1, source)
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
        ok_sync, sync_msg = _sync_this_install_from_server()
        if not ok_sync:
            return False, f"Không xác thực được key với License API: {sync_msg}"

    if is_licensed_on_this_machine():
        if licensed_exports_remaining_today() <= 0:
            return False, (
                f"Đã kích hoạt nhưng đã dùng hết {_effective_daily_limit()} record hôm nay "
                "(theo giờ Việt Nam UTC+7, reset lúc 00:00). Thử lại sau."
            )
        st = load_license_state()
        inst = st.get("this_install") or {}
        allowed_sources = normalize_allowed_sources(inst.get("allowed_sources"))
        src = normalize_source(source)
        if src not in allowed_sources:
            allowed_text = ", ".join(source_label(s) for s in allowed_sources)
            return False, (
                f"Key hiện tại không được cấp quyền chạy {source_label(src)}. "
                f"Các net được phép: {allowed_text}."
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
            f"Đã dùng hết {_effective_daily_limit()} record hôm nay (giờ Việt Nam UTC+7, reset 00:00). "
            "Thử lại ngày mai."
        )
    lab = "Goaffpro" if normalize_free_source(source) == "goaffpro" else "Uppromote"
    cap = FREE_TRIAL_GP_LIMIT if normalize_free_source(source) == "goaffpro" else FREE_TRIAL_UP_LIMIT
    return (
        f"Đã hết {cap} record dùng thử {lab} trên máy này. "
        "Thử nguồn còn lại hoặc kích hoạt key."
    )


def export_cap_partial_log(total_offers: int, cap: int, source: str) -> str:
    if cap >= total_offers:
        return ""
    if is_licensed_on_this_machine():
        return (
            f"Giới hạn bản đã kích hoạt: chỉ xử lý {cap}/{total_offers} offer trong lần chạy này "
            f"(tối đa {_effective_daily_limit()} record / ngày / máy, reset 00:00 giờ Việt Nam UTC+7; "
            f"lần này chỉ còn quota {cap} record)."
        )
    lab = "Goaffpro" if normalize_free_source(source) == "goaffpro" else "Uppromote"
    br_cap = FREE_TRIAL_GP_LIMIT if normalize_free_source(source) == "goaffpro" else FREE_TRIAL_UP_LIMIT
    return (
        f"Giới hạn bản dùng thử ({lab}): chỉ xử lý {cap}/{total_offers} offer trong lần chạy này "
        f"(tối đa {br_cap} record {lab} trên máy, không reset)."
    )


def license_status_payload() -> dict:
    mfp = machine_fingerprint()
    sync_error = ""
    if is_licensed_on_this_machine():
        ok_sync, sync_msg = _sync_this_install_from_server()
        if not ok_sync:
            sync_error = sync_msg
    licensed = is_licensed_on_this_machine()
    st = load_license_state()
    inst = st.get("this_install") or {}
    allowed_sources = normalize_allowed_sources(inst.get("allowed_sources"))
    srv = bool(license_api_base_url())
    activation_mode = "remote" if licensed else "none"
    rem_up = free_exports_remaining_today("uppromote")
    rem_gp = free_exports_remaining_today("goaffpro")
    used_up = free_branch_used_today("uppromote")
    used_gp = free_branch_used_today("goaffpro")
    lic_used = licensed_exports_used_today() if licensed else 0
    lic_rem = licensed_exports_remaining_today() if licensed else None
    if licensed:
        msg = (
            f"Đã kích hoạt — còn {lic_rem}/{_effective_daily_limit()} record hôm nay "
            "(reset 00:00)."
        )
    else:
        msg = (
            f"Chưa kích hoạt — dùng thử: Uppromote còn {rem_up}/{FREE_TRIAL_UP_LIMIT}, "
            f"Goaffpro còn {rem_gp}/{FREE_TRIAL_GP_LIMIT} record."
        )
    if srv and not licensed:
        msg += " Kích hoạt / hủy kích hoạt cần internet."
    if sync_error and licensed:
        msg += f" (Chưa đồng bộ được limit mới từ server: {sync_error})"
    return {
        "enforcement": True,
        "vendor_secret_configured": bool(license_api_token()),
        "license_server_configured": srv,
        "license_activation_mode": activation_mode,
        "licensed": licensed,
        "machine_id": mfp,
        "timezone_note": (
            "Bản quyền (Laravel): ngày quota giờ Việt Nam (UTC+7), đổi chu kỳ 00:00."
            if licensed
            else "Dùng thử: không reset theo ngày; bản kích hoạt có quota theo ngày (VN UTC+7, 00:00)."
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
        "licensed_daily_limit": _effective_daily_limit(),
        "licensed_used_today": lic_used if licensed else 0,
        "licensed_remaining_today": lic_rem,
        "max_machines_per_key": None,
        "activation_id": inst.get("activation_id") if licensed else None,
        "allowed_sources": allowed_sources if licensed else list(ALL_SOURCES),
        "message": msg,
    }


def should_track_free_usage() -> bool:
    return not is_licensed_on_this_machine()


def _effective_daily_limit() -> int:
    st = load_license_state()
    inst = st.get("this_install") or {}
    v = inst.get("daily_limit")
    try:
        n = int(v)
    except (TypeError, ValueError):
        return licensed_exports_per_day()
    return max(1, n)
