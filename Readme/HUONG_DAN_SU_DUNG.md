# Hướng dẫn sử dụng — Conversational Assistant 1.2.1

## Câu lệnh gọi hướng dẫn

Có thể dùng trên Voice Assistant hoặc Zalo:

```text
Hướng dẫn sử dụng tích hợp
Sử dụng tích hợp
Hướng dẫn tích hợp
Học cách sử dụng các tính năng của tích hợp này
Tích hợp có những tính năng gì?
Conversational Assistant làm được gì?
```

Tích hợp cũng nhận các cách nói liên quan đến `trợ giúp`, `các lệnh`, `các tính năng`, `cách dùng tích hợp` và `giới thiệu tích hợp`.

## Nội dung phản hồi

Phản hồi được định dạng thành sáu đầu mục, ngắt dòng rõ ràng:

1. Nhà thông minh.
2. Thời tiết và lịch.
3. Camera.
4. Nhắc hẹn.
5. Ghi chú.
6. Bộ nhớ câu lệnh.

Mỗi đầu mục gồm một mô tả ngắn và hai ví dụ thực tế. Nội dung giống nhau trên Voice Assist và Zalo để người dùng dễ ghi nhớ.

## Ưu tiên xử lý

- Voice Assist đăng ký một trigger riêng cho yêu cầu hướng dẫn.
- Zalo nhận diện cả câu chính xác và các câu tự nhiên có nhắc đến tích hợp hoặc tính năng.
- Khi người dùng yêu cầu hướng dẫn trong lúc đang chọn nơi nhận, chọn camera, tạo hoặc xóa dữ liệu, bước chờ hiện tại được hủy để tránh nhầm lẫn.
- Câu lệnh đã học trỏ đến chức năng `xem hướng dẫn` cũng sử dụng cùng nội dung phản hồi.
