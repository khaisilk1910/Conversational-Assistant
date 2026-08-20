# Hướng dẫn Conversational Assistant

## 1. Gọi tích hợp trên Zalo

Khi **Bắt buộc từ khóa gọi tích hợp trên Zalo** đang bật, mọi yêu cầu mới phải bắt đầu bằng đúng **Zalo invocation keyword** trong Settings.

Thay `[TỪ KHÓA]` bằng giá trị đang cấu hình:

- `[TỪ KHÓA] hướng dẫn tích hợp`
- `[TỪ KHÓA] các lệnh tích hợp`
- `[TỪ KHÓA] nhắc Zalo Khải 1 phút nữa uống thuốc`
- `[TỪ KHÓA] chụp Cam Cổng`

Khi bot đang chờ chọn hoặc xác nhận, chỉ cần trả lời trực tiếp, không cần nhập lại từ khóa.

Nếu người dùng đã nhập đúng Zalo invocation keyword nhưng câu yêu cầu **có liên quan một tính năng mà còn mơ hồ**, tích hợp sẽ ưu tiên hỏi lại theo đúng tính năng đó, kèm ví dụ tự nhiên và giữ phiên **120 giây** để người dùng trả lời tiếp mà không cần nhập lại từ khóa. Chỉ khi không nhận ra tính năng liên quan nào, tích hợp mới phản hồi toàn bộ **Các lệnh tích hợp**.

## 2. Hủy phiên ngay lập tức

Trong bất kỳ phiên nào, gửi một trong các lệnh:

- `Hủy`
- `Hủy yêu cầu`
- `Hủy phiên`
- `Dừng yêu cầu`
- `Dừng phiên`
- `Kết thúc phiên`
- `Bỏ yêu cầu vừa rồi`

Lệnh hủy không cần Zalo invocation keyword. Tích hợp sẽ dừng ngay phiên ghi chú, nhắc hẹn, thiết bị, lịch, camera, gửi Zalo, thông báo loa, trò chuyện AI hoặc tác vụ nền đang xử lý. Thời gian chờ chọn hoặc xác nhận là 120 giây.

## 3. Nguyên tắc xử lý và đa luồng

Tích hợp xử lý theo thứ tự cố định để phản hồi nhanh và hạn chế AI can thiệp sai ý:

1. Phân tích bằng parser nội bộ, trạng thái entity và action có sẵn của Home Assistant.
2. Chỉ dùng AI khi parser hoặc công cụ Home Assistant không lấy đủ ý định, nội dung hay thời gian.
3. Chỉ dùng AI Search khi yêu cầu cần dữ liệu Internet hoặc dữ liệu trong Home Assistant không có/không đủ.
4. Kết quả từ action Home Assistant được phản hồi trực tiếp, không gửi qua AI để viết lại lần nữa.
5. Nếu thiếu nội dung, thời gian, thiết bị hoặc đích đến, tích hợp không tự đoán mà hỏi lại rõ ràng.

Mỗi tài khoản Zalo, nhóm/cuộc trò chuyện, người gửi và nguồn Voice có phiên riêng. Nhiều luồng khác nhau có thể chạy đồng thời; lựa chọn, xác nhận, hủy và phản hồi luôn quay về đúng luồng đã tạo yêu cầu.

Các action chặn được giới hạn thời gian ở phía tích hợp. Một camera, lịch, weather, TTS hoặc custom action bị treo sẽ báo lỗi cho đúng yêu cầu thay vì giữ tác vụ vô thời hạn.

## 4. Xem hướng dẫn và danh sách lệnh

### Xem hướng dẫn

Từ khóa: `trợ giúp`, `hướng dẫn`, `hướng dẫn sử dụng`, `hướng dẫn tích hợp`  
Ví dụ: `Hướng dẫn tích hợp`

### Xem tất cả lệnh

Từ khóa: `lệnh tích hợp`, `các lệnh tích hợp`, `xem lệnh tích hợp`, `xem các lệnh tích hợp`, `xem lệnh của tích hợp`, `xem các lệnh của tích hợp`, `liệt kê các lệnh tích hợp`  
Ví dụ: `Các lệnh tích hợp`

Phản hồi được chia theo tính năng, ngắt dòng dễ đọc và mỗi tính năng chỉ có một ví dụ.

## 5. Các lệnh tích hợp

### Thiết bị

