# HỒ SƠ DỰ ÁN & HƯỚNG DẪN SỬ DỤNG (HANDOUT) - DỰ ÁN VLXX

Hệ thống bóc tách, giải mã luồng video trực tuyến và quản lý cơ sở dữ liệu ngoại tuyến JAV dành riêng cho dự án **VLXX**.

---

## I. KIẾN TRÚC HỆ THỐNG (ARCHITECTURE)

Hệ thống bao gồm 3 thành phần cốt lõi hoạt động nhịp nhàng với nhau:

1.  **Dữ liệu đầu vào (`data.txt`):** Chứa danh sách 3,172 video JAV thô thu thập từ website.
2.  **Trình cào đa luồng (`scripts/scrape_all_links.py`):** Quét và trích xuất link phát video trực tiếp.
3.  **Máy chủ giải mã trực tiếp (`scripts/proxy_server.py`):** Giải mã phân đoạn video ngụy trang PNG trong thời gian thực.
4.  **Trang quản lý Crimson (`dashboard.html`):** Giao diện Dark Mode màu đỏ Crimson giúp lọc, tìm kiếm và phát/tải phim nhanh chóng.

---

## II. CHI TIẾT CÁC THÀNH PHẦN & CƠ CHẾ GIẢI MÃ

### 1. Trình cào đa luồng siêu tốc (`scripts/scrape_all_links.py`)
*   **Chức năng:** Tự động mô phỏng yêu cầu AJAX gửi tới cổng `https://vlxx.moi/ajax.php` để lấy mã nhúng iframe, truy cập trang phát của `play.vlstream.net` và giải mã biến `window.__SRC` để lấy liên kết trực tiếp.
*   **Đa luồng & Checkpoint:** Chạy mặc định 8 luồng song song mượt mà. Tự động lưu tiến trình để có thể tắt và tiếp tục quét bất cứ lúc nào.

### 2. Máy chủ giải mã trực tiếp (`scripts/proxy_server.py`)
*   **Vấn đề thực tế (Anti-Piracy):** Máy chủ video sử dụng cơ chế chống tải lậu bằng cách ngụy trang tất cả phân đoạn video (`.ts`) thành file ảnh PNG thực thụ (`Content-Type: image/png` kèm chữ ký file ảnh `89 50 4E 47...`). Điều này làm cho VLC và FFmpeg báo lỗi không tìm thấy luồng.
*   **Giải pháp:** Máy chủ proxy nội bộ (chạy tại cổng `8899`) sẽ tự động tải phân đoạn ảnh PNG ảo về RAM, tìm kiếm thẻ kết thúc khối ảnh `IEND` (khoảng byte thứ 95) và **cắt bỏ toàn bộ phần Header ảnh PNG để khôi phục luồng video MPEG-TS nguyên bản** trước khi truyền lại cho VLC/FFmpeg.

### 3. Giao diện quản lý Crimson (`dashboard.html`)
*   **Bộ lọc thông minh:** Tìm kiếm tức thời theo tên phim, mã số, diễn viên (JAV Idol) hoặc mã JAV thương mại (*IPX, SSIS, MIDE...*).
*   **Copy 1-click:** Tạo sẵn câu lệnh PowerShell gọi VLC phát hoặc gọi FFmpeg tải phim tự động đi qua Proxy giải mã.

---

## III. HƯỚNG DẪN VẬN HÀNH CHI TIẾT (HOW TO RUN)

### Bước 1: Cài đặt thư viện cần thiết
Mở CMD/PowerShell tại thư mục `d:\AT\github\vlxx` và chạy:
```powershell
pip install -r requirements.txt
```

### Bước 2: Chạy trình cào cập nhật liên kết trực tiếp
```powershell
python scripts/scrape_all_links.py
```
*Bạn có thể tắt đi bật lại bất cứ lúc nào, script sẽ tự động tiếp tục ở vị trí đã dừng.*

### Bước 3: Khởi động máy chủ giải mã (BẮT BUỘC để xem/tải bằng VLC/FFmpeg)
Mở một cửa sổ CMD/PowerShell mới và khởi động proxy:
```powershell
python scripts/proxy_server.py
```
*Hãy luôn giữ cửa sổ này chạy trong suốt quá trình bạn xem phim trên VLC hoặc tải phim bằng FFmpeg.*

### Bước 4: Mở Dashboard quản lý
Nhấp đúp chuột vào file `d:\AT\github\vlxx\dashboard.html` để mở giao diện quản lý trên trình duyệt.

*   **Để xem trực tiếp không quảng cáo:** Ấn nút **VLC Cmd** trên thẻ phim, mở PowerShell và chuột phải dán vào rồi nhấn Enter.
*   **Để tải phim lưu trữ vĩnh viễn:** Ấn nút **FFmpeg Cmd**, dán vào PowerShell và nhấn Enter.
