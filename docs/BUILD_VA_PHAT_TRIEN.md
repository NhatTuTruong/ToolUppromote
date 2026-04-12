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

Các biến khác (delay, giới hạn trang, …) có thể có default trong code — xem `filter.py` và tab Cài đặt trên UI.

## Giới hạn dùng thử (tham chiếu code)

- Chưa kích hoạt key: **10** record Uppromote + **10** record Goaffpro **trên mỗi máy**, **không reset** theo ngày (file `.aff_free_usage.json`).
- Đã kích hoạt: quota **theo ngày** (giờ Việt Nam, reset ~23:05) — giá trị cụ thể trong `LICENSED_EXPORTS_PER_DAY` tại `license_guard.py`.

Khi đổi logic quota, cập nhật `license_guard.py` và thông báo trên UI / tài liệu người dùng cho khớp.
