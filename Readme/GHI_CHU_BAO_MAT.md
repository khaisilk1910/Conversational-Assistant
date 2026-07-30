# Conversational Assistant 1.2.1 — Ghi chú bảo mật

## Chức năng

- Thêm, xem danh sách, xem nội dung, sửa và xóa ghi chú bằng Voice Assist hoặc Zalo.
- Hiểu các cách nói tự nhiên như `thêm ghi chú`, `ghi chú`, `ghi nhớ`, `nhớ`.
- Luôn hỏi mức bảo mật và xác nhận trước khi lưu thay đổi hoặc xóa.
- Mức 1 — Bảo mật: nội dung được mã hóa AES-GCM bằng khóa sinh từ pass riêng của từng ghi chú. Pass và nội dung rõ không được lưu trong Home Assistant Store.
- Mức 2 — Công khai: nội dung có thể xuất hiện trong danh sách và sensor.
- Ghi chú Mức 1 trong danh sách chỉ hiện số thứ tự và chữ `Bảo mật`.
- Sau 5 lần nhập sai pass, ghi chú bị khóa tạm thời 5 phút.
- Tất cả ghi chú dùng chung giữa Voice Assist và mọi cuộc trò chuyện Zalo trong cùng config entry Conversational Assistant.
- Hội thoại nhiều bước được tách theo từng thiết bị/chat để câu trả lời xác nhận và pass không bị lẫn.

## Sensor

Cài mới thường tạo entity `sensor.conversational_assistant_so_ghi_chu`.

- State: tổng số ghi chú.
- `list_ghi_chu`: danh sách dạng văn bản; ghi chú Mức 1 luôn là `Bảo mật`.
- `ghi_chu`: metadata an toàn gồm số thứ tự, ID, mức bảo mật, thời gian tạo/cập nhật, nguồn và trạng thái khóa.
- `so_ghi_chu_bao_mat`, `so_ghi_chu_cong_khai`.

## Ví dụ thao tác

### Thêm

1. `Ghi nhớ mã tủ đồ là 2468`
2. Chọn `mức 1` hoặc `mức 2`.
3. Nếu Mức 1, nhập `pass 1234`.
4. Trả lời `có` để lưu hoặc `không` để hủy.

### Xem

- `Danh sách ghi chú`
- Ghi chú công khai: trả lời `số 2`.
- Ghi chú bảo mật: trả lời `số 1 pass 1234` hoặc chọn số trước rồi nhập pass ở lượt tiếp theo.

### Sửa

1. `Sửa ghi chú`
2. Chọn số và mức hiện tại, ví dụ `số 1 mức 1`.
3. Nhập pass nếu là ghi chú bảo mật.
4. Nhập nội dung mới, chọn mức mới, đặt pass mới nếu cần, rồi xác nhận.

### Xóa

1. `Xóa ghi chú`
2. Chọn số và mức hiện tại, ví dụ `số 2 mức 2`.
3. Nhập pass nếu là Mức 1.
4. Trả lời `có` để xóa.

## Khuyến nghị bảo mật

- Với ghi chú nhạy cảm, nên nhập pass bằng Zalo hoặc giao diện văn bản thay vì đọc pass thành tiếng.
- Không dùng chung một pass cho mọi ghi chú.
- Nếu quên pass của ghi chú Mức 1, nội dung không thể khôi phục.
