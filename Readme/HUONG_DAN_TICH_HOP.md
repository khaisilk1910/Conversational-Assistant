# Conversational Assistant

Phiên bản: **2026.08.03.1607**

## 1. Cài đặt

1. Chép thư mục `conversational_assistant` vào:
   `/config/custom_components/conversational_assistant`
2. Khởi động lại Home Assistant.
3. Vào **Settings > Devices & services > Add integration**.
4. Tìm **Conversational Assistant** và hoàn tất cấu hình.

## 2. Cấu hình chính

Vào **Settings > Devices & services > Conversational Assistant > Configure**:

- **General settings**: cách xưng hô và hành vi chung.
- **Zalo settings**: tài khoản, người/nhóm nhận, webhook và từ khóa gọi tích hợp.
- **AI settings**: AI Agent điều khiển, AI Search, dự phòng và thời gian chờ.
- **Weather settings**: địa điểm mặc định, lịch gửi dự báo, kiểm tra bão.
- **Calendar settings**: lịch cần đọc, thời gian quét và nơi nhận thông báo.
- **TTS settings**: TTS entity, ngôn ngữ, giọng đọc và loa.

## 3. Chuyển webhook Zalo vào tích hợp

Automation hiện có chỉ cần chuyển toàn bộ payload đến action:

```yaml
action: conversational_assistant.process_zalo_webhook
data:
  payload: "{{ trigger.json }}"
```

Khi có nhiều config entry, thêm `config_entry_id`.

Không hard-code từ khóa gọi bot trong automation. Hãy cấu hình từ khóa trong UI để tích hợp tự lọc tin nhắn.

## 4. Lệnh thường dùng

### Thiết bị

- `Bật điều hòa phòng ngủ`
- `Tăng nhiệt độ điều hòa 2 độ`
- `Chuyển điều hòa sang chế độ dry`
- `Tăng tốc độ quạt 20%`
- `Bật quay đảo quạt`
- `Tắt quạt sau 30 phút`

### Thời tiết và bão

- `Thời tiết Hà Nội hôm nay`
- `Thời tiết 5 ngày tiếp theo`
- `Thời tiết Bangkok cuối tuần này`
- `Kiểm tra bão`

Dự báo nhiều ngày được tách theo từng ngày và yêu cầu đủ: điều kiện, nhiệt độ, khả năng mưa, độ ẩm và sức gió.

### Nhắc hẹn và lịch

- `Nhắc tôi uống thuốc lúc 20 giờ`
- `Nhắc tập thể dục mỗi thứ Hai lúc 7 giờ`
- `Danh sách nhắc hẹn`
- `Xóa nhắc hẹn`
- `Tạo sự kiện họp lúc 8 giờ ngày mai`
- `Sự kiện trong 15 ngày tới`

### Gửi Zalo

- `Gửi Zalo yêu cầu ngày mai 8 giờ nhân viên sale họp`
- `Thông báo Zalo hệ thống đã bảo trì xong`

Bot sẽ liệt kê các Zalo đã cấu hình và chờ chọn. Nội dung có thời điểm phù hợp sẽ tạo thêm nhắc Zalo trước 15 phút.

### Thông báo loa

- `Thông báo loa bữa tối đã sẵn sàng`
- `Báo ra loa mời mọi người xuống phòng họp`
- `Gửi loa cửa cổng đang mở`

Có thể chọn một, nhiều loa hoặc **Tất cả**. Mỗi loa được xử lý độc lập. Loa đang `playing` hoặc `buffering` được kiểm tra lại mỗi 10 giây, tối đa 20 lần.

### Camera

- `Chụp camera`
- `Phân tích camera`

Bot sẽ cho chọn camera và nơi nhận ảnh. Tính năng phân tích dùng AI đã chọn trong cấu hình.

### Ghi chú, trò chuyện, AI và bộ nhớ câu lệnh

- `Ghi nhớ mã tủ đồ là 2468`
- `Danh sách ghi chú`
- `Trò chuyện đi`
- `Kết thúc trò chuyện`
- `Tìm thông tin giá vàng hôm nay`
- `Tạo ảnh một ngôi nhà thông minh ban đêm`
- `Học câu lệnh xem cổng để chụp ảnh camera`
- `Danh sách câu lệnh đã học`
- `Xóa câu lệnh xem cổng`

### Âm dương lịch

- `Ngày mai âm lịch bao nhiêu`
- `Hôm nay thứ mấy`
- `Đổi ngày 30/11/1984 sang âm lịch`
- `Thứ Ba tuần sau âm lịch bao nhiêu`

## 5. Chọn, xác nhận và hủy

- Chọn nhiều mục: `1 3`, `1 và 3`, tên mục hoặc `Tất cả`.
- Xác nhận: `Có`, `Đồng ý` hoặc câu trả lời được bot gợi ý.
- Hủy luồng: `Hủy` hoặc `Bỏ yêu cầu vừa rồi`.
- Thời gian chờ mặc định: **120 giây**.

## 6. Hiển thị và TTS

- Zalo giữ emoji, tiêu đề, xuống dòng, gạch đầu dòng và nhấn mạnh để dễ đọc.
- Nội dung phát trực tiếp qua `tts.speak` được bỏ emoji, Markdown, ký tự trang trí và xuống dòng.
- Dấu câu, ngày giờ, phần trăm, nhiệt độ và đơn vị được giữ để giọng đọc có nhịp tự nhiên.
- Các yêu cầu đồng thời tới cùng một loa được xếp hàng; các loa khác nhau vẫn phát song song.

## 7. Xử lý lỗi nhanh

- **Không thấy loa**: kiểm tra media player có hỗ trợ `play_media`, không ở trạng thái `unavailable`, và đã có TTS entity.
- **Không nhận lệnh Zalo**: kiểm tra webhook automation, tài khoản Zalo, từ khóa gọi tích hợp và `config_entry_id` khi có nhiều entry.
- **Thời tiết thiếu ngày**: kiểm tra danh sách AI Search và quyền truy cập Internet của agent.
- **Voice không nhận lệnh**: kiểm tra pipeline đang dùng Home Assistant Conversation và ngôn ngữ phù hợp.
- **Sau cập nhật có lỗi**: khởi động lại Home Assistant và xem **Settings > System > Logs** với từ khóa `conversational_assistant`.
