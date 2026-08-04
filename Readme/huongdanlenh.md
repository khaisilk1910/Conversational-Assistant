# Hướng dẫn Conversational Assistant

## 1. Gọi tích hợp trên Zalo

Khi **Bắt buộc từ khóa gọi tích hợp trên Zalo** đang bật, mọi yêu cầu mới phải bắt đầu bằng đúng **Zalo invocation keyword** trong Settings.

Thay `[TỪ KHÓA]` bằng giá trị đang cấu hình:

- `[TỪ KHÓA] hướng dẫn tích hợp`
- `[TỪ KHÓA] các lệnh tích hợp`
- `[TỪ KHÓA] nhắc Zalo Khải 1 phút nữa uống thuốc`
- `[TỪ KHÓA] chụp Cam Cổng`

Khi bot đang chờ chọn hoặc xác nhận, chỉ cần trả lời trực tiếp, không cần nhập lại từ khóa.

Nếu người dùng đã nhập đúng Zalo invocation keyword nhưng phần yêu cầu không khớp bất kỳ tính năng hoặc câu lệnh đã học nào, tích hợp sẽ phản hồi **Các lệnh tích hợp** để người dùng chọn lại từ khóa chính xác.

## 2. Hủy phiên ngay lập tức

Trong bất kỳ phiên nào, gửi một trong các lệnh:

- `Hủy`
- `Hủy yêu cầu`
- `Hủy phiên`
- `Dừng yêu cầu`
- `Dừng phiên`
- `Kết thúc phiên`
- `Bỏ yêu cầu vừa rồi`

Lệnh hủy không cần Zalo invocation keyword. Tích hợp sẽ dừng ngay phiên ghi chú, nhắc hẹn, thiết bị, lịch, camera, gửi Zalo, thông báo loa, trò chuyện AI hoặc tác vụ nền đang xử lý. Thời gian chờ chọn hoặc xác nhận là 120 giây.

## 3. Xem hướng dẫn và danh sách lệnh

### Xem hướng dẫn

Từ khóa: `trợ giúp`, `hướng dẫn`, `hướng dẫn sử dụng`, `hướng dẫn tích hợp`  
Ví dụ: `Hướng dẫn tích hợp`

### Xem tất cả lệnh

Từ khóa: `lệnh tích hợp`, `các lệnh tích hợp`, `xem lệnh tích hợp`, `xem các lệnh tích hợp`, `xem lệnh của tích hợp`, `xem các lệnh của tích hợp`, `liệt kê các lệnh tích hợp`  
Ví dụ: `Các lệnh tích hợp`

Phản hồi được chia theo tính năng, ngắt dòng dễ đọc và mỗi tính năng chỉ có một ví dụ.

## 4. Các lệnh tích hợp

### Thiết bị

Từ khóa: `bật`, `tắt`, `mở`, `đóng`, `khóa`, `mở khóa`, `tăng`, `giảm`, `đặt`, `chỉnh`, `chuyển`, `đổi`, `dừng`, `tạm dừng`, `tiếp tục`, `phát`, `quét`, `dọn dẹp`, `làm sạch`, `xem trạng thái`, `hẹn giờ`, `lên lịch`  
Ví dụ: `Tắt quạt phòng ngủ sau 30 phút`

### Thời tiết và bão

Từ khóa: `thời tiết`, `dự báo thời tiết`, `có mưa không`, `khả năng mưa`, `nhiệt độ`, `độ ẩm`, `chỉ số UV`, `kiểm tra bão`, `áp thấp nhiệt đới`  
Ví dụ: `Thời tiết Hà Nội 5 ngày tới`

### Nhắc hẹn

Từ khóa: `nhắc`, `hẹn`, `nhắc tôi`, `tạo nhắc hẹn`, `đặt nhắc hẹn`, `thêm nhắc hẹn`, `xem danh sách nhắc hẹn`, `hủy nhắc hẹn`, `xóa nhắc hẹn`  
Ví dụ: `Nhắc Zalo Khải 1 phút nữa uống thuốc`

