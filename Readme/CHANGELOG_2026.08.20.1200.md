# Changelog 2026.08.20.1200

## YouTube speaker playback fix

- Sửa lỗi bot báo **Đã phát** dù loa không phát âm thanh.
- Đổi thứ tự loa: gọi `media_extractor.play_media` trước với `media_content_type: music` đúng action schema Home Assistant.
- Không còn dùng `media_extractor.extract_media_url` làm đường phát loa chính. Home Assistant 2026.8 có xử lý YouTube đặc biệt có thể trả muxed audio+video stream (thường itag 18), không phù hợp với một số loa audio-only.
- Sau mỗi lần phát loa, chờ và xác nhận entity chuyển sang `playing` hoặc `buffering` trước khi phản hồi thành công.
- Nếu Media Extractor không làm loa phát, lazy-extract stream audio-only bằng yt-dlp rồi gọi `media_player.play_media` với MIME thực như `audio/mp4`/`audio/webm`.
- Tái sử dụng `config/media_extractor/cookies.txt` khi có.
- Có fallback cuối cho media player tự hiểu URL YouTube.
- Nếu mọi cách đều không làm loa chuyển sang trạng thái phát, trả lỗi rõ ràng thay vì success giả.
- Không import/không chạy yt-dlp lúc integration khởi động; chỉ dùng khi một yêu cầu YouTube loa thực sự cần fallback.
- Version bumped to `2026.08.20.1200`.