Từ khóa: `bật`, `tắt`, `mở`, `đóng`, `khóa`, `mở khóa`, `tăng`, `giảm`, `đặt`, `chỉnh`, `chuyển`, `đổi`, `dừng`, `tạm dừng`, `tiếp tục`, `phát`, `quét`, `dọn dẹp`, `làm sạch`, `xem trạng thái`, `hẹn giờ`, `lên lịch`  
Ví dụ: `Tắt quạt phòng ngủ sau 30 phút`

### Thời tiết và bão

Từ khóa: `thời tiết`, `dự báo thời tiết`, `có mưa không`, `khả năng mưa`, `nhiệt độ`, `độ ẩm`, `chỉ số UV`, `kiểm tra bão`, `áp thấp nhiệt đới`  
Ví dụ: `Thời tiết ngày mai`

Có thể hỏi bằng ngôn ngữ tự nhiên như:

- `Thời tiết hôm nay`
- `Thời tiết ngày mai`
- `Thời tiết 2 ngày tiếp theo`
- `Thời tiết tuần này`
- `Thời tiết ban ngày và ban đêm ngày mai`

Tích hợp xử lý theo thứ tự:

1. Dùng thực thể `weather.*` đã chọn trong **Weather settings**.
2. Gọi action `weather.get_forecasts` với loại phù hợp: `daily`, `hourly` hoặc `twice_daily`.
3. Chuyển ngày giờ UTC của nguồn dự báo sang múi giờ Home Assistant, lọc đúng khoảng ngày người dùng yêu cầu và chỉ phản hồi các trường thực sự có dữ liệu.
4. Chỉ dùng **AI Search** khi không có thực thể weather, action lỗi, dữ liệu không đủ khoảng ngày hoặc người dùng hỏi một địa điểm khác với nguồn weather đã chọn.

Mỗi yêu cầu dự báo hỗ trợ tối đa 7 ngày. Kiểm tra bão/áp thấp vẫn dùng AI Search và nguồn Internet mới nhất vì cần dữ liệu khu vực cùng cảnh báo chính thức.

### Nhắc hẹn

Từ khóa: `nhắc`, `hẹn`, `nhắc tôi`, `tạo nhắc hẹn`, `đặt nhắc hẹn`, `thêm nhắc hẹn`, `xem danh sách nhắc hẹn`, `hủy nhắc hẹn`, `xóa nhắc hẹn`  
Ví dụ: `Nhắc Zalo Khải 1 phút nữa uống thuốc`

Có thể nhắc trực tiếp đến tên **Mobile**, **Zalo** hoặc **loa** đã đặt trong Settings và có thể nêu nhiều tên liên tiếp. Nếu không nêu nơi nhận, tích hợp luôn hiển thị danh sách để chọn.

### Lịch và sự kiện

Từ khóa: `xem lịch`, `kiểm tra lịch`, `sự kiện`, `tạo sự kiện`, `thêm sự kiện`, `đặt lịch`, `lên lịch`, `cuộc họp`, `cuộc hẹn`, `dương lịch`, `lịch dương`, `âm lịch`, `lịch âm`  
Ví dụ Dương lịch: `Tạo sự kiện họp sale ngày mai lúc 8 giờ dương lịch`  
Ví dụ Âm lịch: `Tạo sự kiện giỗ ông ngày 12/8/2026 âm lịch`

- Trong **Calendar settings**, chọn riêng **Dương lịch mặc định** và **Âm lịch mặc định**. Home Assistant tự quét các entity `calendar.*` để chọn.
- Nói rõ `dương lịch` hoặc `lịch dương`: tích hợp ưu tiên Dương lịch đã cấu hình.
- Nói rõ `âm lịch` hoặc `lịch âm`: tích hợp ưu tiên Âm lịch đã cấu hình và dùng `am_lich_viet_nam.convert_date` với `conversion_type: lunar_to_solar` để lấy ngày dịch vụ chuẩn trước khi tạo.
- Không nói loại lịch: nếu đã cấu hình đủ hai loại, tích hợp liệt kê Dương lịch và Âm lịch; nếu chưa cấu hình đủ, tích hợp liệt kê các lịch có quyền ghi trong Home Assistant để chọn.
- Trước khi tạo, tích hợp luôn hiển thị nội dung, ngày giờ và hỏi xác nhận lịch đích.
- Khi phải lưu sự kiện âm vào lịch dương, phần mô tả ghi rõ ngày âm và ngày dương tương ứng.
- Nếu tháng âm có cả tháng thường và tháng nhuận nhưng câu lệnh chưa nói rõ, tích hợp sẽ hỏi lại trước khi tạo để tránh lệch ngày.
- Với sự kiện âm lặp theo tháng hoặc năm, nên cài lịch âm trong Home Assistant và chọn tại Calendar settings vì ngày dương tương ứng thay đổi theo từng kỳ.