Có thể nhắc trực tiếp đến tên **Mobile**, **Zalo** hoặc **loa** đã đặt trong Settings và có thể nêu nhiều tên liên tiếp. Nếu không nêu nơi nhận, tích hợp luôn hiển thị danh sách để chọn.

### Lịch và sự kiện

Từ khóa: `xem lịch`, `kiểm tra lịch`, `sự kiện`, `tạo sự kiện`, `thêm sự kiện`, `đặt lịch`, `lên lịch`, `cuộc họp`, `cuộc hẹn`  
Ví dụ: `Tạo sự kiện họp sale ngày mai lúc 8 giờ`

### Thông báo loa

Từ khóa: `thông báo loa`, `báo loa`, `báo ra loa`, `thông báo ra loa`, `gửi loa`, `nhắn loa`  
Ví dụ: `Báo loa Phòng Ngủ xuống ăn cơm`

### Gửi Zalo

Từ khóa: `gửi Zalo`, `thông báo Zalo`, `báo Zalo`  
Ví dụ: `Thông báo Zalo Khải xuống ăn cơm`

### Chụp camera

Từ khóa: `chụp camera`, `chụp cam`, `chụp ảnh từ camera`, `lấy ảnh camera`, `lấy hình camera`  
Ví dụ: `Chụp Cam Cổng`

### Phân tích camera

Từ khóa: `phân tích camera`, `phân tích cam`, `kiểm tra camera`, `xem và phân tích camera`  
Ví dụ: `Phân tích Cam Cổng`

### Ghi chú

Từ khóa: `thêm ghi chú`, `tạo ghi chú`, `lưu ghi chú`, `viết ghi chú`, `xem ghi chú`, `liệt kê ghi chú`, `đọc ghi chú`, `sửa ghi chú`, `cập nhật ghi chú`, `xóa ghi chú`  
Ví dụ: `Ghi chú mua sữa`

### Trò chuyện AI

Từ khóa: `trò chuyện đi`, `tám đi`, `buôn đi`, `kết thúc`  
Ví dụ: `Trò chuyện đi`

### Tìm kiếm Internet

Từ khóa: `tìm thông tin`, `tìm kiếm`, `tìm kiếm trên mạng`, `tìm trên mạng`, `tra cứu`  
Ví dụ: `Tìm thông tin giá vàng hôm nay`

### Tạo ảnh AI

Từ khóa: `tạo một bức ảnh`, `tạo bức ảnh`, `tạo một ảnh`, `tạo ảnh`  
Ví dụ: `Tạo ảnh ngôi nhà bên hồ`

### Âm dương lịch

Từ khóa: `âm lịch`, `lịch âm`, `dương lịch`, `lịch dương`, `thứ mấy`, `đổi`, `chuyển`, `quy đổi`, `tra ngày`, `xem ngày`  
Ví dụ: `Đổi 30/11/1984 sang âm lịch`

### Bộ nhớ câu lệnh

Từ khóa: `học câu lệnh`, `dạy câu lệnh`, `thêm câu lệnh`, `thêm cách nói`, `xem câu lệnh đã học`, `xóa câu lệnh`, `quên câu lệnh`  
Ví dụ: `Học câu lệnh xem cổng để chụp Cam Cổng`

### Điều khiển phiên

Từ khóa: `hủy`, `hủy yêu cầu`, `hủy phiên`, `dừng yêu cầu`, `dừng phiên`, `kết thúc phiên`, `bỏ yêu cầu vừa rồi`  
Ví dụ: `Hủy`

## 5. Cấu hình

Mở **Settings > Devices & services > Conversational Assistant > Configure** để:

- đặt tên Mobile, Zalo, loa và camera;
- cấu hình AI Agent, AI Search, lịch, thời tiết và TTS;
- bật hoặc tắt yêu cầu Zalo invocation keyword;
- thay đổi Zalo invocation keyword dùng để gọi tích hợp.
