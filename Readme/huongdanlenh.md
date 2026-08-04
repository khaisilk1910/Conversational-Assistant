# Hướng dẫn Conversational Assistant

## Gọi tích hợp trên Zalo

Khi tùy chọn **Bắt buộc từ khóa gọi tích hợp trên Zalo** đang bật, mọi yêu cầu mới phải bắt đầu bằng đúng **Zalo invocation keyword** đã lưu trong Settings. Trong lúc bot đang chờ chọn hoặc xác nhận, có thể trả lời trực tiếp mà không cần nhập lại từ khóa.

Ví dụ, thay `[TỪ KHÓA]` bằng giá trị hiện được cấu hình:

- `[TỪ KHÓA] hướng dẫn tích hợp`
- `[TỪ KHÓA] các lệnh tích hợp`
- `[TỪ KHÓA] chụp Cam Cổng`
- `[TỪ KHÓA] báo loa Phòng Ngủ xuống ăn cơm`
- `[TỪ KHÓA] thông báo Zalo Khải xuống ăn cơm`
- `[TỪ KHÓA] thời tiết Hà Nội 5 ngày tới`

Gửi **Hủy** để dừng luồng đang chờ. Thời gian chọn hoặc xác nhận là 120 giây.

## Xem nhanh toàn bộ từ khóa

Gửi **lệnh tích hợp** hoặc **các lệnh tích hợp** để nhận danh sách ngắn gọn toàn bộ nhóm từ khóa. Mỗi tính năng có đúng một ví dụ mẫu. Trên Zalo, thêm Zalo invocation keyword ở đầu khi tùy chọn bắt buộc từ khóa đang bật.

## Các nhóm tính năng

### Thiết bị

Bật, tắt, tăng, giảm, thay đổi chế độ điều hòa hoặc quạt và hẹn giờ thao tác thiết bị.

### Thời tiết và bão

Hỏi thời tiết hiện tại hoặc dự báo tối đa 7 ngày; kiểm tra bão và áp thấp nhiệt đới bằng AI Search.

### Nhắc hẹn và lịch

Tạo, xem, sửa, xóa nhắc hẹn hoặc sự kiện; hỗ trợ lặp lại và gửi đến Mobile, Zalo hoặc loa đã đặt tên.

### Thông báo loa

Gọi trực tiếp tên loa đã đặt hoặc chọn một, nhiều loa hay tất cả loa. Loa đang bận sẽ được chờ và kiểm tra lại.

### Gửi Zalo

Gọi trực tiếp tên Zalo đã đặt. Nội dung có ngày giờ có thể tạo nhắc hẹn trước thời điểm đó 15 phút.

### Camera

Chụp hoặc phân tích camera bằng tên đã đặt. Khi không có tên phù hợp, bot hiển thị danh sách camera để chọn.

### Ghi chú và trò chuyện

Thêm, xem, sửa, xóa ghi chú; mở phiên trò chuyện AI bằng lệnh **Trò chuyện** và đóng bằng **Kết thúc**.

### AI và bộ nhớ câu lệnh

Tìm thông tin, tạo ảnh, học câu lệnh mới, xem hoặc xóa câu lệnh đã học.

### Âm dương lịch

Tra ngày âm lịch, thứ trong tuần và chuyển đổi ngày âm sang dương hoặc ngày dương sang âm.

## Cấu hình

Mở **Settings > Devices & services > Conversational Assistant > Configure** để đặt tên Mobile, Zalo, loa, camera và cấu hình AI, lịch, thời tiết, TTS cùng Zalo invocation keyword.