### Thông báo loa

Từ khóa: `thông báo loa`, `báo loa`, `báo ra loa`, `thông báo ra loa`, `gửi loa`, `nhắn loa`  
Ví dụ: `Báo loa Phòng Ngủ xuống ăn cơm`

TTS phát khi media player ở trạng thái `idle`, `off` hoặc `paused`. Nếu loa chưa ở một trong ba trạng thái sẵn sàng này, tích hợp kiểm tra lại tối đa **10 lần**, mỗi lần cách nhau **15 giây**. Sau lần kiểm tra thứ 10 mà loa vẫn chưa sẵn sàng, yêu cầu TTS bị hủy và lỗi được gửi về đúng Zalo/Voice đã yêu cầu. Các loa khác nhau vẫn có thể chờ và phát song song; cùng một loa được xếp tuần tự để tránh chồng tiếng.

### YouTube phát ra loa, TV hoặc media player

Từ khóa/cách nói tự nhiên: `YouTube`, `tìm YouTube`, `tìm trên YouTube`, `tìm kiếm YouTube`, `mở YouTube`, `bật YouTube`, `phát YouTube`, `xem YouTube`.  
Ví dụ loa: `Tìm YouTube nhạc bolero phát loa Phòng Ngủ`  
Ví dụ TV: `Tìm YouTube dạy tiếng Anh phát TV Phòng Ngủ`

Luồng xử lý:

1. Tách **nội dung cần tìm** và **thiết bị cần phát** bằng parser nội bộ trước; nếu thiếu một trong hai, bot hỏi lại đúng phần còn thiếu và giữ phiên 120 giây.
2. Ưu tiên `media_player.search_media` nếu media player hỗ trợ tìm kiếm và kết quả trả về là video YouTube.
3. Nếu chưa đủ kết quả, gọi trực tiếp **YouTube Data API v3** bằng `youtube_api_key` trong **Conversational Assistant options > YouTube Settings**. Nếu chưa cấu hình key hoặc API lỗi, `pyscript.youtube_search_tool` đã có sẵn vẫn được thử như fallback tương thích cũ.
4. Trả danh sách tối đa **10 video**, người dùng chọn bằng số hoặc tên. Nếu không trả lời trong **20 giây**, tích hợp tự chọn video số 1.
5. Với **loa**: nếu trạng thái `playing` hoặc `buffering`, bot hỏi **Phát đè** hay tiếp tục chờ. Nếu không phát đè, tích hợp kiểm tra lại mỗi 10 giây, tối đa **10 phút**; loa rảnh thì tự phát, quá 10 phút thì hủy và báo đúng luồng.
6. Với **TV/video player**: phát ngay, không hỏi phát đè. Ưu tiên phương thức native phù hợp Cast/Android TV/Apple TV; sau đó fallback Media Extractor/`media_player.play_media`.
7. Với **loa**, ưu tiên `media_extractor.extract_media_url` lấy audio rồi gọi `media_player.play_media`; nếu không có action đó thì fallback `media_extractor.play_media`.

Nếu chưa cấu hình danh sách TV/media riêng, tích hợp chỉ quét `media_player` **khi có yêu cầu YouTube**, không quét lúc khởi động. Có thể đặt tên TV/media player trong **General settings > TV/thiết bị phát media và tên gọi** để câu lệnh tự nhiên chính xác hơn.

> Khuyến nghị nhập `youtube_api_key` tại **Settings > Devices & services > Conversational Assistant > Configure > YouTube Settings**. Không còn bắt buộc cấu hình key trong Pyscript. Nếu không có key, tích hợp chỉ tìm được khi media player có native `search_media` trả đúng YouTube hoặc `pyscript.youtube_search_tool` đã tự có key; nếu không sẽ hướng dẫn cấu hình. Tất cả truy cập YouTube đều lazy khi có yêu cầu, không chạy lúc Home Assistant khởi động.

### Gửi Zalo

