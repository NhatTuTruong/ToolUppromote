# Build, license key và lệnh phát triển

Tài liệu dành cho người phát triển / đóng gói ứng dụng **Lọc offer affiliate** (Uppromote / Goaffpro + traffic qua Apify).

## Yêu cầu môi trường

- Python 3.10+ (khuyến nghị bản ổn định mới nhất trên Windows).
- Thư mục làm việc: gốc project (cùng cấp với `webapp.py`, `filter.py`).

Cài dependency chạy app:

```bash
python -m pip install -r requirements.txt
```

Chỉ khi đóng gói `.exe`:

```bash
python -m pip install -r requirements.txt -r requirements-build.txt
```

## Chạy khi phát triển

- **Giao diện web (Flask)** — mở trình duyệt tại `http://127.0.0.1:5050`:

```bash
python webapp.py
```

- **Bản desktop (webview + server nội bộ)**:

```bash
python desktop_app.py
```

File cấu hình `.env` nằm cùng thư mục làm việc của app (xem `runtime_paths.app_dir()` — thường là thư mục chứa `.exe` khi đóng gói, hoặc thư mục project khi chạy `python webapp.py`).

## Đóng gói Windows (.exe)

Trên Windows, từ thư mục gốc project:

```bat
build_exe.bat
```

Script sẽ cài dependency và gọi PyInstaller với `build_exe.spec`. Kết quả: `dist\AffiliateOfferFilter.exe`.

**Lưu ý khi phát hành bản build:**

- Đặt file `.env` (token Apify, URL API, `AFF_LICENSE_HMAC_SECRET` nếu bán key, …) **cùng thư mục** với file `.exe`.
- Không đóng gói sẵn các file trạng thái cá nhân (để người dùng bắt đầu sạch):  
  `.aff_license.json`, `.aff_free_usage.json`, `.aff_licensed_usage.json`.

## Bản quyền và sinh key (vendor)

1. Trong `.env` của **máy vendor**, đặt secret đủ mạnh (tối thiểu 16 ký tự):

   ```env
   AFF_LICENSE_HMAC_SECRET=chuỗi-bí-mật-của-bạn
   ```

   Secret này phải **trùng** trên mọi bản build / máy chủ nơi khách **kích hoạt** key.

2. Sinh danh sách key (mặc định 50 key, ghi `vendor_keys_AFL1.txt` ở gốc project):

   ```bash
   python tools/gen_license_keys.py
   python tools/gen_license_keys.py 100
   python tools/gen_license_keys.py 5 --append
   ```

3. Key có dạng `AFL1-…-…`. Mỗi key tối đa **2 máy** kích hoạt (xem `license_guard.py`).

Chi tiết tham số và hành vi file output: đọc phần docstring đầu file `tools/gen_license_keys.py`.

## Biến môi trường thường dùng (tóm tắt)

| Biến | Vai trò |
|------|---------|
| `APIFY_TOKEN` | Token Apify (actor Similarweb / traffic). |
| `UPPROMOTE_API_URL`, `UPPROMOTE_BEARER_TOKEN` | API Uppromote. |
| `GOAFFPRO_API_URL`, `GOAFFPRO_BEARER_TOKEN` | API Goaffpro. |
| `AFF_LICENSE_HMAC_SECRET` | Secret ký và kiểm tra key bán; bắt buộc nếu cho khách nhập key. |
| `AFF_LICENSE_SERVER_URL` | (Tuỳ chọn) Base URL máy chủ đếm slot, ví dụ `https://license.example.com`. Nếu có: **kích hoạt / hủy kích hoạt bắt buộc có internet** và gọi API server; secret trên client phải **trùng** server để kiểm tra chữ ký `REMOTEv1`. |

Các biến khác (delay, giới hạn trang, …) có thể có default trong code — xem `filter.py` và tab Cài đặt trên UI.

## Máy chủ quản lý slot kích hoạt (`license_server/`)

Deploy riêng (VPS / Docker), **không** nhét vào file `.exe` desktop. Dùng cùng `AFF_LICENSE_HMAC_SECRET` như bản app (đọc từ `.env` gốc project hoặc biến môi trường).

**Chạy thử (máy dev):**

```bash
set LICENSE_ADMIN_PASSWORD=mật-khẩu-admin
python -m license_server
```

Mặc định lắng nghe `http://0.0.0.0:8765`. API:

- `POST /v1/activate` — JSON `{"license_key":"AFL1-...","machine_fingerprint":"<hex>"}` (app tự gửi).
- `POST /v1/deactivate` — JSON `{"binding_id":"...","machine_fingerprint":"..."}`.
- `GET /v1/health` — kiểm tra sống.

**Admin:** `/admin/login` (mật khẩu `LICENSE_ADMIN_PASSWORD`) — danh sách slot, nút **Thu hồi slot** để giải phóng máy khi cần.

**Biến server (tuỳ chọn):** `LICENSE_SERVER_DATABASE` (file SQLite), `MAX_MACHINES_PER_KEY`, `LICENSE_SERVER_HOST`, `LICENSE_SERVER_PORT`, `FLASK_SECRET_KEY`.

**Production:** đặt sau HTTPS reverse proxy (nginx), bật TLS; đổi `FLASK_SECRET_KEY` và mật khẩu admin mạnh.

