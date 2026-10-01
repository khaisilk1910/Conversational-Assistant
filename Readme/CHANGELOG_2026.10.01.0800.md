# 2026.10.01.0800

## Weather settings / Zalo reliability

- Bỏ `send_typing_event` trước bản tin thời tiết theo lịch để tránh chạy đồng thời với `send_message` trên cùng tài khoản Zalo.
- Thêm retry có giới hạn cho lỗi Zalo HTTP 429/500/502/503/504: tối đa 2 lần, backoff 0.75s rồi 1.5s. Chỉ retry đúng chunk đang lỗi.
- Dùng timeout Zalo 15 giây thay cho timeout service chung 60 giây khi gửi bản tin thời tiết.
- Thêm delay chuẩn giữa các chunk dài và serialize forecast/storm scheduled sends để hai lịch trùng giờ không đẩy song song.
- Giữ nguyên local-first: Home Assistant weather entity trước, AI Search chỉ fallback khi dữ liệu native không đủ.
