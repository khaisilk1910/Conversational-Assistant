# Conversational Assistant 1.2.1 — Home Assistant qua Zalo

## Tính năng

- Bật, tắt, mở, đóng, khóa và điều chỉnh thiết bị.
- Kiểm tra trạng thái theo thiết bị, phòng, khu vực hoặc sàn.
- Hỏi nhiệt độ, độ ẩm và thời tiết.
- Đọc sự kiện từ các entity `calendar`.
- Quét toàn bộ entity `camera` khi có yêu cầu, dùng cache ngắn, yêu cầu xác
  nhận và gửi ảnh chụp về Zalo. Không quét camera trong lúc Home Assistant
  khởi động.
- Quản lý nhắc hẹn và ghi chú trong cùng tích hợp.
- Dạy, liệt kê và xóa các câu lệnh tùy chỉnh dùng chung với Voice Assist.
- Hiển thị hướng dẫn sử dụng đầy đủ theo đầu mục khi người dùng yêu cầu trợ giúp.

## Cấu hình

Mở **Cài đặt > Thiết bị & dịch vụ > Conversational Assistant > Cấu hình > Cài đặt chung**.

- Bật quyền Zalo kiểm tra và điều khiển Home Assistant.
- Chọn Conversation agent. Mặc định là `conversation.home_assistant`.
- Expose các entity muốn cho phép Zalo sử dụng.

Automation webhook gọi:

```yaml
- action: conversational_assistant.process_zalo_webhook
  data:
    payload: "{{ trigger.json | to_json }}"
```

## Ví dụ

```text
Bật đèn phòng khách
Tắt quạt phòng ngủ
Đặt điều hòa phòng khách 25 độ
Cửa chính đã khóa chưa?
Phòng khách có thiết bị nào đang bật?
Tầng 2 đang thế nào?
Thời tiết hôm nay
Lịch ngày mai
Xem lịch 7 ngày tới
Chụp ảnh camera
Kiểm tra camera sân trước
Lấy ảnh camera phòng khách
Hướng dẫn sử dụng tích hợp
```

## Cách xử lý

- Nhắc hẹn và ghi chú được nhận diện trước.
- Lệnh thiết bị, trạng thái và thời tiết được gửi vào Conversation agent.
- Truy vấn lịch dùng `calendar.get_events`, gộp nhiều calendar và sắp xếp theo giờ.
- Yêu cầu ảnh camera tạo danh sách đánh số khi tên chưa rõ; người dùng có thể chọn một hoặc nhiều camera như `1 3 10`, hoặc gửi `tất cả`. Các camera được snapshot song song. Khi có nhiều ảnh, group ưu tiên `zalo_bot.send_images_to_group`, chat cá nhân ưu tiên `zalo_bot.send_images_to_user`; chỉ dự phòng `zalo_bot.send_image` từng ảnh khi action nhiều ảnh tương ứng chưa có.
- Snapshot được lưu ổn định trong `/media/conversational_assistant/` và ghi đè cho cùng camera/cuộc trò chuyện để không tăng file vô hạn.
- Mỗi chat riêng giữ một `conversation_id`.
- Chat nhóm chỉ xử lý câu Home Assistant rõ ràng.

## Bảo mật

Chỉ expose các entity thực sự cần dùng. Cẩn thận với khóa, cửa gara, báo động và các thiết bị nhạy cảm.

Tính năng ảnh camera được thiết kế theo yêu cầu tự quét **toàn bộ** entity `camera` đang hoạt động và không dùng bộ lọc expose của Assist. Vì vậy, chỉ cấp quyền webhook Zalo cho người hoặc nhóm được phép xem tất cả camera.


## Luồng camera qua Zalo

1. Người dùng gửi: `chụp ảnh camera`, `kiểm tra camera`, `lấy ảnh camera` hoặc `ảnh camera ...`.
2. Khi nhận yêu cầu, tích hợp mới quét các entity thuộc domain `camera` đang
   có trong Home Assistant. Danh sách được cache trong thời gian ngắn để tránh
   quét lại liên tục.
3. Zalo nhận danh sách đánh số và cho phép xác nhận một hoặc nhiều camera, ví dụ `1 3 10`, tên camera, hoặc `tất cả`.
4. Sau khi chọn, tích hợp gọi:

```yaml
action: camera.snapshot
target:
  entity_id: camera.camera_da_chon
data:
  filename: /media/conversational_assistant/camera_<id>.jpg
```

5. Ảnh được gửi về đúng cuộc trò chuyện bằng dữ liệu tương đương:

```yaml
action: zalo_bot.send_image
data:
  type: "{{ thread_type }}"
  ttl: 0
  image_path: /media/conversational_assistant/camera_<id>.jpg
  message: Đã chụp ảnh camera đã chọn
  thread_id: "{{ thread_id }}"
  account_selection: "{{ account_selection }}"
```

