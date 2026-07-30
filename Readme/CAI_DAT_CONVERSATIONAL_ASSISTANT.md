# Conversational Assistant 1.2.1 — cài đặt như một tích hợp mới

## Định danh kỹ thuật mới

Bản này là một custom integration mới, độc lập với tích hợp cũ:

- Thư mục: `custom_components/conversational_assistant`
- Domain: `conversational_assistant`
- Action Zalo: `conversational_assistant.process_zalo_webhook`
- Storage: `conversational_assistant.<config_entry_id>`
- Notification tag và notification action dùng tiền tố Conversational Assistant.

Không đổi tên thư mục thành tên khác. Home Assistant yêu cầu tên thư mục trùng với domain trong `manifest.json`.

## Cài đặt

1. Tắt hoặc xóa config entry của tích hợp cũ trước khi bật bản mới. Hai tích hợp có cùng mẫu câu nhắc hẹn và ghi chú; nếu chạy đồng thời, cả hai có thể nhận cùng một lệnh hội thoại.
2. Xóa thư mục tích hợp cũ nếu không còn sử dụng.
3. Chép thư mục `custom_components/conversational_assistant` vào `config/custom_components`.
4. Khởi động lại Home Assistant.
5. Thêm tích hợp **Conversational Assistant** trong **Cài đặt > Thiết bị & dịch vụ**.
6. Cập nhật automation webhook Zalo để gọi action mới.

```yaml
- action: conversational_assistant.process_zalo_webhook
  data:
    payload: "{{ trigger.json | to_json }}"
```

## Dữ liệu của tích hợp cũ

Vì đây là một domain mới, config entry, sensor, nhắc hẹn, ghi chú và storage của tích hợp cũ không được Home Assistant tự động gắn sang bản mới. Bản mới khởi tạo kho dữ liệu riêng. Hãy sao lưu thư mục `.storage` trước khi gỡ tích hợp cũ nếu cần giữ dữ liệu để chuyển đổi thủ công.

## Đồng bộ tính năng

Mã nguồn của bản mới giữ đầy đủ các nhóm tính năng:

- tạo, liệt kê, xóa, lặp lại và báo lại nhắc hẹn;
- tự động quét Mobile App và loa theo yêu cầu, có cache, không cản trở quá
  trình khởi động; đồng thời dùng các nơi nhận Zalo đã cấu hình;
- xử lý webhook Zalo và chọn nơi nhận;
- ghi chú công khai và ghi chú mã hóa;
- điều khiển, truy vấn trạng thái Home Assistant;
- thời tiết, lịch sự kiện và Conversation agent;
- bộ nhớ câu lệnh tùy chỉnh dùng chung cho Voice Assist và Zalo;
- hướng dẫn sử dụng có cấu trúc, gọi trực tiếp từ Voice Assist hoặc Zalo;
- các sensor đếm nhắc hẹn, nhắc hẹn tiếp theo, số ghi chú và số câu lệnh đã học.


## Bộ nhớ câu lệnh 1.2.1

Conversational Assistant có thể học thêm cách nói mà không cần sửa mã nguồn hoặc khởi động lại Home Assistant. Dữ liệu được lưu trong cùng Home Assistant Store của config entry và tự đăng ký lại khi tích hợp tải lên.

Ví dụ:

```text
Học câu lệnh xem cổng để chụp ảnh camera
Học câu lệnh việc mới để tạo nhắc hẹn
Học câu lệnh đi ngủ để tắt tất cả đèn
Danh sách câu lệnh đã học
Xóa câu lệnh xem cổng
Xóa tất cả câu lệnh đã học
```

Câu lệnh đã học được dùng chung trên Voice Assist và Zalo. Với câu tạo nhắc hẹn hoặc ghi chú, nội dung nói phía sau alias được chuyển tiếp vào luồng hiện có. Ví dụ sau khi học `việc mới` cho chức năng tạo nhắc hẹn, có thể nói `việc mới 18h30 ngày mai uống thuốc`.


## Hướng dẫn sử dụng 1.2.1

Người dùng có thể yêu cầu trợ giúp bằng các câu tự nhiên như:

```text
Hướng dẫn sử dụng tích hợp
Sử dụng tích hợp
Hướng dẫn tích hợp
Học cách sử dụng các tính năng của tích hợp này
Tích hợp có những tính năng gì?
```

Phản hồi được chia thành các đầu mục nhà thông minh, thời tiết và lịch, camera, nhắc hẹn, ghi chú và bộ nhớ câu lệnh. Mỗi đầu mục có mô tả ngắn cùng hai ví dụ. Lệnh này được ưu tiên cả khi một quy trình khác đang chờ xác nhận.
