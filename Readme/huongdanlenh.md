# 📘 HƯỚNG DẪN CONVERSATIONAL ASSISTANT

> Điều khiển Home Assistant, tra cứu thông tin, nhắc hẹn, gửi Zalo, thông báo loa, camera và AI bằng câu nói tự nhiên.

## ⚠️ LƯU Ý KHI GỬI LỆNH QUA ZALO

> Khi bật tùy chọn **“Require an invocation keyword for Zalo”**, mọi **yêu cầu mới trên Zalo** phải bắt đầu bằng từ khóa đã cấu hình trong giao diện.
>
> **Từ khóa mặc định:** `@1080`  
> **Ví dụ:** `@1080 chụp camera cổng`

- Chỉ cần từ khóa khi **bắt đầu một yêu cầu mới**.
- Khi đang trong luồng **chọn thiết bị, xác nhận, hủy, trả lời bổ sung hoặc trò chuyện tiếp**, không cần nhập lại từ khóa.
- Khi luồng đã hoàn tất hoặc hết thời gian chờ, yêu cầu mới tiếp theo phải có từ khóa lại từ đầu.
- Tin nhắn Zalo không có từ khóa và không thuộc luồng đang hoạt động sẽ bị bỏ qua.
- **Home Assistant Assist/Voice không bị ảnh hưởng** bởi thiết lập này.

---

## 🚀 Cách dùng nhanh

- Gửi lệnh bằng **Zalo** hoặc **Home Assistant Assist/Voice**.
- Có thể nói tự nhiên, không phân biệt chữ hoa/thường và hỗ trợ tiếng Việt không dấu.
- Có thể thêm `Hãy` hoặc `Please` ở đầu câu.
- Khi tích hợp hiển thị danh sách, trả lời bằng **số thứ tự**, **tên**, **nhiều số**, `Tất cả` hoặc `Hủy`.
- Thời gian chờ xác nhận mặc định: **120 giây**.

### Xem hướng dẫn

`Trợ giúp` · `Hướng dẫn` · `Các lệnh` · `Các tính năng` · `Help` · `Commands` · `Features`

---

## 1. 🏠 Điều khiển thiết bị

### Lệnh cơ bản

`Bật` · `Tắt` · `Mở` · `Đóng` · `Khóa` · `Mở khóa` · `Dừng` · `Tạm dừng` · `Tiếp tục` · `Phát` · `Quét` · `Dọn dẹp`

**Ví dụ**

- `Bật đèn phòng khách`
- `Tắt toàn bộ đèn tầng 2`
- `Mở rèm phòng ngủ`
- `Khóa cửa chính`
- `Cho robot hút bụi dọn phòng khách`

> Lệnh mở cửa cuốn hoặc cửa gara cần xác nhận trước khi thực hiện.

### Điều hòa

- `Đặt điều hòa phòng khách 25 độ`
- `Tăng nhiệt độ điều hòa phòng ngủ 2 độ`
- `Chuyển điều hòa phòng khách sang chế độ làm mát`
- `Đặt quạt gió điều hòa ở mức thấp`
- `Bật đảo gió điều hòa phòng khách`
- `Chuyển điều hòa phòng ngủ sang chế độ ngủ`
- `Đặt độ ẩm điều hòa phòng ngủ 55 phần trăm`

Hỗ trợ các chức năng entity thực tế có: nhiệt độ, `cool`, `heat`, `dry`, `fan_only`, `auto`, tốc độ quạt, đảo gió, preset và độ ẩm.

### Quạt

- `Bật quạt phòng khách`
- `Đặt quạt phòng khách 60 phần trăm`
- `Tăng tốc độ quạt phòng ngủ 20 phần trăm`
- `Bật quay quạt phòng khách`
- `Đổi hướng quay quạt phòng ngủ`
- `Chuyển quạt phòng ngủ sang chế độ ngủ`

> Nếu thiết bị không hỗ trợ thao tác, tích hợp sẽ hiển thị các chế độ hoặc mức điều khiển hợp lệ.

---

## 2. ⏱️ Hẹn giờ điều khiển thiết bị

Có thể hẹn bật, tắt, mở, đóng hoặc thay đổi chế độ của đèn, quạt, điều hòa, rèm và các thiết bị được hỗ trợ.

**Ví dụ**

- `Tắt quạt phòng khách sau 30 phút`
- `Bật điều hòa phòng ngủ lúc 22 giờ`
- `Sau 10 phút giảm nhiệt độ điều hòa 2 độ`
- `Ngày mai lúc 7 giờ chuyển điều hòa sang chế độ làm mát`
- `Sau 15 phút bật đảo gió điều hòa phòng khách`
- `Ngày mai lúc 6 giờ 30 mở rèm phòng khách`

Lịch hẹn được lưu để tiếp tục hoạt động sau khi Home Assistant khởi động lại. Đến giờ, tích hợp kiểm tra lại thiết bị trước khi thực hiện.

---

## 3. 🔍 Kiểm tra trạng thái nhà

**Từ khóa:** `Kiểm tra` · `Xem trạng thái` · `Cho tôi biết` · `Báo cáo` · `Thiết bị nào`