Từ khóa: `gửi Zalo`, `thông báo Zalo`, `báo Zalo`  
Ví dụ: `Thông báo Zalo Khải xuống ăn cơm`

### Chụp camera và gửi Zalo

Từ khóa: `chụp camera`, `chụp cam`, `chụp ảnh từ camera`, `lấy ảnh camera`, `lấy hình camera`, `gửi cam`, `gửi camera`  
Ví dụ: `Chụp Cam Cổng`  
Ví dụ gửi đích: `Chụp Cam Bếp gửi Zalo Khải` hoặc `Gửi Cam Bếp Zalo Khải`

- Nếu camera hoặc Zalo chưa rõ, tích hợp liệt kê và chờ chọn tối đa **120 giây**.
- Nếu chọn nhiều camera, các ảnh được chụp song song. Khi gửi nhiều ảnh, group dùng `zalo_bot.send_images_to_group`, cá nhân dùng `zalo_bot.send_images_to_user`; nếu action nhiều ảnh chưa có thì mới dự phòng gửi từng ảnh.
- Caption ảnh là văn bản thuần, không thêm Markdown `**...**`.

### Hẹn chụp camera gửi Zalo

Ví dụ một lần: `Hẹn 5 phút nữa chụp Cam Bếp gửi Zalo Khải`  
Ví dụ lặp: `Hẹn mỗi 5 phút chụp Camera Bếp gửi Zalo Khải`  
Ví dụ hằng ngày: `Hẹn 15 giờ 30 hàng ngày chụp Cam Bếp gửi Zalo Khải`  
Xem lịch: `Xem lịch chụp camera` hoặc `Liệt kê lịch chụp camera`  
Xóa lịch: `Xóa lịch chụp camera`

- Nếu thiếu/không chắc camera hoặc Zalo, tích hợp liệt kê và giữ đúng phiên chờ xác nhận.
- Khi xóa, tích hợp liệt kê lịch, chờ chọn rồi **hỏi xác nhận xóa** trước khi thực hiện.
- Sensor **Số lịch chụp camera** hiển thị tổng số lịch và thuộc tính chi tiết `lich_chup_camera`, `list_lich_chup_camera`.

### Ghi/xem/quay video camera và gửi Zalo

Cách nói tự nhiên: `xem cam`, `xem camera`, `ghi cam`, `ghi camera`, `quay cam`, `quay camera`, `gửi video camera`, `xem video camera`, `quay video camera`, `ghi video camera`, `gửi video cam`, `xem video cam`.  
Ví dụ Zalo hiện tại: `Xem Cam Bếp`, `Ghi Camera Cổng`, `Quay Cam Sân`  
Ví dụ gửi đích khác: `Gửi video Cam Bếp đến Zalo Khải`, `Ghi Cam Cổng gửi Zalo Hass 1080`

- Trên **Zalo**, nếu câu lệnh không nêu nơi nhận thì video **10 giây** được gửi về chính nhóm/cuộc trò chuyện đang yêu cầu. Không cần cấu hình cuộc trò chuyện đó thành một Zalo destination có tên trước.
- Nếu câu lệnh có tên Zalo đích đã đặt, tích hợp gửi đúng đích đó. Nếu tên Zalo không chắc chắn, bot liệt kê **Zalo hiện tại + các Zalo đã cấu hình** để chọn.
- Nếu camera chưa rõ, bot liệt kê camera và giữ đúng Zalo đích đã xác định; sau khi người dùng chọn camera sẽ tiếp tục ghi và gửi.
- Voice Assist không có “Zalo hiện tại”, nên vẫn liệt kê hoặc dùng tên Zalo đích đã cấu hình.
- Tích hợp dùng `camera.record`; `stream` được kiểm tra/khởi tạo **chỉ khi có yêu cầu video**, không thêm tải vào lúc Conversational Assistant khởi động. Sau khi action kết thúc, tích hợp chờ file `.mp4` có dữ liệu rồi mới gọi `zalo_bot.send_video`.
- Hai yêu cầu cùng lúc tới **cùng một camera** được xếp tuần tự; các camera khác nhau vẫn ghi song song. Nếu một automation ngoài tích hợp đang ghi camera đó, tích hợp chờ và thử lại ngắn hạn trước khi báo lỗi.
- Khi `camera.record` lỗi, phản hồi nêu nguyên nhân có ích như stream chưa sẵn sàng, camera không hỗ trợ stream/record, recorder đang bận, lỗi quyền ghi media hoặc timeout thay vì chỉ báo chung “không quay được video”.

