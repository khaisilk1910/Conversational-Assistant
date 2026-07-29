# Conversational Assistant

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](#phiên-bản)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.7.0%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Language](https://img.shields.io/badge/ngôn%20ngữ-Tiếng%20Việt-red.svg)](#ngôn-ngữ)

**Conversational Assistant** là custom integration cho Home Assistant, tập trung vào trải nghiệm điều khiển bằng ngôn ngữ tự nhiên qua **Home Assistant Assist** và **Zalo**.

Tích hợp kết hợp quản lý nhắc hẹn, ghi chú bảo mật, thông báo đa kênh và điều khiển nhà thông minh trong cùng một cấu hình. Người dùng có thể tạo nhắc hẹn bằng giọng nói, nhận thông báo trên điện thoại, Zalo hoặc loa, đồng thời hỏi trạng thái thiết bị, thời tiết và lịch sự kiện trực tiếp từ Zalo.

> [!IMPORTANT]
> Đây là custom integration do cộng đồng phát triển, không phải tích hợp chính thức do Home Assistant cung cấp. Hãy sao lưu cấu hình Home Assistant trước khi cài đặt hoặc nâng cấp.

---

## Mục lục

- [Tính năng nổi bật](#tính-năng-nổi-bật)
- [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
- [Cài đặt](#cài-đặt)
- [Thêm tích hợp vào Home Assistant](#thêm-tích-hợp-vào-home-assistant)
- [Cấu hình chung](#cấu-hình-chung)
- [Tích hợp Zalo](#tích-hợp-zalo)
- [Điều khiển Home Assistant từ Zalo](#điều-khiển-home-assistant-từ-zalo)
- [Quản lý nhắc hẹn](#quản-lý-nhắc-hẹn)
- [Quản lý ghi chú](#quản-lý-ghi-chú)
- [Sensor được tạo](#sensor-được-tạo)
- [Lưu trữ và bảo mật](#lưu-trữ-và-bảo-mật)
- [Nâng cấp từ tích hợp cũ](#nâng-cấp-từ-tích-hợp-cũ)
- [Khắc phục sự cố](#khắc-phục-sự-cố)
- [Cấu trúc repository](#cấu-trúc-repository)
- [Phát triển và đóng góp](#phát-triển-và-đóng-góp)
- [Phiên bản](#phiên-bản)
- [Giấy phép](#giấy-phép)

---

## Tính năng nổi bật

### Nhắc hẹn bằng ngôn ngữ tự nhiên

- Tạo nhắc hẹn bằng Home Assistant Assist hoặc Zalo.
- Hiểu nhiều định dạng thời gian tiếng Việt:
  - thời gian tương đối: `30 phút nữa`, `2 giờ nữa`, `ngày mai`;
  - giờ dạng số: `18h30`, `18:30`, `1830`, `18 giờ 30 phút`;
  - giờ dạng chữ: `mười tám giờ ba mươi`;
  - ngày cụ thể: `20/10`, `ngày 20 tháng 10`, có hoặc không có năm;
  - thứ trong tuần và các nhóm ngày.
- Hỗ trợ nhắc một lần và nhắc lặp:
  - hằng ngày;
  - các ngày trong tuần;
  - cuối tuần;
  - một hoặc nhiều thứ mỗi tuần;
  - hằng tháng;
  - hằng năm.
- Liệt kê và xóa nhắc hẹn bằng câu lệnh tự nhiên.
- Hỗ trợ chọn nhiều nhắc hẹn để xóa.
- Nhắc lại sau 10 phút hoặc bỏ qua ngay từ thông báo Mobile App.
- Có thể xem thao tác vuốt bỏ thông báo Android là bỏ qua nhắc hẹn.

### Thông báo đa kênh

Mỗi nhắc hẹn có thể được gửi đồng thời tới một hoặc nhiều nơi nhận:

- **Home Assistant Companion App** qua dịch vụ `notify`;
- **Zalo** qua `zalo_bot.send_message`;
- **loa/media player** qua `tts.speak`;
- **Persistent Notification** của Home Assistant khi không có kênh đã chọn nào khả dụng.

Tích hợp tự động quét:

- các thiết bị Mobile App có dịch vụ thông báo đang hoạt động;
- các `media_player` phù hợp để phát TTS;
- các nơi nhận Zalo đã cấu hình;
- chính cuộc trò chuyện Zalo đang gửi lệnh.

Khi bật xác nhận nơi nhận, người dùng có thể trả lời bằng:

```text
1
1 và 3
Điện thoại của Nam
Tất cả
Tất cả điện thoại
Tất cả loa
Tất cả Zalo
```

### Ghi chú công khai và ghi chú bảo mật

- Thêm, xem danh sách, đọc, sửa và xóa ghi chú.
- Ghi chú được dùng chung giữa Assist và các cuộc trò chuyện Zalo trong cùng config entry.
- Hai mức bảo mật:
  - **Mức 1 — Bảo mật:** nội dung được mã hóa và yêu cầu pass để đọc, sửa hoặc xóa;
  - **Mức 2 — Công khai:** nội dung có thể xuất hiện trong danh sách và thuộc tính sensor.
- Mỗi ghi chú bảo mật có salt và nonce riêng.
- Không lưu pass trong Home Assistant Store.
- Khóa tạm thời 5 phút sau 5 lần nhập sai pass.
- Luồng hội thoại được tách theo thiết bị, người dùng hoặc cuộc trò chuyện Zalo để tránh lẫn câu trả lời xác nhận.

### Điều khiển nhà thông minh từ Zalo

- Bật, tắt, mở, đóng, khóa và điều chỉnh thiết bị.
- Kiểm tra trạng thái theo:
  - tên thiết bị;
  - phòng;
  - khu vực;
  - sàn.
- Hỏi nhiệt độ, độ ẩm và thời tiết.
- Đọc sự kiện từ một hoặc nhiều entity `calendar`.
- Chọn Conversation agent riêng để xử lý lệnh Zalo.
- Duy trì `conversation_id` riêng cho từng cuộc trò chuyện.
- Chat nhóm chỉ xử lý các câu lệnh Home Assistant rõ ràng, hạn chế bot phản hồi nhầm vào hội thoại thông thường.
- Chỉ các entity đã được expose cho Assist mới có thể được truy vấn hoặc điều khiển.

### Sensor theo dõi dữ liệu

Tích hợp tạo ba sensor:

- số lượng nhắc hẹn đang hoạt động;
- thời điểm nhắc hẹn tiếp theo;
- số lượng ghi chú.

Các sensor cung cấp thêm thuộc tính để dùng trong dashboard, template và automation.

---

## Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|---|---|
| Home Assistant | `2026.7.0` trở lên |
| Phương thức cấu hình | Config Flow trên giao diện |
| Số config entry | Một |
| Ngôn ngữ câu lệnh | Tối ưu cho tiếng Việt |
| Home Assistant Assist | Cần thiết cho lệnh giọng nói và điều khiển thiết bị từ Zalo |
| Mobile App | Không bắt buộc; cần khi gửi thông báo tới điện thoại |
| TTS và media player | Không bắt buộc; cần khi phát nhắc hẹn qua loa |
| Zalo Bot | Không bắt buộc; cần khi dùng thông báo hoặc lệnh Zalo |
| Calendar/Weather | Không bắt buộc; cần có entity tương ứng khi truy vấn |

### Thành phần phụ thuộc của Home Assistant

Integration khai báo các dependency sau:

```text
conversation
mobile_app
media_player
tts
```

### Yêu cầu khi sử dụng Zalo

Conversational Assistant **không tự tạo endpoint webhook Zalo**. Bạn cần có:

1. một nguồn webhook đang nhận được payload tương thích với `zca-js`;
2. một automation chuyển payload đó tới action của integration;
3. dịch vụ `zalo_bot.send_message` để gửi câu trả lời và thông báo ra Zalo.

---

## Cài đặt

### Cách 1 — Cài qua HACS

Repository chưa nằm trong danh sách mặc định của HACS có thể được thêm dưới dạng **Custom repository**.

1. Mở **HACS** trong Home Assistant.
2. Chọn menu dấu ba chấm ở góc trên bên phải.
3. Chọn **Custom repositories**.
4. Nhập URL repository GitHub của Conversational Assistant.
5. Chọn loại **Integration**.
6. Nhấn **Add**.
7. Tìm **Conversational Assistant** trong HACS và chọn **Download**.
8. Khởi động lại Home Assistant.

Tài liệu HACS: [Custom Repositories](https://hacs.xyz/docs/faq/custom_repositories/)

> [!NOTE]
> Repository cần đặt `hacs.json`, `README.md` và thư mục `custom_components/conversational_assistant` đúng cấu trúc để HACS nhận diện.

### Cách 2 — Cài thủ công

1. Tải phiên bản phát hành mới nhất.
2. Giải nén gói tải về.
3. Sao chép nguyên thư mục:

```text
custom_components/conversational_assistant
```

vào thư mục cấu hình Home Assistant:

```text
/config/custom_components/conversational_assistant
```

4. Kiểm tra cấu trúc cuối cùng:

```text
/config/
└── custom_components/
    └── conversational_assistant/
        ├── __init__.py
        ├── config_flow.py
        ├── const.py
        ├── manager.py
        ├── manifest.json
        ├── models.py
        ├── note_flow.py
        ├── notes.py
        ├── parser.py
        ├── sensor.py
        ├── services.yaml
        ├── strings.json
        ├── targeting.py
        ├── zalo_home_assistant.py
        └── translations/
            ├── en.json
            └── vi.json
```

5. Khởi động lại Home Assistant.
6. Xóa cache hoặc tải lại cứng trình duyệt nếu tên tích hợp hoặc bản dịch chưa cập nhật.

---

## Thêm tích hợp vào Home Assistant

Sau khi Home Assistant khởi động lại:

1. Mở **Cài đặt**.
2. Chọn **Thiết bị & dịch vụ**.
3. Chọn **Thêm tích hợp**.
4. Tìm **Conversational Assistant**.
5. Hoàn thành bước thiết lập ban đầu.

Integration chỉ cho phép một config entry để tránh đăng ký trùng các mẫu câu hội thoại.

---

## Cấu hình chung

Mở:

```text
Cài đặt → Thiết bị & dịch vụ → Conversational Assistant → Cấu hình
```

### Các tùy chọn

| Tùy chọn | Mô tả |
|---|---|
| Vuốt bỏ thông báo cũng được xem là Bỏ qua | Áp dụng cho sự kiện xóa thông báo của Android |
| Hỏi nơi nhận trước khi lưu | Liệt kê điện thoại, Zalo và loa, sau đó chờ người dùng chọn |
| Đưa loa tự quét vào danh sách | Cho phép chọn các media player phù hợp làm nơi phát nhắc hẹn |
| Bộ máy TTS | TTS entity dùng với `tts.speak`; nếu để trống, integration dùng entity TTS đầu tiên tìm được |
| Xử lý lệnh webhook Zalo | Bật hoặc tắt bộ xử lý payload Zalo |
| ID tài khoản Zalo của bot | Dùng để lọc tin nhắn do chính bot gửi |
| Tài khoản Zalo trả lời webhook | Giá trị `account_selection` dùng khi gửi phản hồi |
| Cho phép Zalo điều khiển Home Assistant | Cho phép chuyển lệnh thiết bị, trạng thái, thời tiết và lịch vào Home Assistant |
| Conversation agent dùng cho Zalo | Agent xử lý câu lệnh tự nhiên, mặc định là Home Assistant |

### Thêm nơi nhận Zalo

Trong menu tùy chọn, chọn **Thêm nơi nhận Zalo** và nhập:

| Trường | Ví dụ |
|---|---|
| Tên nơi nhận | `Gia đình`, `Anh Nam` |
| Trạng thái | Bật |
| Loại người nhận | Người dùng hoặc Nhóm |
| Thread ID | ID người dùng hoặc nhóm Zalo |
| Account selection | Số điện thoại/tài khoản bot theo dịch vụ Zalo đang dùng |

Nên đặt tên ngắn, dễ đọc và không trùng nhau để việc chọn nơi nhận bằng giọng nói chính xác hơn.

---

## Tích hợp Zalo

### Action nhận payload

Integration đăng ký action:

```text
conversational_assistant.process_zalo_webhook
```

Action nhận hai trường:

| Trường | Bắt buộc | Mô tả |
|---|---:|---|
| `payload` | Có | JSON object hoặc chuỗi JSON chứa payload Zalo |
| `config_entry_id` | Không | ID config entry; chỉ cần khi có nhiều entry, nhưng integration hiện chỉ cho phép một entry |

### Automation webhook

Giữ nguyên trigger webhook đang dùng và gọi action mới:

```yaml
alias: Conversational Assistant - Zalo webhook
mode: queued
max: 20
triggers:
  - trigger: webhook
    webhook_id: YOUR_ZALO_WEBHOOK_ID
    allowed_methods:
      - POST
    local_only: false

actions:
  - action: conversational_assistant.process_zalo_webhook
    data:
      payload: "{{ trigger.json | to_json }}"
```

> [!WARNING]
> Không dùng nút **Run actions** để kiểm thử automation này vì khi chạy thủ công sẽ không có biến `trigger.json`.

### Payload mẫu

```json
{
  "type": 1,
  "data": {
    "msgId": "8092589555886",
    "uidFrom": "2036121378794772276",
    "content": "Bật đèn phòng khách"
  },
  "threadId": "8606394172334558469",
  "isSelf": false,
  "_accountId": "781454039143291053"
}
```

### Bộ lọc webhook

Payload sẽ bị bỏ qua khi:

- `isSelf` là `true`;
- `data.uidFrom` trùng ID bot đã cấu hình;
- `_accountId` không trùng tài khoản bot đã cấu hình;
- `msgId` đã được xử lý gần đây;
- nội dung không phải tin nhắn văn bản hợp lệ;
- xử lý webhook Zalo đã bị tắt trong tùy chọn.

Bộ nhớ chống trùng giữ tối đa 512 message ID gần nhất trong phiên chạy hiện tại.

### Lệnh trợ giúp

Gửi một trong các câu sau cho bot:

```text
Help
Trợ giúp
Hướng dẫn
Các lệnh
```

Bot sẽ trả về danh sách lệnh rút gọn.

Xem thêm: [ZALO_WEBHOOK.md](ZALO_WEBHOOK.md)

---

## Điều khiển Home Assistant từ Zalo

### Bật tính năng

1. Mở tùy chọn **Conversational Assistant**.
2. Bật **Cho phép Zalo kiểm tra và điều khiển Home Assistant**.
3. Chọn Conversation agent.
4. Expose các entity muốn cho phép điều khiển hoặc truy vấn.

Trong Home Assistant, mở:

```text
Cài đặt → Voice assistants → Expose
```

Chỉ nên expose các entity thực sự cần dùng. Home Assistant áp dụng cơ chế expose nhằm hạn chế việc vô tình điều khiển các thiết bị nhạy cảm như khóa hoặc cửa gara.

Tài liệu Home Assistant: [Exposing entities to Assist](https://www.home-assistant.io/voice_control/voice_remote_expose_devices/)

### Ví dụ điều khiển thiết bị

```text
Bật đèn phòng khách
Tắt toàn bộ đèn tầng 2
Mở rèm phòng ngủ
Khóa cửa chính
Đặt điều hòa phòng khách 25 độ
Tăng nhiệt độ phòng ngủ lên 26 độ
```

### Ví dụ kiểm tra trạng thái

```text
Cửa chính đã khóa chưa?
Đèn phòng khách có đang bật không?
Phòng ngủ đang thế nào?
Tầng 2 có thiết bị nào đang bật?
Kiểm tra trạng thái khu vực sân vườn
Nhiệt độ phòng khách là bao nhiêu?
Độ ẩm phòng ngủ hiện tại
```

### Ví dụ thời tiết

```text
Thời tiết hôm nay thế nào?
Ngày mai có mưa không?
Nhiệt độ ngoài trời hiện tại
```

Kết quả phụ thuộc vào Conversation agent và các entity thời tiết đã expose.

### Ví dụ lịch sự kiện

```text
Lịch hôm nay
Ngày mai có sự kiện gì?
Xem lịch 7 ngày tới
Lịch Gia đình tuần này
```

Integration đọc sự kiện từ các entity `calendar` đã expose, gộp kết quả từ nhiều lịch và sắp xếp theo thời gian.

Xem thêm: [ZALO_HOME_ASSISTANT.md](ZALO_HOME_ASSISTANT.md)

---

## Quản lý nhắc hẹn

### Tạo nhắc hẹn một lần

```text
Nhắc tôi 30 phút nữa uống thuốc
Nhắc tôi 2 giờ nữa kiểm tra máy giặt
Tạo nhắc hẹn 18h30 ngày mai đi tập thể dục
Nhắc tôi 7 giờ sáng ngày 20 tháng 10 gọi cho mẹ
Nhắc tôi 20:15 thứ sáu gửi báo cáo
```

### Tạo nhắc hẹn lặp

```text
Nhắc tôi 7 giờ mỗi ngày uống vitamin
Nhắc tôi 8 giờ từ thứ hai đến thứ sáu đi làm
Nhắc tôi 9 giờ cuối tuần tưới cây
Nhắc tôi 18h30 mỗi tuần thứ hai và thứ năm tập thể dục
Nhắc tôi 9 giờ ngày 15 hàng tháng thanh toán hóa đơn
Nhắc tôi 8 giờ ngày 20 tháng 10 hàng năm mua quà
```

Với nhắc hằng tháng vào ngày 29, 30 hoặc 31, integration dùng ngày cuối tháng khi tháng đó không có ngày tương ứng.

### Chọn nơi nhận

Khi tùy chọn xác nhận nơi nhận được bật, integration đọc hoặc gửi danh sách như:

```text
1 - Điện thoại Pixel
2 - Zalo Gia đình
3 - Loa phòng khách
4 - Loa phòng ngủ
```

Có thể trả lời:

```text
1 và 3
Chọn Zalo Gia đình
Tất cả
Tất cả loa
Bỏ yêu cầu vừa rồi
```

Yêu cầu đang chờ chọn hết hạn sau 5 phút.

### Xem danh sách

```text
Danh sách nhắc hẹn
Liệt kê nhắc nhở
Nhắc hẹn tiếp theo là gì?
```

Assist đọc tối đa 10 nhắc hẹn đầu tiên và thông báo số lượng còn lại. Sensor vẫn chứa danh sách đầy đủ các nhắc hẹn sắp tới.

### Xóa nhắc hẹn

```text
Xóa nhắc hẹn
Xóa nhắc hẹn uống thuốc
Xóa tất cả nhắc hẹn
```

Khi chỉ nói `Xóa nhắc hẹn`, integration hiển thị danh sách đánh số và cho phép chọn một hoặc nhiều mục.

### Thông báo Mobile App

Thông báo có hai action:

- **Nhắc lại 10 phút**;
- **Bỏ qua**.

Với nhắc hẹn một lần, **Bỏ qua** sẽ xóa nhắc hẹn. Với nhắc hẹn lặp, action chỉ bỏ qua lần hiện tại và lịch lặp tiếp tục hoạt động.

---

## Quản lý ghi chú

### Thêm ghi chú

```text
Ghi nhớ mua pin cho khóa cửa
Thêm ghi chú lịch bảo trì máy lọc nước
Nhớ rằng mã tủ đồ là 2468
```

Luồng tạo ghi chú:

1. nhập nội dung;
2. chọn Mức 1 hoặc Mức 2;
3. nhập pass nếu chọn Mức 1;
4. xác nhận lưu.

### Xem danh sách

```text
Danh sách ghi chú
Xem ghi chú
Tôi có ghi chú gì?
```

Ghi chú Mức 1 chỉ hiển thị số thứ tự và nhãn `Bảo mật`. Nội dung không xuất hiện trong danh sách hoặc sensor.

### Đọc ghi chú

```text
Xem ghi chú số 2
Đọc ghi chú số 1
Số 1 pass 1234
```

Ghi chú bảo mật yêu cầu pass chính xác.

### Sửa ghi chú

```text
Sửa ghi chú
Cập nhật ghi chú số 2
```

Integration cho phép thay đổi nội dung, mức bảo mật và pass của ghi chú.

### Xóa ghi chú

```text
Xóa ghi chú
Xóa ghi chú số 3
```

Mọi thao tác xóa đều yêu cầu xác nhận. Ghi chú Mức 1 còn yêu cầu pass trước khi xóa.

### Giới hạn

- Nội dung ghi chú: tối đa 4.000 ký tự.
- Pass: tối thiểu 4 ký tự, tối đa 256 ký tự.
- Sau 5 lần nhập sai: khóa 5 phút.
- Không có cơ chế khôi phục nội dung nếu quên pass.

Xem thêm: [GHI_CHU_BAO_MAT.md](GHI_CHU_BAO_MAT.md)

---

## Sensor được tạo

Tên entity ID thực tế có thể thay đổi theo ngôn ngữ, lịch sử entity registry hoặc thao tác đổi tên của người dùng. Hãy kiểm tra entity trong trang thiết bị của integration thay vì phụ thuộc tuyệt đối vào entity ID ví dụ.

### Sensor số nhắc nhở

**State:** tổng số nhắc hẹn đang hoạt động.

**Thuộc tính:**

| Thuộc tính | Nội dung |
|---|---|
| `list_nhac_nho` | Danh sách nhắc hẹn dạng văn bản |
| `nhac_nho_sap_toi` | Danh sách object gồm số thứ tự, thời gian, nội dung, kiểu lặp và reminder ID |
| `zalo_webhook_enabled` | Trạng thái xử lý webhook Zalo |
| `zalo_webhook_action` | Tên action webhook đang dùng |
| `zalo_webhook_mode` | Chế độ webhook hiện tại |
| `zalo_bot_account_id` | ID bot Zalo đã cấu hình |
| `zalo_home_assistant_enabled` | Trạng thái điều khiển Home Assistant từ Zalo |
| `zalo_conversation_agent_id` | Conversation agent đã chọn |

Ví dụ đọc danh sách trong template:

```jinja2
{{ state_attr('sensor.conversational_assistant_so_nhac_nho', 'list_nhac_nho') }}
```

### Sensor nhắc nhở tiếp theo

**Device class:** `timestamp`.

**State:** thời điểm nhắc hẹn gần nhất.

**Thuộc tính:**

- `reminder_id`;
- `message`;
- `recurrence`;
- `snoozed`.

### Sensor số ghi chú

**State:** tổng số ghi chú.

**Thuộc tính:**

| Thuộc tính | Nội dung |
|---|---|
| `list_ghi_chu` | Danh sách dạng văn bản; ghi chú bảo mật luôn bị che |
| `ghi_chu` | Metadata an toàn của từng ghi chú |
| `so_ghi_chu_bao_mat` | Số ghi chú Mức 1 |
| `so_ghi_chu_cong_khai` | Số ghi chú Mức 2 |
| `bao_mat` | Ghi chú về chính sách che nội dung |

> [!TIP]
> Entity ID ví dụ chỉ mang tính minh họa. Dùng **Developer Tools → States** để lấy entity ID chính xác trên hệ thống của bạn.

---

## Lưu trữ và bảo mật

### Dữ liệu lưu trữ

Dữ liệu được lưu bằng Home Assistant Store với khóa dạng:

```text
conversational_assistant.<config_entry_id>
```

Kho dữ liệu chứa:

- nhắc hẹn;
- quy tắc lặp;
- nơi nhận đã gán cho từng nhắc hẹn;
- ghi chú công khai;
- ciphertext, salt và nonce của ghi chú bảo mật;
- metadata cần thiết để lập lịch và hiển thị sensor.

Hãy sao lưu thư mục `.storage` trước khi gỡ integration hoặc thực hiện thay đổi lớn.

### Mã hóa ghi chú Mức 1

Ghi chú bảo mật sử dụng:

- AES-GCM;
- khóa 256-bit được dẫn xuất từ pass;
- PBKDF2-HMAC-SHA256;
- 260.000 vòng lặp;
- salt ngẫu nhiên 16 byte;
- nonce ngẫu nhiên 12 byte;
- note ID làm associated data.

Pass không được lưu trong Store. Nội dung rõ của ghi chú Mức 1 không được đưa vào sensor.

### Khuyến nghị

- Không đọc pass nhạy cảm thành tiếng ở nơi có người khác.
- Ưu tiên nhập pass qua Zalo hoặc giao diện văn bản.
- Không dùng chung một pass cho tất cả ghi chú.
- Chỉ expose các entity thực sự cần thiết cho Assist.
- Cân nhắc kỹ trước khi expose khóa, cửa gara, báo động hoặc thiết bị có rủi ro an toàn.
- Bảo vệ webhook Zalo và không công khai webhook ID.
- Không commit file `secrets.yaml`, dữ liệu `.storage`, log hoặc payload thật lên Git.

---

## Nâng cấp từ tích hợp cũ

Conversational Assistant sử dụng domain và kho dữ liệu riêng, vì vậy được Home Assistant xem là một integration độc lập.

Trước khi chuyển sang bản mới:

1. sao lưu Home Assistant;
2. ghi lại các nơi nhận Zalo và tùy chọn đang dùng;
3. tắt hoặc gỡ config entry cũ;
4. cài Conversational Assistant;
5. thêm config entry mới;
6. cập nhật automation webhook để gọi:

```text
conversational_assistant.process_zalo_webhook
```

7. tạo lại hoặc chuyển dữ liệu nhắc hẹn, ghi chú nếu cần.

> [!WARNING]
> Không nên chạy đồng thời hai integration có cùng mẫu câu nhắc hẹn và ghi chú. Cả hai có thể cùng nhận một câu lệnh Assist và tạo dữ liệu trùng.

Config entry, entity registry, nhắc hẹn, ghi chú và Store của integration trước đó không được tự động nhập vào Conversational Assistant.

Xem thêm: [CAI_DAT_CONVERSATIONAL_ASSISTANT.md](CAI_DAT_CONVERSATIONAL_ASSISTANT.md)

---

## Khắc phục sự cố

### Không tìm thấy integration sau khi cài

Kiểm tra:

- thư mục phải là `/config/custom_components/conversational_assistant`;
- `manifest.json` phải nằm trực tiếp trong thư mục trên;
- Home Assistant đã được khởi động lại hoàn toàn;
- không có thêm một lớp thư mục do giải nén sai;
- phiên bản Home Assistant đáp ứng yêu cầu tối thiểu.

Sau đó kiểm tra log để tìm lỗi import hoặc lỗi cú pháp.

### HACS không nhận repository

Kiểm tra repository có:

```text
README.md
hacs.json
custom_components/conversational_assistant/manifest.json
```

Trong `hacs.json`, tên integration và phiên bản Home Assistant tối thiểu phải hợp lệ. Khi chuẩn bị công bố chính thức trên HACS, repository còn cần đáp ứng các yêu cầu metadata, tài liệu và brand assets của HACS.

Tài liệu: [HACS publishing requirements](https://hacs.xyz/docs/publish/integration/)

### Zalo nhận webhook nhưng bot không trả lời

Kiểm tra:

- action automation có đúng là `conversational_assistant.process_zalo_webhook`;
- `payload` đang truyền `trigger.json`;
- dịch vụ `zalo_bot.send_message` tồn tại trong **Developer Tools → Actions**;
- `account_selection` đúng tài khoản bot;
- `_accountId` của payload khớp ID bot đã cấu hình;
- webhook processing đang được bật;
- payload không có `isSelf: true`.

### Bot trả lời lặp hai lần

- Kiểm tra có nhiều automation cùng dùng một webhook hay không.
- Kiểm tra integration cũ đã được tắt hoàn toàn.
- Kiểm tra cổng Zalo có gửi hai event cho cùng một tin nhắn hay không.
- Đảm bảo payload có `msgId` ổn định để bộ lọc chống trùng hoạt động.

### Không điều khiển được thiết bị từ Zalo

Kiểm tra:

- quyền điều khiển Home Assistant từ Zalo đã bật;
- Conversation agent đã được chọn và hoạt động;
- entity đã được expose cho Assist;
- tên thiết bị, phòng, khu vực và sàn trong Home Assistant rõ ràng, không trùng;
- người dùng/ngữ cảnh gọi action có đủ quyền.

### Lịch không có sự kiện

Kiểm tra:

- có entity thuộc domain `calendar`;
- calendar đã được expose cho Assist;
- `calendar.get_events` hoạt động;
- tên lịch trong câu hỏi trùng hoặc gần với friendly name của entity;
- khoảng thời gian hỏi thực sự có sự kiện.

### Không thấy điện thoại trong danh sách nơi nhận

Kiểm tra:

- thiết bị đã đăng ký qua Home Assistant Companion App;
- config entry `mobile_app` vẫn hoạt động;
- dịch vụ `notify` của thiết bị tồn tại;
- thiết bị không bị xóa hoặc vô hiệu hóa.

### Không thấy loa hoặc loa không phát

Kiểm tra:

- tùy chọn đưa loa tự quét vào danh sách đang bật;
- media player không ở trạng thái `unavailable` hoặc `unknown`;
- media player hỗ trợ phát nội dung phù hợp;
- có TTS entity;
- action `tts.speak` hoạt động khi thử thủ công;
- loa và Home Assistant có thể truy cập URL media do TTS tạo.

### Tên hoặc bản dịch chưa cập nhật

- Khởi động lại Home Assistant.
- Tải lại cứng trình duyệt.
- Xóa cache frontend nếu cần.
- Kiểm tra không còn thư mục integration cũ hoặc bản sao trùng trong `custom_components`.

### Bật log gỡ lỗi

Thêm vào `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.conversational_assistant: debug
```

Khởi động lại Home Assistant, tái hiện lỗi và kiểm tra **Cài đặt → Hệ thống → Nhật ký**.

> [!CAUTION]
> Trước khi chia sẻ log, hãy xóa webhook ID, thread ID, account ID, số điện thoại, nội dung ghi chú và các thông tin riêng tư khác.

---

## Cấu trúc repository

```text
.
├── .gitignore
├── README.md
├── hacs.json
├── CAI_DAT_CONVERSATIONAL_ASSISTANT.md
├── GHI_CHU_BAO_MAT.md
├── ZALO_HOME_ASSISTANT.md
├── ZALO_WEBHOOK.md
└── custom_components/
    └── conversational_assistant/
        ├── __init__.py
        ├── config_flow.py
        ├── const.py
        ├── manager.py
        ├── manifest.json
        ├── models.py
        ├── note_flow.py
        ├── notes.py
        ├── parser.py
        ├── sensor.py
        ├── services.yaml
        ├── strings.json
        ├── targeting.py
        ├── zalo_home_assistant.py
        └── translations/
            ├── en.json
            └── vi.json
```

### Vai trò các file chính

| File | Vai trò |
|---|---|
| `__init__.py` | Thiết lập integration và đăng ký action webhook |
| `config_flow.py` | Config Flow và Options Flow |
| `const.py` | Domain, tùy chọn, mẫu câu và hằng số |
| `manager.py` | Lập lịch nhắc hẹn, Zalo, thông báo và điều phối chính |
| `parser.py` | Phân tích ngày giờ và quy tắc lặp tiếng Việt |
| `note_flow.py` | Hội thoại nhiều bước cho ghi chú |
| `notes.py` | Mã hóa, giải mã và xác thực ghi chú |
| `zalo_home_assistant.py` | Phân loại truy vấn Home Assistant và định dạng lịch |
| `targeting.py` | Phân tích lựa chọn nơi nhận bằng số, tên hoặc nhóm |
| `sensor.py` | Các sensor và thuộc tính trạng thái |
| `services.yaml` | Mô tả action trên giao diện Home Assistant |
| `translations/` | Bản dịch tiếng Việt và tiếng Anh |

---

## Phát triển và đóng góp

Khi báo lỗi, nên cung cấp:

- phiên bản Conversational Assistant;
- phiên bản Home Assistant;
- phương thức cài đặt HACS hay thủ công;
- loại lệnh: Assist, Zalo, nhắc hẹn, ghi chú, TTS hoặc calendar;
- câu lệnh đầu vào đã được ẩn thông tin nhạy cảm;
- log debug liên quan;
- các bước tái hiện lỗi;
- kết quả mong đợi và kết quả thực tế.

Trước khi gửi pull request, nên kiểm tra:

- mã Python biên dịch thành công;
- JSON và YAML hợp lệ;
- key bản dịch tiếng Việt và tiếng Anh đồng bộ;
- không có thông tin bí mật trong commit;
- không thay đổi domain `conversational_assistant`;
- không thay đổi unique ID hoặc storage key nếu chưa có chiến lược migration;
- luồng Assist, Zalo và hội thoại nhiều bước không đăng ký trùng trigger.

### Kiểm tra nhanh

```bash
python -m compileall custom_components/conversational_assistant
python -m json.tool custom_components/conversational_assistant/manifest.json
python -m json.tool custom_components/conversational_assistant/strings.json
python -m json.tool custom_components/conversational_assistant/translations/vi.json
python -m json.tool custom_components/conversational_assistant/translations/en.json
```

---

## Ngôn ngữ

- Giao diện: tiếng Việt và tiếng Anh.
- Parser nhắc hẹn, ghi chú và bộ phân loại lệnh Zalo: tối ưu cho tiếng Việt.
- Conversation agent xử lý thiết bị và thời tiết có thể hỗ trợ thêm ngôn ngữ tùy theo agent, nhưng integration hiện gửi lệnh Zalo với ngôn ngữ `vi`.

---

## Phiên bản

Phiên bản hiện tại: **1.0.0**

Domain:

```text
conversational_assistant
```

Action webhook:

```text
conversational_assistant.process_zalo_webhook
```

Phiên bản Home Assistant tối thiểu theo `hacs.json`:

```text
2026.7.0
```

---

## Giấy phép

Repository hiện cần có file `LICENSE` riêng trước khi phân phối công khai. Hãy chọn giấy phép phù hợp với mục tiêu dự án và cập nhật phần này bằng tên giấy phép cùng đường dẫn tới file `LICENSE`.

---

## Tuyên bố miễn trừ trách nhiệm

Conversational Assistant có thể điều khiển thiết bị thật trong Home Assistant. Người dùng chịu trách nhiệm cấu hình quyền expose, bảo vệ webhook, kiểm soát tài khoản Zalo và đánh giá rủi ro trước khi cho phép điều khiển khóa, cửa, báo động, thiết bị nhiệt hoặc các hệ thống quan trọng khác.