**Ví dụ**

- `Kiểm tra trạng thái phòng khách`
- `Thiết bị nào đang bật ở tầng 2?`
- `Cửa chính đã khóa chưa?`
- `Cho tôi biết nhiệt độ phòng ngủ`

---

## 4. 🌦️ Thời tiết

**Từ khóa:** `Thời tiết` · `Dự báo` · `Nhiệt độ` · `Độ ẩm` · `Khả năng mưa`

**Ví dụ**

- `Thời tiết hôm nay thế nào?`
- `Dự báo thời tiết ngày mai`
- `Thời tiết 5 ngày tới tại Hà Nội`
- `Cuối tuần này có mưa không?`

Mỗi ngày dự báo được trình bày đủ:

- 📅 Ngày và thứ
- 🌤️ Điều kiện thời tiết
- 🌡️ Nhiệt độ thấp nhất – cao nhất
- 🌧️ Khả năng mưa
- 💧 Độ ẩm
- 💨 Sức gió

> Tra cứu thời tiết và thông tin ngoài hệ thống được thực hiện bằng **AI Search** để lấy dữ liệu mới nhất.

---

## 5. 📅 Lịch và sự kiện

### Tra cứu

- `Xem lịch hôm nay`
- `Tuần tới tôi có lịch gì?`
- `Sự kiện trong 30 ngày tới`
- `Kiểm tra các sự kiện tháng sau`

### Tạo sự kiện

- `Tạo sự kiện họp lúc 18 giờ 30 ngày mai`
- `Thêm cuộc hẹn khám bệnh lúc 9 giờ thứ Hai`

Sau khi tra cứu có thể dùng: `Sửa` · `Xóa` · `Bỏ qua`.

---

## 6. ⏰ Nhắc hẹn

### Tạo nhắc hẹn

- `Nhắc tôi uống thuốc sau 30 phút`
- `Nhắc tôi đi họp lúc 8 giờ ngày mai`
- `Nhắc tôi tập thể dục mỗi thứ Hai lúc 7 giờ`

### Xem hoặc xóa

- `Danh sách nhắc hẹn`
- `Nhắc hẹn tiếp theo là gì?`
- `Xóa nhắc hẹn số 2`
- `Xóa tất cả nhắc hẹn`

---

## 7. 📝 Ghi chú

### Tạo

- `Ghi nhớ mã tủ đồ là 2468`
- `Thêm ghi chú mua sữa chiều nay`

### Quản lý

- `Danh sách ghi chú`
- `Đọc ghi chú số 2`
- `Sửa ghi chú số 3`
- `Xóa ghi chú số 1`

---

## 8. 💬 Trò chuyện và hỏi đáp AI

### Bắt đầu

`Trò chuyện đi` · `Tám đi` · `Buôn đi`

**Ví dụ**

- `Trò chuyện đi, kể tôi nghe một chuyện vui`
- `Tám đi, giải thích cho tôi lỗ đen là gì`
- `Buôn đi, hôm nay có tin công nghệ gì đáng chú ý?`

Tích hợp ưu tiên dữ liệu và công cụ sẵn có của Home Assistant. Khi không có dữ liệu phù hợp, tích hợp mới dùng AI Agent; câu hỏi cần thông tin mới hoặc kiểm chứng sẽ dùng AI Search.

Luồng trò chuyện được giữ **120 giây** sau mỗi phản hồi. Nếu không có trả lời, tích hợp hỏi lại một lần rồi tự kết thúc sau **10 giây**.

---

## 9. 🔎 Tìm kiếm Internet

**Từ khóa:** `Tìm thông tin` · `Tìm kiếm trên mạng` · `Tra cứu` · `Search for` · `Look up`

**Ví dụ**

- `Tìm thông tin giá vàng hôm nay`
- `Tìm kiếm tin tức Home Assistant mới nhất`
- `Tra cứu thời gian diễn ra sự kiện này`

---

## 10. 🎨 Tạo ảnh bằng AI

**Từ khóa:** `Tạo ảnh` · `Tạo bức ảnh` · `Generate image` · `Create image`

**Ví dụ**

- `Tạo ảnh một chú mèo phi hành gia`
- `Tạo bức ảnh ngôi nhà thông minh vào ban đêm`

---

## 11. 📸 Camera

### Chụp ảnh

- `Chụp camera`
- `Chụp ảnh camera cổng`
- `Chụp camera phòng khách và sân trước`

### Phân tích bằng AI

- `Phân tích camera`
- `Kiểm tra camera cổng và sân sau`
- `Phân tích tất cả camera`

Khi danh sách camera xuất hiện, có thể trả lời: `1` · `1 3 5` · tên camera · `Tất cả` · `Hủy`.

---

## 12. 📣 Gửi thông báo Zalo

**Từ khóa:** `Gửi Zalo` · `Thông báo Zalo` · `Báo Zalo`

**Ví dụ**

- `Gửi Zalo ngày mai 8 giờ tất cả nhân viên sale họp`
- `Thông báo Zalo chiều nay 15 giờ họp tại phòng tầng 2`
- `Báo Zalo hệ thống điện tầng 1 đang bảo trì`

