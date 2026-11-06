# Clarification policy (planned)

Tài liệu này chốt policy cho vòng hỏi lại thông tin thiếu. Nguồn schema là
[`docs/architecture/Cấu trúc schema.md`](../architecture/Cấu%20trúc%20schema.md),
nhất là mục 2, 6, 9.2, 9.3, 9.4 và 10. Khi policy này nêu field/schema chưa có
trong `shared/contracts.py`, field đó được đánh dấu **planned**; tài liệu không
khẳng định code hiện hành đã hỗ trợ nó.

## 1. Luồng và điều kiện rẽ nhánh

Sau Request Parser và Pydantic validation, CODE tính `pending_fields`.

1. `pending_fields` **rỗng**: đi Destination Agent (Agent A).
2. `pending_fields` **không rỗng**: dùng counter áp dụng để hỏi user nếu còn
   lượt; nếu đã hết lượt thì áp default/fail theo bảng ở mục 4.
3. Một round chỉ tăng khi CODE đã có bộ câu hỏi hợp lệ và thực sự gửi bộ đó cho
   user. Không tăng khi LLM output sai, khi fallback chưa được gửi, hoặc khi
   chỉ tính lại pending fields.

`pending_fields` do CODE quyết định. LLM chỉ extract thay đổi từ lời user và
diễn đạt câu hỏi; LLM không quyết định route, counter, default hay failed.

## 2. Hai counter độc lập (**planned fields/config**)

| Counter | Max | Dùng cho | Không dùng cho |
| --- | ---: | --- | --- |
| `clarification_round` | 3 | Trường thiếu của TripRequest; `needs_more_info` từ Agent A | `needs_user_choice`, `no_valid_candidate` |
| `destination_round` | 2 | `needs_user_choice`, `no_valid_candidate` từ Agent A | Trường thiếu TripRequest, `needs_more_info` |

`max_clarification_rounds=3` đã có trong schema hiện hành. `max_destination_rounds=2`
là **planned** và phải có default tương thích snapshot cũ. `destination_round`
đã có default `0` trong schema hiện hành, nhưng giới hạn/validation đầy đủ là
**planned**.

### Ánh xạ `selection_status`

| `selection_status` | Hành động CODE | Counter |
| --- | --- | --- |
| `selected` | Lưu DestinationResult mới và đi Constraint Planner | Không tăng |
| `needs_more_info` | Gộp `missing_fields` vào `pending_fields`; hỏi/default/fail theo policy TripRequest | `clarification_round` |
| `needs_user_choice` | Soạn lựa chọn từ `candidate_regions`; chờ lựa chọn | `destination_round` |
| `no_valid_candidate` | Hỏi đổi điều kiện khi còn lượt; hết lượt thì failed | `destination_round` |

Với destination `implicit`, nếu Agent A chọn được đúng một khu vực thì trả
`selected`, lưu kết quả và không tốn counter.

## 3. Câu hỏi và câu trả lời

LLM có thể gộp nhiều field vào một câu hỏi. CODE validate đúng một lần trước
khi gửi:

1. mỗi `fields` là tập con của `pending_fields`;
2. hợp các `fields` bao phủ toàn bộ `pending_fields`;
3. mỗi câu có `question` không rỗng và `fields` không rỗng;
4. một field không xuất hiện trong nhiều câu của cùng bộ.

Nếu bất kỳ điều kiện nào sai, CODE dùng ngay câu hỏi mẫu theo field/group field.
Không retry LLM chỉ để soạn lại câu hỏi.

Khi user trả lời, CODE ghi `answers_history` với câu hỏi đã gửi, raw answer,
resolved fields và declared-unknown fields. Giá trị user mới nhất ghi đè giá trị
cũ với `source=user`; không cần cơ chế revision riêng.

### Lựa chọn từ Agent A (**planned option contract**)

Mỗi ứng viên hiển thị phải có `option_id` ổn định cùng city/province/country và
reason. UI chỉ gửi `option_id`. CODE tra `option_id` trong candidate list của
round đang chờ, rồi ghi destination với `source=default` khi áp candidate mặc
định, hoặc `source=user` khi user chọn.