Camera ở trạng thái `unavailable` hoặc `unknown` vẫn được hiển thị để người dùng biết, nhưng tích hợp sẽ không gọi snapshot cho camera đó.

Trong mọi luồng xử lý từ Zalo, tích hợp gọi `zalo_bot.send_typing_event` ngay khi nhận yêu cầu và tự làm mới định kỳ cho đến khi phản hồi cuối cùng đã được gửi. Cơ chế này áp dụng cho điều khiển/kiểm tra thiết bị, lịch, thời tiết, nhắc hẹn, ghi chú, camera và các bước xác nhận. Action này là tùy chọn; nếu phiên bản `zalo_bot` chưa cung cấp thì các chức năng khác vẫn hoạt động bình thường.

Khi có nhiều ảnh, dữ liệu gửi dùng action theo loại đích:

```yaml
# Zalo group
action: zalo_bot.send_images_to_group
data:
  thread_id: "<thread_id>"
  account_selection: "<tài khoản bot>"
  image_paths: /media/conversational_assistant/camera_1.jpg,/media/conversational_assistant/camera_2.jpg

# Zalo cá nhân
action: zalo_bot.send_images_to_user
data:
  thread_id: "<thread_id>"
  account_selection: "<tài khoản bot>"
  image_paths: /media/conversational_assistant/camera_1.jpg,/media/conversational_assistant/camera_2.jpg
```

Caption ảnh gửi bằng `send_image` là plain text, không thêm Markdown. Có thể gọi thẳng `Chụp Cam Bếp gửi Zalo Khải` hoặc `Gửi Cam Bếp Zalo Khải`. Nếu camera/Zalo không chắc chắn, tích hợp liệt kê và giữ phiên 120 giây để chọn.

Lịch chụp cũng dùng cùng cơ chế chọn camera/Zalo:

```text
Hẹn 5 phút nữa chụp Cam Bếp gửi Zalo Khải
Hẹn mỗi 5 phút chụp Cam Bếp gửi Zalo Khải
Hẹn 15 giờ 30 hàng ngày chụp Cam Bếp gửi Zalo Khải
Xem lịch chụp camera
Xóa lịch chụp camera
```

Khi xóa lịch, bot luôn chờ chọn lịch rồi hỏi xác nhận xóa. Sensor `Số lịch chụp camera` lưu tổng số và chi tiết lịch trong attributes.



## Camera video ngay trong Zalo

Các cách nói `Xem Cam Bếp`, `Ghi Camera Cổng`, `Quay Cam Sân` hoặc `Xem video Cam Bếp` sẽ ghi một clip ngắn bằng `camera.record`. Nếu không nêu Zalo đích, clip được gửi trở lại **chính nhóm/cuộc trò chuyện hiện tại**. Muốn gửi nơi khác, nói rõ tên đã đặt, ví dụ `Gửi video Cam Bếp đến Zalo Khải`.

Nếu camera hoặc Zalo không chắc chắn, bot liệt kê lựa chọn và giữ phiên 120 giây. Tích hợp chỉ khởi tạo `stream` khi thực sự cần ghi video; các yêu cầu cùng một camera được xếp tuần tự, còn camera khác vẫn có thể xử lý đồng thời.

Nếu câu sau invocation keyword chỉ gợi ý một tính năng nhưng chưa đủ rõ, bot trả về hướng dẫn/ ví dụ đúng tính năng đó và chờ câu làm rõ; không đẩy ngay toàn bộ yêu cầu sang AI.

## Bộ nhớ câu lệnh qua Zalo

Có thể dạy câu lệnh trực tiếp trong cuộc trò chuyện Zalo:

```text
Học câu lệnh xem cổng để chụp ảnh camera
Học câu lệnh đi ngủ để tắt tất cả đèn
Danh sách câu lệnh đã học
Xóa câu lệnh xem cổng
```

Câu đã học có hiệu lực ngay và cũng dùng được trên Voice Assist. Bộ nhớ là bộ nhớ chung của config entry, không tách riêng theo từng nhóm hoặc người dùng Zalo. Vì vậy chỉ nên cho các cuộc trò chuyện tin cậy gọi webhook và dạy các macro điều khiển thiết bị nhạy cảm. Các lệnh Home Assistant đích vẫn được xử lý qua Conversation agent và quyền expose hiện tại.


## Hướng dẫn sử dụng qua Zalo

Các câu như `hướng dẫn sử dụng tích hợp`, `sử dụng tích hợp`, `hướng dẫn tích hợp`, `học cách sử dụng các tính năng` hoặc `tích hợp có tính năng gì` sẽ trả về danh sách chức năng có định dạng đầu mục và ví dụ. Khi yêu cầu này được nhận, các bước xác nhận Zalo đang chờ trước đó được hủy để tránh câu trả lời tiếp theo bị hiểu nhầm.