### Cách hoạt động

1. Tích hợp liệt kê người dùng và nhóm Zalo đã bật trong cấu hình.
2. Chọn bằng số, tên, nhiều mục hoặc `Tất cả`.
3. Tích hợp chỉ gửi sau khi xác nhận.
4. Nếu nội dung có ngày giờ rõ ràng, tích hợp tạo thêm nhắc hẹn **trước 15 phút**.
5. Nếu một đích lỗi, các đích còn lại vẫn tiếp tục được gửi và kết quả sẽ được báo lại.

---

## 13. 🔊 Thông báo ra loa

**Từ khóa:** `Thông báo loa` · `Báo loa` · `Báo ra loa` · `Thông báo ra loa` · `Gửi loa` · `Nhắn loa`

**Ví dụ**

- `Thông báo loa đến giờ ăn cơm`
- `Báo ra loa phòng khách khách đã đến`
- `Gửi loa nhắc mọi người 8 giờ họp`

### Cách hoạt động

1. Tích hợp liệt kê các loa có thể phát TTS.
2. Chọn một hoặc nhiều loa bằng số, tên hoặc `Tất cả`.
3. Tích hợp kiểm tra loa trước khi phát.
4. Nếu loa đang `playing` hoặc `buffering`, tích hợp chờ **10 giây** rồi kiểm tra lại, tối đa **20 lần**.
5. Nếu loa lỗi, mất kết nối, không khả dụng hoặc vẫn bận, tích hợp báo rõ nguyên nhân.
6. Yêu cầu từ Zalo được phản hồi về Zalo đã gửi lệnh; yêu cầu Voice lỗi được báo về Zalo đầu tiên trong cấu hình.

Phần TTS tự loại emoji, Markdown, ký tự trang trí và xuống dòng; vẫn giữ dấu chấm, phẩy và nhịp câu để giọng đọc tự nhiên.

---

## 14. 🌙 Tra cứu âm – dương lịch

**Ví dụ**

- `Hôm nay âm lịch ngày bao nhiêu?`
- `Đổi ngày 10 tháng 2 năm 2026 dương lịch sang âm lịch`
- `Đổi mùng 1 tháng 7 âm lịch sang dương lịch`
- `Cho tôi biết ngày âm lịch của ngày mai`

> Khi đổi ngày, nên nói rõ **âm lịch** hoặc **dương lịch** và đầy đủ ngày, tháng, năm.

---

## 15. 🧩 Bộ nhớ câu lệnh

### Dạy câu lệnh

- `Học câu lệnh xem cổng để chụp ảnh camera`
- `Thêm câu lệnh coi ngoài sân để phân tích camera`

### Xem hoặc xóa

- `Danh sách câu lệnh đã học`
- `Tôi đã dạy những câu lệnh nào?`
- `Xóa câu lệnh đã học`
- `Xóa tất cả câu lệnh đã học`

---

## 16. ✅ Lựa chọn và xác nhận

### Đồng ý

`Có` · `Đồng ý` · `Xác nhận` · `Được` · `OK` · `Làm đi` · `Gửi đi`

### Hủy hoặc từ chối

`Không` · `Hủy` · `Dừng` · `Thôi` · `Bỏ qua`

### Chọn mục

`1` · `1 3 10` · `Chọn 1 và 3` · tên thiết bị · `Tất cả` · `Toàn bộ`

- Nếu không tìm thấy đúng thiết bị, tích hợp sẽ liệt kê các thiết bị phù hợp để chọn lại.
- Các số chỉ nhiệt độ, phần trăm hoặc thời gian không được hiểu nhầm là số thứ tự.
- Yêu cầu chờ sẽ tự hủy sau **120 giây** nếu không có phản hồi.

---

## 17. 🎙️ Phản hồi Zalo, Voice và TTS

- **Zalo:** hiển thị đầy đủ emoji, tiêu đề, gạch đầu dòng và xuống dòng dễ đọc.
- **Assist/Voice:** nội dung chat được ngắt câu, ngắt dòng và trình bày rõ ràng.
- **TTS:** loại emoji, ký tự đặc biệt, Markdown và xuống dòng nhưng giữ dấu câu để đọc mượt, rõ và có nhấn nhá.
- Tính năng nâng cao trên Voice chỉ được xử lý khi Home Assistant chưa thực hiện sẵn, tránh chạy lệnh hai lần.

---

## ℹ️ Nguyên tắc xử lý

1. Ưu tiên công cụ, entity, service và dữ liệu có sẵn trong Home Assistant.
2. Nếu Home Assistant không xử lý được, tích hợp mới chuyển sang AI Agent.
3. Nội dung cần dữ liệu bên ngoài, thời tiết hoặc thông tin mới sẽ dùng AI Search.
4. Tích hợp không tự gọi action mà thiết bị không hỗ trợ.
5. Khi chưa đủ thông tin, tích hợp sẽ hỏi lại hoặc hiển thị danh sách để lựa chọn.

---

**Conversational Assistant** — điều khiển nhà thông minh và trợ lý AI bằng câu nói tự nhiên.