Nếu user gõ tên tự do, CODE chỉ tự khớp khi đúng một candidate. Không khớp hoặc
khớp hơn một candidate thì giữ unresolved và hỏi lại; không tự chọn theo tên.

## 4. Hết lượt, unknown và default

### TripRequest / `clarification_round` hết lượt

| Field/tình huống | Kết quả CODE |
| --- | --- |
| `trip.start_date`, `trip.end_date`, `travelers.adults` | Never-default; còn thiếu thì `failed` |
| `destination.city` khi `selection_mode=explicit` | Never-default; còn thiếu thì `failed` |
| `travelers.children` | Gán `0`, `source=default` |
| `preferences.interests`, `preferences.pace`, `preferences.transport_modes` | Đọc bảng default hệ thống trong config (**planned**), `source=default` |
| `budget.amount`, `budget.scope` chưa có câu trả lời | `amount=null`, không default số tiền, không failed; budget được xử lý soft theo mục 5 |
| `needs_more_info` | Áp dụng bảng này; never-default còn thiếu thì failed |

`declared_unknown` giữ giá trị null và không hỏi lại, **trừ never-default**:
`trip.start_date`, `trip.end_date`, `travelers.adults`, và `destination.city`
khi explicit. Các field ngoại lệ này tiếp tục pending cho tới khi có giá trị hợp
lệ hoặc workflow failed vì hết lượt.

### Destination / `destination_round` hết lượt

| Status | Kết quả CODE |
| --- | --- |
| `needs_user_choice` | Chọn phần tử đầu tiên của `candidate_regions`, ghi `destination.city`, `source=default`, `selection_mode=explicit` |
| `no_valid_candidate` | `failed`; ghi errors và thông báo điều kiện/điểm đến không có ứng viên hợp lệ |

## 5. Ngày và ngân sách

### Ngày

LLM chỉ trích xuất `trip.start_date` và `trip.duration_days`. CODE tính:

```text
trip.end_date = trip.start_date + trip.duration_days - 1 day
```

CODE dùng ngày hiện tại và timezone user để xử lý `14/11` không có năm: lấy lần
sắp tới. Các cụm `tuần sau`, `cuối tuần`, `tháng sau`, cùng mọi ngày đã quá khứ,
được đánh dấu ambiguous/pending và hỏi lại ngày cụ thể; CODE không suy đoán.

### Ngân sách

`budget.amount` và `budget.scope` được hỏi user một lần. Khi user nêu mức tối
đa, `amount` có giá trị và `flexibility=strict`; tính hard/soft được suy ra từ
`amount`, `flexibility` và `meta.field_sources`, không thêm `budget.is_hard`.

Khi user nói “không giới hạn” hoặc “chưa biết”, ghi `amount=null`, đánh dấu
declared_unknown và không hỏi lại. Khi hết clarification rounds mà user chưa
trả lời, vẫn giữ `amount=null`, không failed và không gán số tiền default.

## 6. Resume sau completed (**planned behavior**)

Theo bảng 9.4, yêu cầu user thay đổi sau `completed` resume cùng request:

- ghi input user mới với `source=user`;
- đặt `retry_count=0`, `clarification_round=0`, `destination_round=0`;
- invalidates outputs downstream bị ảnh hưởng;
- artifact mới phải có ID mới; artifact JSON lịch sử giữ immutable;
- chạy lại theo state machine, không tạo request mới chỉ vì user đổi ý.

## 7. Schema/status compatibility

Các ví dụ JSON hiện hành có `destination_round` và
`max_clarification_rounds`; chúng không được giả vờ chứa field **planned** như
`max_destination_rounds` hoặc question options. Khi thêm field mới, schema phải
có default để snapshot JSON cũ deserialize được. Không sửa snapshot cũ hàng
loạt; lần save/resume tiếp theo có thể ghi format mới.