### Phân tích camera

Từ khóa: `phân tích camera`, `phân tích cam`, `kiểm tra camera`, `xem và phân tích camera`  
Ví dụ: `Phân tích Cam Cổng`

### Ghi chú

Từ khóa: `thêm ghi chú`, `tạo ghi chú`, `lưu ghi chú`, `viết ghi chú`, `xem ghi chú`, `liệt kê ghi chú`, `đọc ghi chú`, `sửa ghi chú`, `cập nhật ghi chú`, `xóa ghi chú`  
Ví dụ: `Ghi chú mua sữa`

### Trò chuyện AI

Từ khóa: `trò chuyện đi`, `tám đi`, `buôn đi`, `kết thúc`  
Ví dụ: `Trò chuyện đi`

### Tìm kiếm Internet

Từ khóa: `tìm thông tin`, `tìm kiếm`, `tìm kiếm trên mạng`, `tìm trên mạng`, `tra cứu`  
Ví dụ: `Tìm thông tin giá vàng hôm nay`

### Tạo ảnh AI

Từ khóa: `tạo một bức ảnh`, `tạo bức ảnh`, `tạo một ảnh`, `tạo ảnh`  
Ví dụ: `Tạo ảnh ngôi nhà bên hồ`

### Âm dương lịch

Từ khóa: `âm lịch`, `lịch âm`, `dương lịch`, `lịch dương`, `thứ mấy`, `đổi`, `chuyển`, `quy đổi`, `tra ngày`, `xem ngày`  
Ví dụ: `Đổi 30/11/1984 sang âm lịch`

### Bộ nhớ câu lệnh

Từ khóa: `học câu lệnh`, `dạy câu lệnh`, `thêm câu lệnh`, `thêm cách nói`, `xem câu lệnh đã học`, `xóa câu lệnh`, `quên câu lệnh`  
Ví dụ: `Học câu lệnh xem cổng để chụp Cam Cổng`

### Điều khiển phiên

Từ khóa: `hủy`, `hủy yêu cầu`, `hủy phiên`, `dừng yêu cầu`, `dừng phiên`, `kết thúc phiên`, `bỏ yêu cầu vừa rồi`  
Ví dụ: `Hủy`

## 6. Cách nói tự nhiên theo từng tính năng

Không bắt buộc phải nói đúng một mẫu cứng. Các câu dưới đây là ví dụ để parser nhận ý định trước khi phải dùng AI:

- **Thiết bị:** `Bật đèn phòng khách`, `Tắt hết đèn tầng 2`, `Cho quạt phòng ngủ quay`, `Tăng điều hòa lên 26 độ`, `Chuyển điều hòa sang làm lạnh`, `Tắt quạt sau 20 phút`.
- **Thời tiết:** `Mai có mưa không`, `Thời tiết 3 ngày tới`, `Nhiệt độ chiều nay`, `Độ ẩm ngoài trời`, `UV hôm nay`, `Có bão hay áp thấp nào không`.
- **Nhắc hẹn:** `5 phút nữa nhắc tôi uống thuốc`, `Nhắc Zalo Khải 7 giờ mai họp`, `Mỗi thứ hai 8 giờ nhắc họp`, `Tôi có những nhắc hẹn nào`, `Xóa nhắc hẹn`.
- **Lịch/sự kiện:** `Lịch ngày mai có gì`, `Xem sự kiện tuần này`, `Thêm lịch họp 15 giờ mai`, `Tạo cuộc hẹn 8 giờ thứ tư tuần sau dương lịch`.
- **Loa:** `Báo loa Phòng Ngủ xuống ăn cơm`, `Thông báo ra loa Tầng 1 có khách`, `Gửi loa Phòng Khách chúc ngủ ngon`.
- **YouTube:** `Tìm YouTube nhạc bolero phát loa Phòng Ngủ`, `Mở YouTube nhạc thiếu nhi trên TV Phòng Khách`, `Tìm trên YouTube dạy tiếng Anh phát tivi Phòng Ngủ`.
- **Gửi Zalo:** `Gửi Zalo Khải xuống ăn cơm`, `Báo Zalo Gia đình cửa cổng đang mở`, `Thông báo Zalo Hass 1080 hệ thống đã xong`.
- **Chụp camera:** `Chụp Cam Bếp`, `Lấy ảnh Camera Cổng`, `Gửi Cam Bếp Zalo Khải`, `Chụp Cam Bếp và Cam Cổng gửi Zalo Khải`.
- **Video camera:** `Xem Cam Bếp`, `Ghi Camera Cổng`, `Quay Cam Sân`, `Xem video Cam Bếp`, `Gửi video Cam Bếp đến Zalo Khải`.
- **Lịch chụp camera:** `5 phút nữa chụp Cam Bếp gửi Zalo Khải`, `Hẹn mỗi 5 phút chụp Cam Bếp gửi Zalo Khải`, `15 giờ 30 hàng ngày chụp Cam Bếp gửi Zalo Khải`, `Liệt kê lịch chụp camera`, `Xóa lịch chụp camera`.
- **Phân tích camera:** `Phân tích Cam Cổng`, `Kiểm tra Camera Bếp`, `Xem và phân tích Cam Sân`.
- **Ghi chú:** `Ghi chú mua sữa`, `Lưu ghi chú mã cửa 1234`, `Xem ghi chú`, `Sửa ghi chú mua sữa`, `Xóa ghi chú`.
- **Trò chuyện AI:** `Trò chuyện đi`, `Tám đi`, `Buôn đi`; dùng `Kết thúc` hoặc `Hủy` để dừng phiên.
- **Tìm Internet:** `Tìm giá vàng hôm nay`, `Tra cứu thông tin ...`, `Tìm trên mạng ...`.
- **Tạo ảnh AI:** `Tạo ảnh ngôi nhà bên hồ`, `Tạo một bức ảnh robot trong vườn`.
- **Âm/dương lịch:** `Hôm nay âm lịch ngày mấy`, `Ngày mai thứ mấy`, `Đổi 30/11/1984 sang âm lịch`, `Đổi mùng 1 tháng 8 âm sang dương lịch`.
- **Bộ nhớ câu lệnh:** `Học câu lệnh xem cổng để chụp Cam Cổng`, `Xem câu lệnh đã học`, `Quên câu lệnh xem cổng`.
- **Trợ giúp/phiên:** `Hướng dẫn tích hợp`, `Các lệnh tích hợp`, `Hủy`, `Dừng phiên`, `Bỏ yêu cầu vừa rồi`.

Nếu câu nói rõ camera/thiết bị/đích/thời gian thì tích hợp thực hiện ngay. Nếu chỉ nhận ra **chủ đề** nhưng chưa đủ hành động hoặc đối tượng, bot không tự đoán: bot đưa ví dụ đúng chủ đề và chờ người dùng nói rõ trong 120 giây.

## 7. Cấu hình

Mở **Settings > Devices & services > Conversational Assistant > Configure** để:

- đặt tên Mobile, Zalo, loa, TV/media player và camera;
- chọn thực thể `weather.*` trong **Weather settings** để ưu tiên dữ liệu Home Assistant;
- chọn riêng Dương lịch và Âm lịch mặc định trong **Calendar settings**;
- cấu hình AI Agent, AI Search dự phòng, lịch, bản tin thời tiết và TTS;
- bật hoặc tắt yêu cầu Zalo invocation keyword;
- thay đổi Zalo invocation keyword dùng để gọi tích hợp.


## Phân tích nội dung và mốc thời gian

- Tích hợp phân loại ý định trước: tạo sự kiện không bị nhầm thành tra cứu ngày Âm/Dương lịch.
- Hiểu các cách nói như `thứ 4 tuần sau`, `t4 tuần tới`, `ngày mốt`, `ngày kìa`, giờ dạng `13h30`, `13:30` hoặc `13 giờ 30`.
- Ví dụ: `Thêm sự kiện 13h30 thứ 4 tuần sau dương lịch Họp test sản phẩm`.
- Parser và công cụ Home Assistant luôn chạy trước. Nếu chưa tách đủ thiết bị, nội dung hoặc thời gian, AI chỉ được dùng để chuẩn hóa yêu cầu; AI Search không dùng để đoán ý định mà chỉ tra dữ liệu Internet.
- Quy tắc trên áp dụng cho lịch, nhắc hẹn, gửi Zalo có thời gian, TTS hẹn giờ, thời tiết và hẹn điều khiển thiết bị. Nếu vẫn mơ hồ, tích hợp hỏi lại và không thực hiện ngay.