### Deploy lên VPS / hosting (Gunicorn + MySQL)

**1. Chuẩn bị MySQL (trên hosting hoặc RDS)**

- Tạo database `utf8mb4`, ví dụ:

```sql
CREATE DATABASE aff_license CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

- Tạo user chỉ quyền trên database đó và ghi mật khẩu an toàn.

**2. Code trên server**

- Clone/copy project (ít nhất thư mục `license_server/` + `license_guard.py` ở gốc, vì server import `license_guard`).
- Python 3.10+:

```bash
cd /đường/dẫn/project
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux
pip install -r license_server/requirements.txt
```

**3. File `.env` trên server** (cùng thư mục gốc project — `license_server/app.py` đọc `ROOT/.env`):

```env
AFF_LICENSE_HMAC_SECRET=trùng-với-bản-app-và-lúc-sinh-key
LICENSE_ADMIN_PASSWORD=mật-khẩu-admin-mạnh
FLASK_SECRET_KEY=chuỗi-ngẫu-nhiên-dài

LICENSE_DB_DRIVER=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=aff_license
MYSQL_PASSWORD=...
MYSQL_DATABASE=aff_license
MYSQL_CHARSET=utf8mb4
```

Bảng `activations` được tạo tự động lần chạy đầu (engine InnoDB).

**4. Chạy bằng Gunicorn** (không dùng `flask run` trên production):

```bash
# Từ thư mục gốc project (chứa package license_server)
gunicorn -w 2 -b 127.0.0.1:8765 license_server.wsgi:application
```

Đặt systemd hoặc supervisor để tự khởi động lại; có thể proxy qua **nginx** HTTPS tới `127.0.0.1:8765`. URL công khai (ví dụ `https://license.example.com`) chính là giá trị **`AFF_LICENSE_SERVER_URL`** trong `.env` của app desktop/web.

Ví dụ khối `server` nginx (SSL đã cấu hình chứng chỉ riêng):

```nginx
location / {
    proxy_pass http://127.0.0.1:8765;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

**5. Nếu vẫn dùng SQLite trên VPS** (ít máy, backup đơn giản)

- Không đặt `LICENSE_DB_DRIVER` / `MYSQL_HOST`; chỉ cần `LICENSE_SERVER_DATABASE=/var/data/license_slots.db` (đường dẫn tuyệt đối, thư mục phải ghi được).

**6. Kiểm tra**

- `curl https://license.example.com/v1/health` → JSON `ok: true`.
- Mở `/admin/login` qua HTTPS.

### Không có nginx — trỏ domain vào file WSGI (shared hosting / Passenger)

**DNS / domain:** Bạn vẫn trỏ domain về **IP máy chủ** (hoặc record hosting quy định). Không có khái niệm “trỏ domain thẳng vào `app.py`”; phần **Application startup file** trên panel mới là file Python mà hosting dùng để chạy app.

**`http://127.0.0.1:8765` là gì?** Chỉ là ví dụ **trên cùng một VPS** khi có reverse proxy (nginx) chuyển tiếp vào tiến trình Gunicorn. Máy khách (app lọc trên PC) **không** được điền `127.0.0.1` — phải dùng URL công khai, ví dụ `https://license.example.com` → đặt trong **`AFF_LICENSE_SERVER_URL`**.

**Hosting có Passenger / cPanel “Setup Python App”:**

1. Thư mục ứng dụng = **gốc project** (có `license_guard.py`, `license_server/`, `.env`).
2. Cài dependency: `pip install -r license_server/requirements.txt` (trong virtualenv mà panel tạo).
3. **Application startup file:** chọn **`passenger_wsgi.py`** (file nằm **cùng cấp** `license_guard.py` trong repo).
4. File đó export biến `application` — Passenger gọi Flask qua WSGI; HTTPS thường do hosting (Apache + SSL) xử lý, **không cần nginx riêng**.

Nếu panel tự sinh `passenger_wsgi.py` (có dòng trỏ tới `virtualenv`), hãy **giữ phần virtualenv** và đảm bảo cuối file có import tương đương:

`from license_server.app import app as application`

**Không dùng Passenger (VPS trần, không nginx):** có thể chạy Gunicorn lắng nghe công khai (ít dùng vì thiếu TLS trừ khi có Cloudflare SSL chẳng hạn):

```bash
gunicorn -w 2 -b 0.0.0.0:8765 license_server.wsgi:application
```

Mở firewall cho port `8765` và dùng URL `http://IP:8765` hoặc tên miền trỏ thẳng tới IP:port — **nên bật HTTPS** (Let's Encrypt, Cloudflare, hoặc hosting quản lý SSL).

## Giới hạn dùng thử (tham chiếu code)

- Chưa kích hoạt key: **10** record Uppromote + **10** record Goaffpro **trên mỗi máy**, **không reset** theo ngày (file `.aff_free_usage.json`).
- Đã kích hoạt: quota **theo ngày** (giờ Việt Nam, reset ~23:05) — giá trị cụ thể trong `LICENSED_EXPORTS_PER_DAY` tại `license_guard.py`.

Khi đổi logic quota, cập nhật `license_guard.py` và thông báo trên UI / tài liệu người dùng cho khớp.
