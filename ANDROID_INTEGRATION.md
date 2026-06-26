# TÀI LIỆU TÍCH HỢP ỨNG DỤNG DI ĐỘNG (ANDROID INTEGRATION GUIDE) - DỰ ÁN VLXX

Tài liệu hướng dẫn kỹ thuật chi tiết để nhúng luồng dữ liệu và phát video giải mã từ dự án **VLXX** vào ứng dụng Android chuyên nghiệp mà **không cần máy chủ Proxy trung gian**.

---

## I. THIẾT LẬP NGUỒN DỮ LIỆU TỪ GITHUB (DATABASE SOURCE)

Bạn không cần tốn chi phí thuê máy chủ để lưu trữ dữ liệu. Ứng dụng Android của bạn có thể gọi trực tiếp file dữ liệu đã được cào và đẩy tự động lên GitHub hàng ngày.

*   **URL API chính thức của bạn:**
    `https://raw.githubusercontent.com/gx288/vlxx/main/data/vlxx_database.json`
*   **Cơ chế hoạt động:**
    1. Khi App khởi động, sử dụng thư viện **Retrofit** hoặc **OkHttp** để gửi một yêu cầu `GET` đến URL trên.
    2. Parse dữ liệu JSON nhận được thành danh sách đối tượng Video trong ứng dụng để hiển thị lên giao diện (RecyclerView/Compose).

---

## II. GIẢI PHÁP PHÁT VIDEO GIẢI MÃ KHÔNG CẦN SERVER (NATIVE DECRYPTION)

Do các phân đoạn video (`.ts`) bị máy chủ Google CDN ngụy trang dưới dạng ảnh PNG ảo (`89 50 4E 47...` ở 8 byte đầu), trình phát mặc định của Android sẽ báo lỗi định dạng.

Giải pháp chuyên nghiệp nhất là sử dụng **ExoPlayer** (hoặc thư viện mới **Media3 ExoPlayer**) kết hợp với một **Custom DataSource** để tự động gỡ bỏ 95 byte PNG giả lập ngay trên RAM điện thoại.

### 1. Mã nguồn Kotlin cho bộ giải mã trên Android (ExoPlayer DataSource):

Hãy tích hợp lớp code dưới đây vào dự án Android của bạn:

```kotlin
import android.net.Uri
import com.google.android.exoplayer2.upstream.DataSource
import com.google.android.exoplayer2.upstream.DataSpec
import com.google.android.exoplayer2.upstream.TransferListener
import java.io.IOException

class PngDecryptionDataSource(private val upstream: DataSource) : DataSource {

    private var isFirstRead = true

    @Throws(IOException::class)
    override fun open(dataSpec: DataSpec): Long {
        isFirstRead = true
        return upstream.open(dataSpec)
    }

    @Throws(IOException::class)
    override fun read(buffer: ByteArray, offset: Int, readLength: Int): Int {
        if (isFirstRead) {
            isFirstRead = false
            // Đọc tạm 95 byte đầu tiên của phân đoạn để kiểm tra và loại bỏ PNG Header
            val peekBuffer = ByteArray(95)
            val bytesPeeked = upstream.read(peekBuffer, 0, 95)
            
            if (bytesPeeked >= 8 && isPngSignature(peekBuffer)) {
                // Đây là phân đoạn video ngụy trang PNG!
                // Ta đã bỏ qua (skip) thành công 95 byte PNG đầu tiên.
                // Bây giờ tiến hành đọc dữ liệu video thực tế (MPEG-TS bắt đầu bằng byte 0x47)
                return upstream.read(buffer, offset, readLength)
            } else {
                // Nếu không phải PNG ngụy trang, trả lại dữ liệu bình thường
                System.arraycopy(peekBuffer, 0, buffer, offset, bytesPeeked)
                if (bytesPeeked < readLength) {
                    val additionalRead = upstream.read(buffer, offset + bytesPeeked, readLength - bytesPeeked)
                    return if (additionalRead == -1) bytesPeeked else bytesPeeked + additionalRead
                }
                return bytesPeeked
            }
        }
        return upstream.read(buffer, offset, readLength)
    }

    private fun isPngSignature(buffer: ByteArray): Boolean {
        // Kiểm tra chữ ký file PNG: 89 50 4E 47 0D 0A 1A 0A
        return buffer[0] == 0x89.toByte() &&
               buffer[1] == 0x50.toByte() &&
               buffer[2] == 0x4E.toByte() &&
               buffer[3] == 0x47.toByte()
    }

    override fun getUri(): Uri? = upstream.uri

    @Throws(IOException::class)
    override fun close() {
        upstream.close()
    }

    override fun addTransferListener(transferListener: TransferListener) {
        upstream.addTransferListener(transferListener)
    }
}
```

