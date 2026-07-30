# Bộ nhớ câu lệnh — Conversational Assistant 1.2.1

## Mục đích

Bộ nhớ câu lệnh cho phép người dùng dạy thêm cách nói tự nhiên mà không sửa `const.py`, không chỉnh Hassil thủ công và không cần khởi động lại Home Assistant.

Mỗi mục gồm:

- câu nói mới, ví dụ `xem cổng`;
- chức năng hoặc lệnh đích, ví dụ `chụp ảnh camera`;
- thời điểm tạo và cập nhật;
- thông tin câu đó có nhận thêm nội dung phía sau hay không.

Dữ liệu được lưu trong Home Assistant Store:

```text
.storage/conversational_assistant.<config_entry_id>
```

Khi tích hợp khởi động lại, toàn bộ câu đã học được đọc từ Store và đăng ký lại với Conversation agent. Câu mới có hiệu lực ngay sau khi được dạy, không cần reload tích hợp.

## Cách dạy câu lệnh

Mẫu chính:

```text
Học câu lệnh <câu mới> để <lệnh hoặc chức năng đích>
```

Cũng hỗ trợ các cách nói:

```text
Dạy câu lệnh <câu mới> để <lệnh đích>
Thêm câu lệnh <câu mới> để <lệnh đích>
Thêm cách nói <câu mới> thay cho <lệnh đích>
Thêm câu lệnh tùy chỉnh <câu mới> để <lệnh đích>
```

Ví dụ camera:

```text
Học câu lệnh xem cổng để chụp ảnh camera
```

Sau đó chỉ cần nói hoặc gửi Zalo:

```text
Xem cổng
```

Ví dụ nhắc hẹn có nội dung theo sau:

```text
Học câu lệnh việc mới để tạo nhắc hẹn
Việc mới 18h30 ngày mai uống thuốc
```

Phần `18h30 ngày mai uống thuốc` được chuyển tiếp vào bộ phân tích nhắc hẹn hiện có.

Ví dụ macro Home Assistant:

```text
Học câu lệnh đi ngủ để tắt tất cả đèn
Học câu lệnh về nhà để bật đèn phòng khách
Học câu lệnh hôm nay có gì để lịch hôm nay
```

Macro Home Assistant được gửi qua Conversation agent đã cấu hình. Quyền expose thiết bị và các giới hạn hiện có vẫn được áp dụng.

## Chức năng có thể học

- Chụp ảnh camera.
- Tạo, liệt kê và xóa nhắc hẹn.
- Tạo, liệt kê, mở, sửa và xóa ghi chú.
- Xem hướng dẫn.
- Điều khiển hoặc kiểm tra Home Assistant bằng một lệnh đích rõ ràng.
- Thời tiết và lịch khi lệnh đích được Conversation agent nhận diện.

## Quản lý bộ nhớ

```text
Danh sách câu lệnh đã học
Bộ nhớ câu lệnh
Xóa câu lệnh xem cổng
Quên câu lệnh xem cổng
Xóa tất cả câu lệnh đã học
```

Dạy lại cùng một câu với chức năng đích khác sẽ cập nhật mục hiện có.

## Chống nhầm lẫn

Tích hợp từ chối:

- câu quá chung như `có`, `không`, `đồng ý`, `tất cả`;
- câu quản lý bộ nhớ được dùng làm alias;
- câu đã là lệnh tích hợp có sẵn;
- hai alias chồng tiền tố gây nhập nhằng với phần nội dung theo sau;
- câu dài hơn 12 từ hoặc lệnh đích dài hơn 40 từ;
- tổng số câu vượt quá giới hạn 100 câu cho mỗi config entry.

## Sensor

Tích hợp tạo sensor **Số câu lệnh đã học**. Attributes gồm:

- `list_cau_lenh`;
- `cau_lenh_da_hoc`;
- câu nói mới;
- chức năng và lệnh đích;
- khả năng nhận nội dung phía sau;
- thời điểm cập nhật.

## Phạm vi và bảo mật

Bộ nhớ là bộ nhớ chung của một config entry và được dùng chung trên Voice Assist lẫn mọi cuộc trò chuyện Zalo đi qua webhook. Không lưu câu lệnh riêng theo người dùng hoặc nhóm.

Chỉ nên cho nguồn tin cậy dạy macro điều khiển khóa, cửa, báo động, gara hoặc thiết bị nhạy cảm. Bộ nhớ chỉ lưu văn bản alias và lệnh đích; không lưu mật khẩu hay mã xác nhận.
