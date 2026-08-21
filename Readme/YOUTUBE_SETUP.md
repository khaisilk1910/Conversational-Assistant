# YouTube search & playback setup

Conversational Assistant 2026.08.20.1900 tìm YouTube, trả tối đa 10 kết quả và phát tới loa/TV/media player đã đặt tên trong Home Assistant.

## Cấu hình khuyến nghị

1. Mở **Settings > Devices & services > Conversational Assistant > Configure > YouTube Settings**.
2. Nhập `youtube_api_key` của YouTube Data API v3 để tìm kiếm ổn định.
3. Trong **General settings**, đặt tên cho loa và TV/media player.
4. Với loa audio-only, cài integration đang cung cấp action **`yt_dlp.play`**. Conversational Assistant chỉ kiểm tra action này lúc có lệnh phát; không thêm hard dependency nên startup Home Assistant không bị chặn nếu integration đó không có.

## Action loa audio-only được ưu tiên

Sau khi người dùng đã chọn bài và loa, Conversational Assistant gọi đúng dạng:

```yaml
action: yt_dlp.play
data:
  url: https://www.youtube.com/watch?v=VIDEO_ID
  media_player: media_player.phong_ngu_speaker
```

Quy tắc:

- chỉ dùng `yt_dlp.play` khi đích là **loa/speaker/audio-only**;
- `url` lấy trực tiếp từ video người dùng đã chọn trong danh sách tìm kiếm;
- `media_player` lấy trực tiếp từ loa người dùng đã chọn/đã gọi đúng tên;
- không gọi action trước khi cả bài và loa đã được xác định;
- nếu loa đang `playing`/`buffering`, bot vẫn hỏi **Phát đè** hay chờ rảnh tối đa 10 phút; action chỉ chạy sau quyết định đó;
- sau action, tích hợp theo dõi trạng thái loa tối đa 25 giây để tránh báo thành công khi loa chưa thực sự bắt đầu phát;
- nếu `yt_dlp.play` có tồn tại nhưng lỗi, bot trả lỗi action đó và **không** chạy tiếp chuỗi Cast/Media Extractor cũ gây nhiều lần gọi lặp;
- các đường cũ chỉ là compatibility fallback cho hệ thống không có `yt_dlp.play`.

## TV / thiết bị có hình

`yt_dlp.play` **không áp dụng cho TV/video**. TV tiếp tục ưu tiên cách native của Home Assistant:

- Google Cast/Chromecast: mở YouTube app bằng video ID;
- Android TV/Google TV: phát URL YouTube;
- Apple TV: dùng URL scheme YouTube khi platform hỗ trợ;
- sau đó mới dùng fallback media player phù hợp.

## Luồng tìm kiếm và chọn

Ví dụ:

- `Tìm YouTube nhạc bolero phát loa Phòng Ngủ`
- `Mở nhạc vàng trên YouTube ở loa Phòng Khách`
- `Tìm YouTube dạy tiếng Anh phát TV Phòng Ngủ`
- `YouTube nhạc AI ở loa Bếp`

Xử lý:

1. Nếu thiếu nội dung cần tìm → hỏi lại bài/video cần tìm.
2. Nếu thiếu nơi phát → liệt kê loa/TV để chọn.
3. Tìm tối đa 10 kết quả.
4. **Loa/audio-only:** chờ người dùng chọn số hoặc tên video; không tự gọi `yt_dlp.play` khi chưa có lựa chọn video.
5. **TV/video:** vẫn giữ hành vi tương thích cũ: nếu không chọn sau 20 giây có thể lấy video số 1.
6. Sau khi bài + thiết bị rõ ràng mới thực hiện playback.

## Thứ tự tìm kiếm

1. `media_player.search_media` khi entity thực sự hỗ trợ và trả nội dung nhận diện được là YouTube.
2. YouTube Data API v3 với API key trong **YouTube Settings**.
3. `pyscript.youtube_search_tool` làm fallback tương thích cũ.

Không có truy cập YouTube, yt-dlp, FFmpeg hay quét media player nặng nào chạy trong lúc Conversational Assistant khởi động.

## Kiểm thử action `yt_dlp.play`

Trong **Developer Tools > Actions** hãy thử chính entity loa:

```yaml
action: yt_dlp.play
data:
  url: https://youtu.be/z8DLkLnemFY
  media_player: media_player.phong_ngu_speaker
```

Nếu action này phát được, Conversational Assistant 1900 sẽ dùng đúng action đó sau bước chọn video/loa.

## Fallback tương thích

Chỉ khi Home Assistant không đăng ký `yt_dlp.play`, integration mới thử các đường cũ như platform-native, yt-dlp Python/audio proxy, `shell_command.youtube_stream`, Media Extractor hoặc `media_player.play_media` tùy loại thiết bị. Những fallback này không phải đường chính trên hệ thống đã có `yt_dlp.play`.