### 2. Cách đăng ký bộ giải mã vào ExoPlayer:

Cấu hình trình phát video trong App Android của bạn sử dụng bộ giải mã trên như sau:

```kotlin
val defaultHttpDataSourceFactory = DefaultHttpDataSource.Factory()
    .setUserAgent("Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36")
    .setDefaultRequestProperties(mapOf("Referer" to "https://vlxx.moi/"))

val customDataSourceFactory = DataSource.Factory {
    PngDecryptionDataSource(defaultHttpDataSourceFactory.createDataSource())
}

// Khởi tạo ExoPlayer sử dụng Custom DataSource giải mã
val player = ExoPlayer.Builder(context)
    .setMediaSourceFactory(DefaultMediaSourceFactory(customDataSourceFactory))
    .build()
```

---

## III. CÁC LỖI THƯỜNG GẶP & PHƯƠNG PHÁP PHÒNG TRÁNH CHUYÊN NGHIỆP

### Lỗi 1: Lỗi chặn Hotlinking từ máy chủ (`HTTP 403 Forbidden`)
*   **Triệu chứng:** Link phát được trên trình duyệt gốc nhưng đưa vào App thì màn hình đen và báo lỗi HTTP 403.
*   **Nguyên nhân:** Server kiểm tra và chặn nếu thiếu tiêu đề liên kết.
*   **Cách khắc phục:** Luôn đính kèm tiêu đề **`Referer: https://vlxx.moi/`** (hoặc domain đang hoạt động của web) và **`User-Agent`** giả lập trình duyệt Chrome di động vào mọi yêu cầu tải phân đoạn (như đã cấu hình ở phần `DefaultHttpDataSource.Factory` phía trên).

### Lỗi 2: Lỗi nhà mạng Việt Nam chặn tên miền phụ (`UnknownHostException` / `Connection Timeout`)
*   **Triệu chứng:** Các server dự phòng hoặc ảnh bìa không thể tải được trên một số nhà mạng (Viettel, FPT, VNPT).
*   **Cách khắc phục chuyên nghiệp:**
    1.  **Sử dụng DNS qua HTTPS (DoH):** Thay vì dùng DNS mặc định của điện thoại (dễ bị nhà mạng điều hướng chặn), hãy tích hợp thư viện **OkHttp DNS-over-HTTPS** trong App để phân giải IP trực tiếp qua DNS của Cloudflare (`1.1.1.1`) hoặc Google (`8.8.8.8`).
    2.  **Cơ chế Tự động chuyển Server (Auto-Fallback):** Thiết lập sự kiện lắng nghe lỗi trình phát (`Player.Listener`). Nếu xảy ra lỗi kết nối ở Server #1, ứng dụng sẽ tự động chuyển sang Server #2 hoặc các server dự phòng mà không hiển thị thông báo lỗi ra màn hình để tránh làm gián đoạn trải nghiệm người dùng.

### Lỗi 3: Link trực tiếp Google CDN hết hạn (`HTTP 410 Gone` hoặc `HTTP 403`)
*   **Triệu chứng:** Xem lại phim cũ sau vài ngày thì báo lỗi không tải được.
*   **Nguyên nhân:** Link Google CDN có chữ ký giới hạn thời gian.
*   **Cách khắc phục chuyên nghiệp:**
    *   Tận dụng các Server dự phòng (như Blogger, Seaporn) vốn là link nhúng ổn định lâu dài.
    *   App cần có cơ chế kiểm tra thời gian hết hạn của link (dựa vào trường `/expire/[TIMESTAMP]` trên URL) để cảnh báo người dùng hoặc tự động kích hoạt tiến trình yêu cầu cào lại link mới.
