"""
Máy chủ quản lý slot kích hoạt key AFL1 (đếm máy / key trên DB).

Chạy (từ thư mục gốc project, đã export biến môi trường hoặc có .env):

  set AFF_LICENSE_HMAC_SECRET=...   (trùng secret lúc sinh key)
  set LICENSE_ADMIN_PASSWORD=...    (mật khẩu giao diện admin)
  python -m license_server.app

Biến tùy chọn:
  LICENSE_SERVER_DATABASE — đường dẫn file sqlite (mặc định: ./data/license_slots.db), bỏ qua nếu dùng MySQL
  LICENSE_DB_DRIVER=mysql — hoặc đặt MYSQL_HOST để dùng MySQL (cần pip install pymysql)
  MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE, MYSQL_CHARSET
  MAX_MACHINES_PER_KEY — số máy tối đa / key (mặc định 2)
  FLASK_SECRET_KEY — session admin (mặc định: đổi ngay trên production)
  LICENSE_SERVER_HOST, LICENSE_SERVER_PORT — mặc định 0.0.0.0:8765
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sys
import time
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

# Gốc project (cha của thư mục license_server)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_root_dotenv() -> None:
    p = ROOT / ".env"
    if not p.is_file():
        return
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        v = v.strip().strip("\r")
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k and k not in os.environ:
            os.environ[k] = v


_load_root_dotenv()

import license_guard as lg

from license_server.db import get_store


def _activation_sig(secret: bytes, binding_id: str, machine_fingerprint: str, ts: str) -> str:
    msg = f"REMOTEv1|{binding_id}|{machine_fingerprint}|{ts}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()

app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent / "templates"))
app.secret_key = (os.getenv("FLASK_SECRET_KEY") or "").strip() or secrets.token_hex(32)


def _max_machines() -> int:
    try:
        return max(1, min(32, int(os.getenv("MAX_MACHINES_PER_KEY", "2"))))
    except ValueError:
        return 2


def _admin_password() -> str:
    return (os.getenv("LICENSE_ADMIN_PASSWORD") or "").strip()


def _store():
    return get_store(ROOT)


def _require_secret_configured():
    if not lg.license_hmac_secret():
        return jsonify({"ok": False, "error": "Server thiếu AFF_LICENSE_HMAC_SECRET."}), 500
    return None


@app.post("/v1/activate")
def api_v1_activate():
    err = _require_secret_configured()
    if err:
        return err
    data = request.get_json(force=True, silent=True) or {}
    key = lg.normalize_license_key(str(data.get("license_key") or ""))
    mfp = str(data.get("machine_fingerprint") or "").strip()
    if not key or not mfp:
        return jsonify({"ok": False, "error": "Thiếu license_key hoặc machine_fingerprint."}), 400

    secret = lg.license_hmac_secret()
    assert secret is not None
    if not lg.verify_license_key_shape(secret, key):
        return jsonify({"ok": False, "error": "Key không hợp lệ hoặc sai."}), 400

    bid = lg.binding_id_for_key(secret, key)
    hint = key[-8:] if len(key) >= 8 else key
    store = _store()
    max_m = _max_machines()

    if store.has_machine(bid, mfp):
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        sig = _activation_sig(secret, bid, mfp, ts)
        return jsonify(
            {
                "ok": True,
                "binding_id": bid,
                "key_hint": hint,
                "machines_active": store.count_for_binding(bid),
                "machines_max": max_m,
                "already_active": True,
                "activation_ts": ts,
                "activation_sig": sig,
            }
        )

    n = store.count_for_binding(bid)
    if n >= max_m:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": f"Key đã kích hoạt đủ {max_m} máy. Hủy trên một máy hoặc xóa slot trên admin.",
                }
            ),
            403,
        )

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    store.insert_activation(bid, mfp, hint, ts)
    sig = _activation_sig(secret, bid, mfp, ts)
    return jsonify(
        {
            "ok": True,
            "binding_id": bid,
            "key_hint": hint,
            "machines_active": store.count_for_binding(bid),
            "machines_max": max_m,
            "already_active": False,
            "activation_ts": ts,
            "activation_sig": sig,
        }
    )


@app.post("/v1/deactivate")
def api_v1_deactivate():
    data = request.get_json(force=True, silent=True) or {}
    mfp = str(data.get("machine_fingerprint") or "").strip()
    bid = str(data.get("binding_id") or "").strip()
    store = _store()

    if bid and mfp:
        removed = store.delete_by_binding_and_machine(bid, mfp)
        if removed == 0:
            return jsonify(
                {
                    "ok": True,
                    "removed": False,
                    "message": "Không có slot nào khớp (có thể đã gỡ trước đó).",
                }
            )
        return jsonify({"ok": True, "removed": True, "message": "Đã gỡ slot trên server."})

    key = lg.normalize_license_key(str(data.get("license_key") or ""))
    if not key or not mfp:
        return jsonify(
            {"ok": False, "error": "Gửi binding_id + machine_fingerprint hoặc license_key + machine_fingerprint."},
            400,
        )

    err = _require_secret_configured()
    if err:
        return err
    secret = lg.license_hmac_secret()
    assert secret is not None
    if not lg.verify_license_key_shape(secret, key):
        return jsonify({"ok": False, "error": "Key không hợp lệ hoặc sai."}), 400

    bid2 = lg.binding_id_for_key(secret, key)
    removed = store.delete_by_binding_and_machine(bid2, mfp)
    if removed == 0:
        return jsonify({"ok": True, "removed": False, "message": "Không có slot nào khớp (có thể đã gỡ trước đó)."})
    return jsonify({"ok": True, "removed": True, "message": "Đã gỡ slot trên server."})


@app.get("/")
def index():
    """Trang gốc — trước đây không có route nên GET / trả 404."""
    return render_template("home.html")


@app.get("/v1/health")
def api_v1_health():
    return jsonify({"ok": True, "service": "aff-license-slots"})


def _admin_ok() -> bool:
    return bool(session.get("admin"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    pw = _admin_password()
    if not pw:
        return (
            "Cấu hình LICENSE_ADMIN_PASSWORD trên server để dùng admin.",
            503,
        )
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("password") or "", pw):
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Sai mật khẩu."), 401
    return render_template("admin_login.html", error=None)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/admin/")
def admin_dashboard():
    if not _admin_ok():
        return redirect(url_for("admin_login"))
    store = _store()
    rows = store.list_all()
    by_binding: dict[str, list[dict]] = {}
    for r in rows:
        by_binding.setdefault(r["binding_id"], []).append(r)
    return render_template(
        "admin_dashboard.html",
        rows=rows,
        by_binding=by_binding,
        max_machines=_max_machines(),
        db_info=store.connection_info(),
    )


@app.post("/admin/revoke/<int:row_id>")
def admin_revoke(row_id: int):
    if not _admin_ok():
        return redirect(url_for("admin_login"))
    _store().delete_by_id(row_id)
    return redirect(url_for("admin_dashboard"))


def main():
    host = (os.getenv("LICENSE_SERVER_HOST") or "0.0.0.0").strip()
    port = int(os.getenv("LICENSE_SERVER_PORT", "8765") or "8765")
    if not lg.license_hmac_secret():
        print("Cảnh báo: thiếu AFF_LICENSE_HMAC_SECRET — API activate sẽ trả 500.", file=sys.stderr)
    if not _admin_password():
        print("Cảnh báo: thiếu LICENSE_ADMIN_PASSWORD — /admin không đăng nhập được.", file=sys.stderr)
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
