# Conversational Assistant 1.2.1 — webhook Zalo

Bản này không đăng ký endpoint webhook mới. Webhook hoặc automation của bạn gọi action:

```text
conversational_assistant.process_zalo_webhook
```

## Automation

Giữ trigger và webhook ID đang dùng, nhưng phải đổi action sang domain mới:

```yaml
- action: conversational_assistant.process_zalo_webhook
  data:
    payload: "{{ trigger.json | to_json }}"
```

Không dùng nút Run thủ công để thử action này vì khi chạy thủ công sẽ không có `trigger.json`.

## Tự động quét nơi nhận theo yêu cầu

Conversational Assistant không quét thiết bị trong lúc Home Assistant khởi
động. Danh sách chỉ được tạo khi người dùng bắt đầu tạo nhắc hẹn, sau đó được
cache ngắn để các yêu cầu liên tiếp không phải quét lại toàn bộ registry.

Danh sách gồm:

- Mobile App có dịch vụ `notify` đang hoạt động;
- media player phù hợp để phát TTS;
- nơi nhận Zalo đã cấu hình;
- chính cuộc trò chuyện Zalo đang gửi lệnh.

Khi tùy chọn hỏi nơi nhận được bật, bot gửi danh sách và cho phép trả lời bằng số, tên, `tất cả`, `tất cả điện thoại`, `tất cả loa` hoặc `bỏ yêu cầu vừa rồi`.

## Bộ lọc webhook

Khi cài đặt, trường **ID tài khoản Zalo của bot** được để trống và
không chứa ID mặc định. Nếu bật xử lý webhook Zalo, bạn phải nhập
`_accountId` của chính bot trong payload webhook trước khi có thể lưu cấu hình.

Payload bị bỏ qua khi:

- `isSelf` là `true`;
- `data.uidFrom` bằng ID bot đã cấu hình;
- `_accountId` khác ID bot đã cấu hình;
- `msgId` đã được xử lý gần đây.

## Lệnh hỗ trợ

```text
Nhắc tôi 30 phút nữa uống thuốc
Tạo nhắc hẹn 18h30 ngày mai đi tập thể dục
Danh sách nhắc hẹn
Xóa nhắc hẹn
Ghi nhớ mua pin cho khóa cửa
Danh sách ghi chú
Bật đèn phòng khách
Cửa chính đã khóa chưa?
Thời tiết hôm nay
Lịch ngày mai
Hướng dẫn sử dụng tích hợp
```

## Home Assistant qua Zalo

Trong **Cài đặt > Thiết bị & dịch vụ > Conversational Assistant > Cấu hình > Cài đặt chung**:

1. Bật quyền Zalo kiểm tra và điều khiển Home Assistant.
2. Chọn Conversation agent.
3. Chỉ expose các entity được phép dùng từ Zalo.

Lệnh thiết bị, trạng thái và thời tiết được chuyển qua Conversation/Assist. Lịch được đọc từ các entity `calendar` đã expose.

## Trạng thái đang gõ

Từ phiên bản 1.1.4, sau khi webhook nhận một tin nhắn hợp lệ, tích hợp gọi ngay `zalo_bot.send_typing_event` với `thread_id` và `account_selection` của cuộc trò chuyện hiện tại. Trong khi yêu cầu còn đang xử lý, trạng thái được làm mới định kỳ khoảng 4 giây một lần và chỉ dừng sau khi phản hồi văn bản hoặc ảnh cuối cùng đã gửi xong. Cơ chế dùng chung này áp dụng cho nhắc hẹn, ghi chú, camera, lịch, thời tiết, kiểm tra trạng thái và điều khiển thiết bị. Lỗi hoặc thiếu action này không làm thất bại tính năng chính. Các nhắc hẹn chủ động gửi tới Zalo cũng phát trạng thái gõ ngay trước khi gửi.
