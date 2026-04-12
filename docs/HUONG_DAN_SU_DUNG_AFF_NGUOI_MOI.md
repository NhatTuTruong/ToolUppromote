# Hướng dẫn sử dụng cho người mới (affiliate offer)

Ứng dụng giúp **lấy danh sách offer** từ **Uppromote** hoặc **Goaffpro**, **lọc theo điều kiện offer** (hoa hồng, cookie, …) và **ước lượng traffic** qua Similarweb (chuỗi xử lý dùng **Apify**). Kết quả là file **Excel (.xlsx)** có cột trạng thái (ví dụ ĐẠT / CHƯA ĐẠT theo ngưỡng traffic bạn chọn).

## Bạn cần chuẩn bị gì?

1. **Tài khoản / quyền truy cập API** của Uppromote và/hoặc Goaffpro (URL API và Bearer token do nhà cung cấp hoặc admin cấp).
2. **Token Apify** để chạy actor lấy dữ liệu traffic theo domain.
3. (Tuỳ chọn) File **`domain.txt`** trong thư mục app nếu bạn muốn bổ sung thêm domain lọc — nếu không, app vẫn dùng domain suy ra từ URL offer.

Token nhạy cảm trên giao diện web được nhập dạng **ô ẩn** (password); hãy **không chia sẻ** màn hình hoặc file `.env` chứa token.

## Các tab trên giao diện

### 1. Cài đặt

- Điền **Token Apify**, **URL + Bearer** cho Uppromote và Goaffpro (nếu bạn dùng cả hai).
- Bấm **Lưu cài đặt** để ghi vào file `.env` của app.

### 2. Uppromote

- Chọn **ngưỡng traffic tối thiểu** (số visits tương đương từ dữ liệu Similarweb).
- Điều **trang bắt đầu / kết thúc** (mặc định thường chỉ lấy vài trang đầu cho lần thử).
- Điều các bộ lọc offer (hoa hồng, cookie, tiền tệ, duyệt đơn, …).
- Bấm **Lọc & xuất Excel**. Quá trình chạy có **log** chi tiết; có thể **Tạm dừng** / **Dừng** (file vẫn lưu phần đã xử lý nếu có).

### 3. Goaffpro

- Tương tự tab Uppromote nhưng nguồn dữ liệu là **cửa hàng Goaffpro** và mapping cột theo định dạng Goaffpro.

### 4. Kết quả

- Danh sách file `.xlsx` đã tạo; có thể **Tải xuống** hoặc **Xóa**.
- Dòng **ĐẠT** thường được tô nền để dễ lọc trong Excel.

## Bản quyền và dùng thử

- **Chưa kích hoạt key:** trên mỗi máy bạn được dùng thử tối đa **10 lượt xuất record Uppromote** và **10 lượt xuất record Goaffpro** (đếm theo từng dòng đã ghi vào Excel trong pipeline). **Không reset** theo ngày — hết quota nhánh đó thì cần dùng nhánh còn lại hoặc **kích hoạt key**.
- **Đã kích hoạt key:** quota theo **ngày** (theo giờ Việt Nam, có mốc reset trong app — xem thông báo trong mục Bản quyền).

Nhập key dạng `AFL1-…` trong mục **Bản quyền** (tab Cài đặt) và bấm **Kích hoạt**. **Hủy kích hoạt** giải phóng slot máy trên key và đưa app về chế độ dùng thử.

## Mẹo cho người mới

- Lần đầu chỉ đặt **trang kết thúc = 1** để chạy nhanh và làm quen log + file Excel.
- Nếu báo lỗi thiếu URL/token, quay lại tab **Cài đặt** và kiểm tra đã **Lưu** chưa.
- Nếu hết dùng thử một nguồn, đọc thông báo lỗi: thường gợi ý thử nguồn còn lại hoặc kích hoạt key.

## Cần hỗ trợ kỹ thuật (build, key, dev)

Xem file **`docs/BUILD_VA_PHAT_TRIEN.md`** trong cùng project.
