
# Thiết kế schema hệ thống lập lịch trình du lịch đa agent

Tài liệu thiết kế dữ liệu, có phân loại từng phần là CODE hay LLM/Agent

## 0. Cách đọc tài liệu này

### 0.1. Nhãn phân loại

| Nhãn | Ý nghĩa |
| --- | --- |
| [CODE] | Logic xác định (deterministic), viết bằng Python/thuật toán, không gọi LLM. Có thể unit test. |
| [LLM] | Cần LLM/Agent vì đầu vào là ngôn ngữ tự nhiên hoặc cần phán đoán mềm. |
| [HYBRID] | LLM tạo hoặc đề xuất, sau đó CODE kiểm tra, chuẩn hóa hoặc quyết định cuối. |

Nguyên tắc chung: LLM không được là nơi ra quyết định cuối cùng về ràng buộc cứng (ngân sách, giờ mở cửa, giờ phải về). Mọi đầu ra của LLM đều phải đi qua Pydantic validation trước khi sang bước tiếp theo.

### 0.2. Các nội dung được BỔ SUNG so với bản thiết kế gốc

Những mục có nhãn [BỔ SUNG] trong tài liệu là phần mới thêm vào schema. Danh sách đầy đủ:

| # | Vị trí | Nội dung bổ sung | Lý do |
| --- | --- | --- | --- |
| 1 | TripRequest | meta (prompt gốc, độ tin cậy parse), missing_fields (CODE tính, đưa vào pending_fields của WorkflowState) | Orchestrator cần biết hỏi lại gì mà không phải đoán |
| 2 | TripRequest | Trường source (user / inferred) cho các giá trị quan trọng | Phân biệt điều người dùng nói với điều hệ thống suy ra |
| 3 | TimeConstraints | is_hard cho từng giá trị (nguồn user / default / inferred nằm ở TripRequest.meta.field_sources) | Tránh biến giá trị mặc định thành ràng buộc cứng |
| 4 | TimeConstraints | Việc cần hỏi lại ghi ở WorkflowState.pending_fields (mục 9.2), không đặt trong TimeConstraints | Báo cho Orchestrator cần hỏi người dùng |
| 5 | PlaceCandidate | Cấu trúc con cụ thể của weekly_schedule, special_hours; cluster_id | Gốc để mảng rỗng; cluster do DBSCAN gán |
| 6 | CostedPlaceCandidate | admission_price_raw, price_confidence_score | Giữ giá gốc để truy vết |
| 7 | PlanningInput | must_visit_place_ids, avoid_place_ids, weights, solver_config, budget đầy đủ (includes, excludes, flexibility, max_overrun_percent); chi phí dạng khoảng (min, max) kèm price_status và price_confidence_score | Thuật toán cần đủ dữ liệu, không tự suy ra; không làm mất thông tin từ TripRequest và Budget Module C |
| 8 | Itinerary | schema_version, trip_id, optimality_proven, dropped_places, relaxation_suggestions | Giải thích vì sao bỏ địa điểm hoặc không tìm được nghiệm |
| 9 | ValidationResult | schema_version, trip_id, checked_rules, recomputed, suggested_action, severity của warnings | Orchestrator biết quy tắc nào đã chạy và nên làm gì tiếp |
| 10 | WorkflowState | pending_questions, attempts, schema_version, clarification_round, max_clarification_rounds, pending_fields, answers_history, status, errors | Hỗ trợ hỏi lại có giới hạn, retry có lịch sử, tương thích phiên bản |
| 11 | Quy ước chung | Tiền tệ lưu bằng số nguyên (VND không có phần thập phân); giờ lưu dạng ISO 8601 có múi giờ; so sánh bao gồm biên; null là chưa biết, không tự thay bằng 0; schema_version dạng chính.phụ; enum giữ đúng chữ hoa, chữ thường; ID kết quả bất biến (chi tiết ở mục 10) | Tránh lỗi làm tròn, lỗi múi giờ và nhầm giữa chưa biết với bằng 0 |

## 1. Kiến trúc dữ liệu tổng thể

Không ép toàn bộ thông tin vào một schema. Dùng 8 hợp đồng dữ liệu:

| Schema | Mục đích | Thành phần tạo ra | Loại |
| --- | --- | --- | --- |
| TripRequest | Yêu cầu chuyến đi đã trích xuất từ prompt | Request Parser | [HYBRID] |
| DestinationResult | Kết quả chọn điểm đến | Agent A | [HYBRID]: [LLM] + CODE kiểm tra điểm đến tồn tại |
| TimeConstraints | Ràng buộc thời gian chuẩn hóa theo ngày | Constraint Planner | [CODE] |
| PlaceCandidate | Địa điểm ứng viên | Agent B | [HYBRID] |
| CostedPlaceCandidate | Địa điểm kèm chi phí | Budget Module C | [HYBRID] |
| PlanningInput | Toàn bộ dữ liệu cho thuật toán | Planning Input Builder | [CODE] |
| Itinerary | Lịch trình tìm được | Planning Engine | [CODE] |
| ValidationResult | Kết quả kiểm tra | Validator | [CODE] |

Luồng chạy:

```text
User prompt + context
    -> Orchestrator / Request Parser  -> TripRequest
    -> Agent A                    	-> DestinationResult
    -> Constraint Planner         	-> TimeConstraints
    -> Agent B                    	-> PlaceCandidate[]
    -> Budget C                   	-> CostedPlaceCandidate[]
    -> Planning Engine (PlanningInput -> Itinerary)
    -> Validator                  	-> ValidationResult
```

Bảng phân loại thành phần

| Thành phần | Loại | Giải thích |
| --- | --- | --- |
| Request Parser | [HYBRID] | LLM hiểu prompt tự nhiên; Pydantic kiểm tra kiểu và tính hợp lệ |
| Agent A (chọn điểm đến) | [HYBRID] | LLM hiểu sở thích và gợi ý điểm đến; CODE kiểm tra kết quả có trong danh sách điểm đến hỗ trợ |
| Constraint Planner | [CODE] | Quy tắc xác định, áp dụng cấu hình mặc định, tính khung giờ |
| Agent B (tìm địa điểm) | [HYBRID] | Gọi Places API (code) lấy tọa độ, giờ mở cửa; LLM có thể chấm mức phù hợp sở thích và tóm tắt lý do |
| Budget Module C | [HYBRID] | Giá có sẵn thì code chuẩn hóa; giá thiếu thì LLM hoặc mô hình ước tính, bắt buộc gắn status và confidence |
| DBSCAN | [CODE] | Gom cụm theo tọa độ; chạy một lần ở Agent B để gán cluster_id |
| Travel time matrix và travel cost matrix | [CODE] | Planning Input Builder gọi API bản đồ (hoặc mô hình ước tính) để lấy thời gian và khoảng cách; |
| Planning Engine (TOPTW, OR-Tools, ALNS) | [CODE] | Tối ưu hóa; không dùng LLM |
| Validator | [CODE] | Kiểm tra độc lập, không LLM |
| Orchestrator | [CODE] (máy trạng thái) | Quản lý bước, retry, lỗi. Chỉ gọi LLM để viết câu hỏi lại hoặc diễn giải kết quả cho người dùng |
| Giải thích lịch trình cho người dùng | [LLM] | Viết văn bản từ Itinerary đã được validate; không được thay đổi dữ liệu |

## 2. TripRequest

Loại: [HYBRID]. LLM chuyển prompt thành JSON. [CODE] dùng Pydantic để kiểm tra kiểu, định dạng ngày giờ, đơn vị tiền, ràng buộc logic (ngày về không trước ngày đi), rồi tính missing_fields.
Ví dụ sau khi parse

```jsonc
{
  "schema_version": "1.0",

  "destination": {
    "selection_mode": "explicit",
    "city": "Đà Lạt",
    "province": "Lâm Đồng",
    "country": "Việt Nam",
    "candidate_cities": [],
    "preferred_areas": [],
    "must_visit": [],
    "avoid_places": []
  },

  "trip": {
    "start_date": "2026-11-14",
    "end_date": "2026-11-16",
    "duration_days": 3,
    "timezone": "Asia/Ho_Chi_Minh",

    "arrival": {
      "datetime": null,
      "location": null
    },

    "departure": {
      "datetime": null,
      "location": null
    }
  },

  "travelers": {
    "adults": 2,
    "children": 0,
    "children_ages": []
  },

  "budget": {
    "amount": 3000000,
    "currency": "VND",
    "scope": "whole_trip",
    "includes": [
      "admission",
      "food",
    ],
    "excludes": [ ],
    "flexibility": "strict",
    "max_overrun_percent": 0 // ngân sách ddc phép vượt mức
  },

  "preferences": {
    "interests": [
      "nature",
      "food",
      "photography"
    ],
    "pace": "relaxed",
    "transport_modes": [
      "motorbike"
    ]
  },

  "daily_preferences": [
    {
      "day": 1,
      "activity_start": null,
      "activity_end": null,
      "return_by": null,
      "start_location": null,
      "end_location": null,
      "min_activities": null,
      "target_activities": null,
      "max_activities": null,
      "rest_minutes": null,
      "pace_override": null
    }
  ],

  "must_do": [],

  "additional_constraints": [
    {
      "description": "Không muốn leo núi",
      "type": "avoid",
      "is_hard": true
    },
    {
      "description": "Ưu tiên địa điểm ít đông đúc",
      "type": "preference",
      "is_hard": false
    }
  ],

  "meta": {
    "raw_prompt": "...",
    "field_sources": {
      "trip.start_date": "user",
      "trip.timezone": "default",
      "preferences.pace": "inferred"
    },
    "field_confidences": {
      "trip.start_date": 1.0,
      "preferences.pace": 0.85
    }
  },
 "missing_fields": [],
}
```

Selection mode hỗ trợ các giá trị:
- explicit: Người dùng đã chỉ định điểm đến.
- implicit: Người dùng muốn hệ thống chọn điểm đến phù hợp.
- ambiguous: Người dùng đang phân vân giữa các lựa chọn.
Quy tắc meta:

| Loại trường | source | confidence |
| --- | --- | --- |
| Người dùng nói rõ | Có | Không |
| LLM suy luận từ prompt | Có | Có |
| Hệ thống tự đặt mặc định | Có | Không |
| CODE tính toán từ dữ liệu đã xác định | Không | Không |
| Metadata kỹ thuật | Không | Không |

Những trường cần xác nhận lại nếu ko có

| Trường | Điều kiện bắt buộc |
| --- | --- |
| destination.city / destination.selection_mode | Phải xác định được điểm đến hoặc ý định để Agent A lựa chọn |
| trip.start_date và trip.end_date | Phải xác định được khoảng thời gian chuyến đi |
| travelers.adults và travelers.children | Phải xác định được quy mô đoàn, ít nhất theo cách hiểu đã được xác nhận hoặc quy tắc mặc định được người dùng chấp nhận |
| preferences.interests, preferences.pace, preferences.transport_modes | Cần để Agent B chấm mức phù hợp và Constraint Planner đặt nhịp, phương tiện; thiếu thì hỏi lại, hết lượt hỏi thì dùng mặc định của hệ thống (source = default) |
| budget.amount và budget.scope | Bắt buộc nếu hệ thống phải bảo đảm giới hạn ngân sách theo yêu cầu thiết kế |

Quy tắc xác nhận lại:
Hỏi tối đa 3 lần cho một yêu cầu lập lịch trình
→ Hết 3 lần, xử lí giá trị mặc định (source = default). Trạng thái hỏi lại (pending_fields, pending_questions, clarification_round, answers_history) được quản lý ở WorkflowState, mục 9.2
Nếu hỏi lại nhưng người dùng bảo “chưa biết” ,.... thì để giá trị null,, meta - source: user và không hỏi lại
Phân chia LLM / CODE trong bước này

| Việc | Ai làm |
| --- | --- |
| Hiểu "cuối tuần này", "khoảng 2 triệu", "đi thong thả" | [LLM] |
| Đổi ngày tương đối sang ngày tuyệt đối (cần ngày hiện tại truyền vào prompt) | [LLM] sinh, [CODE] kiểm tra |
| Kiểm tra kiểu, định dạng, ngày về >= ngày đi | [CODE] (Pydantic) |
| Tính missing_fields theo danh sách trường bắt buộc | [CODE] |
| Soạn câu hỏi hỏi lại tự nhiên (ghi vào pending_questions ở WorkflowState) | [LLM] |

## 3. Constraint Planner và TimeConstraints

Loại: [CODE]. Đây là phần dữ liệu thời gian dễ sai nhất vì người dùng thường nói thiếu và khác nhau theo ngày.
Input: TripRequest và cấu hình mặc định của hệ thống.
Output:

```jsonc
{
  "days": [
    {
      "day": 1,
      "date": "2026-11-14",
       "activity_window": {"start": {"value": "09:00", "is_hard": false}, "end": {"value": "20:00", "is_hard": false}},
      "target_activity_count": {
        "min": {"value": 2, "is_hard": true},
        "target": {"value": 3, "is_hard": false},
        "max": {"value": 4, "is_hard": true}
      },
      "pace": {"value": "relaxed", "is_hard": false},
      "transport_mode": {"value": ["motorbike"], "is_hard": false},
      "meal_windows": [
        {
          "type": "dinner",
          "start": "17:30",
          "end": "19:30",
          "duration_minutes": 60,
          "required": false
        }
      ],
      "rest_minutes": {"value": 60, "is_hard": false},
      "preferences": [{"value": "nature", "is_hard": false}, {"value": "food", "is_hard": false}]
    },
    {
      "day": 2,
      "date": "2026-11-15",
      "activity_window": {"start": {"value": "09:00", "is_hard": true}, "end": {"value": "12:00", "is_hard": true}},
      "target_activity_count": {
        "min": {"value": 1, "is_hard": true},
        "target": {"value": 2, "is_hard": false},
        "max": {"value": 2, "is_hard": true}
      },
      "pace": {"value": "relaxed", "is_hard": false},
      "transport_mode": {"value": ["motorbike"], "is_hard": false},
      "meal_windows": [],
      "rest_minutes": {"value": 0, "is_hard": true},
      "preferences": [{"value": "nature", "is_hard": false}, {"value": "food", "is_hard": false}]
    }
  ]
}
```

Quy tắc xử lý (đều là [CODE])
- Is hard = true là yêu cầu từ người dùng, ràng buộc cứng
- PlanningInput.time_constraints dùng đúng cấu trúc TimeConstraints ở trên: activity_window, target_activity_count.min/target/max, rest_minutes, mỗi giá trị có is_hard riêng. Planning Input Builder không đổi tên, gộp hoặc bỏ trường.
- Thao tác duy nhất Builder được phép làm là thay giá trị null của start_location_id / end_location_id bằng id điểm thật (arrival_point, departure_point hoặc hotel) trước khi kiểm tra nhất quán với ma trận di chuyển.
- target luôn là giá trị mềm (is_hard = false); min và max mới có thể là ràng buộc cứng.

## 4. Agent A

Loại: [HYBRID]

| Việc | Ai làm |
| --- | --- |
| Nhận TripRequest schema, trích xuất thông tin về khu vực, sở thích, ràng buộc và yêu cầu lựa chọn | [LLM] trích xuất, [CODE] kiểm tra schema |
| Phân loại yêu cầu thành EXPLICIT, IMPLICIT, AMBIGUOUS | [LLM] phân loại, [CODE] kiểm tra tính hợp lệ của nhãn |
| Xử lý EXPLICIT: xác định khu vực đã được người dùng chỉ định | [LLM] trích xuất khu vực, [CODE] chuẩn hóa và xác minh |
| Xử lý IMPLICIT: tìm các khu vực ứng viên dựa trên nhu cầu, sở thích và ràng buộc | [LLM] đề xuất và giải thích, [TOOL/API] hỗ trợ tra cứu thông tin khu vực |
| Xử lý AMBIGUOUS: so sánh các khu vực người dùng đang phân vân theo tiêu chí phù hợp | [LLM] phân tích, so sánh và đưa ra lý do |
| Kiểm tra kết quả | Code |

Input

```jsonc
{
  "destination": {
    "city": null,
    "candidate_cities": ["Đà Lạt", "Nha Trang"],
    "preferred_areas": [],
    "must_visit": [],
    "avoid_places": []
  },
  "trip": {
    "start_date": null,
    "end_date": null,
    "duration_days": null
  },
  "travelers": {
    "adults": 1,
    "children": 0
  },
  "budget": {
    "amount": 3000000,
    "currency": "VND",
    "scope": "whole_trip",
    },
  "preferences": {
   "interests": [
      "ngắm cảnh thiên nhiên",
      "chụp ảnh phong cảnh",
      "khám phá ẩm thực địa phương"
    ],
    "pace": "relaxed",
  },
  "additional_constraints": [
    "không muốn leo núi",
    "ưu tiên địa điểm ít đông đúc"
    ]
  },
  "must_do": [],
  "meta": {
    "raw_prompt": "T có 3 triệu, thích thiên nhiên, đang phân vân Đà Lạt với Nha Trang, chọn giúp t."
  },
}

```

Output (DestinationResult )

```jsonc
{
  "request_type": "AMBIGUOUS",
  "selected_region": {
    "city": "Đà Lạt",
    "province": "Lâm Đồng",
    "country": "Việt Nam"
  },
  “selection_status”: “selected”/”needs_user_choice”/”no_valid_candidate”
  "selection_reason": "Phù hợp với sở thích thiên nhiên của người dùng.",
  "candidate_regions": [
    {
      "city": "Đà Lạt",
      "reason": "Có nhiều hoạt động tham quan thiên nhiên."
    },
    {
      "city": "Nha Trang",
      "reason": "Phù hợp với du lịch biển và nghỉ dưỡng."
    }
  ],
“missing_fields”:[]

}

```

Bảng ánh xạ:

| request_type | Khi nào | Tương ứng selection_mode |
| --- | --- | --- |
| EXPLICIT | Người dùng nêu rõ khu vực | explicit |
| IMPLICIT | Chỉ nêu nhu cầu chung, nhờ hệ thống chọn | implicit |
| AMBIGUOUS | Phân vân giữa ≥ 2 khu vực đã nêu | ambiguous |
| INSUFFICIENT | Không đủ thông tin để chọn | không có |

Bốn giá trị selection_status (CODE chốt, LLM chỉ đề xuất)

| Trạng thái | Khi nào | Orchestrator làm |
| --- | --- | --- |
| selected | Chọn được 1 khu vực | Đi tiếp Constraint Planner |
| needs_user_choice | ≥ 2 ứng viên, chưa chọn được 1 | Thêm destination.city vào pending_fields, hỏi người dùng |
| no_valid_candidate | Không còn ứng viên hợp lệ | Thêm destination.* vào pending_fields, hỏi đổi điều kiện |
| pending_fields (trong WorkflowState) | Thiếu thông tin | Gộp missing_fields vào pending_fields |

### 5. Kiểm tra kết quả (6 check)

CODE kiểm tra kết quả của LLM theo 6 bước:
Đúng schema và enum.
Khu vực có tồn tại.
Khớp tên người dùng đã nêu (chỉ EXPLICIT).
Không vi phạm ràng buộc (khu vực bị loại, ngoài phạm vi hỗ trợ).
Thuộc danh sách phân vân (chỉ AMBIGUOUS).
selection_status khớp với selected_region, candidate_regions và missing_fields.
Khi có lỗi:
Ứng viên sai (check 2, 4, 5): loại ứng viên đó khỏi danh sách.
selected_region sai, hoặc lỗi check 1, 3, 6: gọi lại LLM kèm lỗi, tối đa k lần.
Hết k lần mà vẫn lỗi:
lỗi cấu trúc (check 1, 6): ghi llm_output_invalid, status = failed;
lỗi nội dung (check 2 đến 5): selection_status = no_valid_candidate.

### 6. Hỏi lại người dùng

Tùy selection_status, Orchestrator xử lý như sau:

| selection_status | Orchestrator làm | Bộ đếm |
| --- | --- | --- |
| needs_more_info | Gộp missing_fields vào pending_fields (gộp thêm, không ghi đè) | clarification_round (tối đa 3 lượt) |
| needs_user_choice | Thêm destination.city vào pending_fields, hỏi người dùng chọn trong candidate_regions | destination_round (tối đa 2 lượt) |
| no_valid_candidate | Thêm destination.* vào pending_fields, hỏi người dùng đổi điều kiện | destination_round (tối đa 2 lượt) |

Sau khi người dùng chọn xong:
Ghi destination.city với source = user, đặt selection_mode = explicit.
Chạy lại Agent A theo nhánh EXPLICIT.
Kết quả mới có ID mới.
Hết lượt mà vẫn chưa xong:
needs_user_choice: lấy ứng viên đầu danh sách làm mặc định (source = default).
needs_more_info: áp mặc định theo bảng trường bắt buộc ở mục 2. Không có mặc định hợp lệ thì failed.
no_valid_candidate: không có mặc định, failed.

## 5. Agent B và PlaceCandidate

Loại: [HYBRID].

| Việc | Ai làm |
| --- | --- |
| Gọi Places API, lấy tọa độ, giờ mở cửa | [CODE] |
| Lọc theo exclude_place_ids, loại trùng, gán place_id ổn định | [CODE] |
| Chấm score_places theo mức khớp sở thích, viết reason | [LLM] (hoặc mô hình xếp hạng); code kiểm tra điểm nằm trong 0 đến 100 |
| Ước tính visit_duration khi nguồn không có (khi crawl dữ liệu), kèm source = estimated và confidence | [LLM] hoặc bảng mặc định theo loại; phải đánh dấu là ước tính |
| Gán cluster_id | [CODE] (DBSCAN) |

Input:

```jsonc
 {
   "trip_request": {
 	"destination": {
   	"city": "Đà Lạt",
   	"preferred_areas": [],
   	"must_visit": [],
   	"avoid_places": []
 	},
 	"travelers": {
   	"adults": 1,
   	"children": 0
 	},
 	"preferences": {
   	"interests": ["nature", "food"],
   	"pace": "relaxed",
    	},
 	"must_do": [],
 	"additional_constraints": []
   },

   "destination_result": {
 	"selected_destination_id": "dalat"
   },

{
  "time_constraints": {
    "total_days": 2,
    "opening_time": "09:00", // tính từ min các ngày nếu user có yêu cầu
    "closing_time": "18:00"  // tính từ max các ngày nếu user có yêu cầu
  }
}

```

Output PlaceCandidate[]:

```jsonc
 [
   "max_candidates": 100,
   {
   "place_id": "p001",
   "google_place_id": "ChIJ...",
   "name": "Place A",
   "category": "nature",
   "types": ["park", "tourist_attraction"],
   "google_maps_url": "https://maps.google.com/?cid=example",
   "rating": 4.5,
   "user_rating_count": 1250,
   "business_status": "OPERATIONAL",

   "photos": [
     {
       "photo_reference": "photo_reference_001",
       "url": null,
       "width": 1200,
       "height": 800,
       "attributions": []
     },
     {
       "photo_reference": "photo_reference_002",
       "url": null,
       "width": 800,
       "height": 600,
       "attributions": []
     }
   ],

   "location": {
     "latitude": 11.95,
     "longitude": 108.45,
     "address": null
   },

   "opening_hours": {
     "timezone": "Asia/Ho_Chi_Minh",
     "weekly_schedule": [
       {
         "weekday": 6,
         "open": "07:30",
         "close": "17:00",
         "is_closed": false
       }
     ],
     "special_hours": [
       {
         "date": "2026-12-25",
         "open": null,
         "close": null,
         "is_closed": true,
         "note": "Đóng cửa"
       }
     ]
   },

   "visit_duration": {
     "min_minutes": 60,
     "typical_minutes": 90,
     "max_minutes": 120,
     "source": "crawled",
     "source_url": "https://example.com/place-a",
     "crawled_at": "2026-10-24"
   },

   "suitability": {
     "score_places": 92,
     "matched_interests": ["nature"],
     "reason": "Phù hợp sở thích thiên nhiên"
   },

   "constraints": {
     "reservation_required": false,
     "accessibility_notes": []
   },

   "cluster_id": null,

   "data_quality": {
     "source": "places_provider", // nguồn lấy dữ liệu
     "opening_hours_verified": false,
     "last_verified_at": null
   }
   "source": {
      "type": "user_requested", // hoặc “agent_suggested” và không có trường original_name
      "original_name": "Bà Nà Hill"
  }

   },

   {
   "place_id": "p002",
   "google_place_id": "ChIJ...",
   "name": "Place B",
   "category": "food",
   "types": ["restaurant", "food"],
   "google_maps_url": "https://maps.google.com/?cid=example2",
   "rating": 4.3,
   "user_rating_count": 680,
   "business_status": "OPERATIONAL",

   "photos": [],

   "location": {
     "latitude": 11.94,
     "longitude": 108.44,
     "address": null
   },

   "opening_hours": {
     "timezone": "Asia/Ho_Chi_Minh",
     "weekly_schedule": [
       {
         "weekday": 6,
         "open": "08:00",
         "close": "21:00",
         "is_closed": false
       }
     ],
     "special_hours": []
   },

   "visit_duration": {
     "min_minutes": 30,
     "typical_minutes": 60,
     "max_minutes": 90,
     "source": "estimated", "confidence": 0.6,
     "reason": "Ước tính dựa trên loại hình địa điểm ăn uống và thời gian dùng bữa thông thường."
   },

   "suitability": {
     "score_places": 85,
     "matched_interests": ["food"],
     "reason": "Phù hợp với sở thích khám phá ẩm thực"
   },

   "constraints": {
     "reservation_required": false,
     "accessibility_notes": []
   },

   "cluster_id": null,

   "data_quality": {
     "source": "places_provider",
     "opening_hours_verified": false,
     "last_verified_at": null
   }
   "source": {
      "type": "user_requested", // hoặc “agent_suggested” và không có trường original_name
      "original_name": "Bà Nà Hill"
   }

   },

   {
     "place_id": "p003",
     "google_place_id": "ChIJ...",
     "name": "Place C",
     "category": "nature",
     "types": ["park", "tourist_attraction"],
     "google_maps_url": "https://maps.google.com/?cid=example3",
     "rating": 4.4,
     "user_rating_count": 910,
     "business_status": "OPERATIONAL",
     "photos": [],
     "location": {"latitude": 11.93, "longitude": 108.46, "address": null},
     "opening_hours": {
       "timezone": "Asia/Ho_Chi_Minh",
       "weekly_schedule": [{"weekday": 7, "open": "08:00", "close": "17:00", "is_closed": false}],
       "special_hours": []
     },
     "visit_duration": {
       "min_minutes": 60,
       "typical_minutes": 90,
       "max_minutes": 120,
       "source": "estimated", "confidence": 0.7,
       "reason": "Ước tính dựa trên loại hình công viên, tham quan nhẹ nhàng."
     },
     "suitability": {"score_places": 78, "matched_interests": ["nature"], "reason": "Phù hợp sở thích thiên nhiên"},
     "constraints": {"reservation_required": false, "accessibility_notes": []},
     "cluster_id": null,
     "data_quality": {"source": "places_provider", "opening_hours_verified": false, "last_verified_at": null,

  "source": {
      "type":  “agent_suggested”
     }
   },
]
```

B không quyết định lịch trình cuối và không tính tổng chi phí toàn chuyến. place_id phải ổn định để nối dữ liệu giữa B, C và Planning Engine.

## 6. Budget Module C và CostedPlaceCandidate

Loại: [HYBRID]. Tách chi phí từng địa điểm khỏi ngân sách toàn chuyến để không nhầm giá vé với tổng chi phí thực tế.

| Việc | Ai làm |
| --- | --- |
| Chuẩn hóa giá có sẵn (theo người/nhóm, đổi tiền tệ) | [CODE] |
| Ước tính giá khi thiếu (tra bảng, hỏi LLM, mô hình thống kê) | [LLM] hoặc mô hình ước tính; luôn gắn price_status = ESTIMATED và confidence |
| Nhân số người, cộng các khoản theo basis | [CODE] |
| Xác định chi phí ăn uống lấy từ chi phí các địa điểm ăn uống | [CODE] theo bảng đơn giá hoặc mô hình ước tính; luôn gắn price_status và confidence (xem 6.2) |

Input:

```jsonc
//triprequest
{
  "budget": {
    "amount": 2000000,
    "currency": "VND",
    "scope": "whole_trip",
    "includes": [
      "admission",
      "food"
    ],
    "excludes": [],
    "flexibility": "strict",
     "max_overrun_percent": 0,
    "preferences": {
      "food": "HIGH",
      "admission": "NORMAL",
      }
    },
  "travel_dates": {
    "start_date": "2026-12-20",
    "end_date": "2026-12-22"
  },
  "travelers": {
    "adults": 1,
    "children": 0,
     "children_ages": []
  },
  "must_visit_place_ids": ["p001"]
//output của B
  "places": [
    {
      "place_id": "p001",
      "google_place_id": "ChIJ...",
      "name": "Place A",
      "category": "nature",
      "types": ["park", "tourist_attraction"],
      "address": null
      "score_places": 92
    },
    {
      "place_id": "p002",
      "google_place_id": "ChIJ...",
      "name": "Place B",
      "category": "food",
      "types": ["restaurant", "food"],
       "address": null
      "score_places": 85
    },
    {
      "place_id": "p003",
      "google_place_id": "ChIJ...",
      "name": "Place C",
      "category": "nature",
      "types": ["park", "tourist_attraction"],
      "address": null,
      "score_places": 78
    }
  ]
 }
```

Output CostedPlaceCandidate[]:

```jsonc
{
  "places": [
    {
      "place_id": "p001",
      "google_place_id": "ChIJ...",
      "name": "Place A",
      "category": "nature",
      "types": ["park", "tourist_attraction"],
      "address": null,
      "score_places": 92,
      "price_status": "ESTIMATED",
      "price_confidence_score": 0.75,
      "estimated_total_cost": {"min": 40000, "max": 60000, "currency": "VND"}
    },
    {
      "place_id": "p002",
      "google_place_id": "ChIJ...",
      "name": "Place B",
      "category": "food",
      "types": ["restaurant", "food"],
      "address": null,
      "score_places": 85,
      "price_status": "ESTIMATED",
      "price_confidence_score": 0.65,
      "estimated_total_cost": {"min": 120000, "max": 200000, "currency": "VND"}
    },
    {
      "place_id": "p003",
      "google_place_id": "ChIJ...",
      "name": "Place C",
      "category": "nature",
      "types": ["park", "tourist_attraction"],
      "address": null,
      "score_places": 78,
      "price_status": "ESTIMATED",
      "price_confidence_score": 0.7,
      "estimated_total_cost": {"min": 30000, "max": 50000, "currency": "VND"}
    }
  ],
  "missing_costs": [],
  "budget_reason": "Chi phí có thể cao hơn mức ngân sách dự kiến cho một bữa ăn."
}
```

Quy tắc
- Giá chưa biết không được cộng thành 0 rồi coi là miễn phí. Phải dùng price_status = UNKNOWN hoặc ước tính có nguồn, và đưa vào missing_costs.
- Chỉ ghi amount = 0 khi có nguồn xác nhận miễn phí (price_status = VERIFIED_FREE).
- C không loại cứng địa điểm chỉ vì giá riêng lẻ cao. Địa điểm đắt vẫn có thể được chọn nếu là ưu tiên bắt buộc; việc chọn do Planning Engine cân nhắc trên toàn lịch trình.

### 6.2. Chi phí ăn uống

Chi phí ăn uống được xử lý tương tự các địa điểm tham quan. Mỗi nhà hàng, quán ăn hoặc địa điểm ăn uống thuộc category = food trong danh sách ứng viên của B.
Nếu có dữ liệu giá, CODE chuẩn hóa và tính chi phí theo số người.
Nếu thiếu dữ liệu giá, LLM hoặc mô hình ước tính xác định khoảng chi phí phù hợp với loại hình ăn uống, kèm price_status
Chi phí đầu ra được lưu trong estimated_total_cost của từng địa điểm.
Không xây dựng mô hình tính tổng chi phí ăn uống riêng trong Module C. Tổng chi phí các địa điểm được chọn sẽ do Planning Engine tính toán.

## 7. Planning Engine

### 7.1. PlanningInput

Loại: [CODE]. Một hàm builder gom dữ liệu từ các bước trước, kiểm tra tính nhất quán (mọi place_id có trong ma trận, mọi ngày có điểm bắt đầu và kết thúc), rồi mới gọi bộ giải.
Gồm 6 nhóm dữ liệu: danh sách địa điểm có chi phí (dạng khoảng min–max kèm trạng thái giá), ràng buộc thời gian theo ngày (đúng cấu trúc TimeConstraints), ngân sách và phạm vi chi phí, ma trận thời gian di chuyển, ma trận khoảng cách di chuyển, cấu hình tối ưu.

```jsonc
{
  "trip_id": "trip_001",
  "schema_version": "1.0",
  "budget": {
    "amount": 3000000,
    "currency": "VND",
    "scope": "whole_trip",
    "includes": ["admission", "food"],
    "excludes": [null],
    "flexibility": "strict",
    "max_overrun_percent": 0
  },
"candidate_places": [
    {
      "place_id": "p001",
      "types": ["park", "tourist_attraction"],
      "score_places": 92,
      "visit_duration_typical": 90,
      "estimated_total_cost": {"min": 40000, "max": 60000, "currency": "VND"},
      "price_status": "ESTIMATED",
      "latitude": 11.95,
      "longitude": 108.45,
      "cluster_id": 0,
      "opening_hours": {
        "timezone": "Asia/Ho_Chi_Minh",
        "weekly_schedule": [{"weekday": 6, "open": "07:30", "close": "17:00", "is_closed": false}],
        "special_hours": [{"date": "2026-12-25", "open": null, "close": null, "is_closed": true, "note": "Đóng cửa"}]
      }
    },
    {
      "place_id": "p002",
      "types": ["restaurant", "food"],
      "score_places": 85,
      "visit_duration_typical": 60,
      "estimated_total_cost": {"min": 120000, "max": 200000, "currency": "VND"},
      "price_status": "ESTIMATED",
      "latitude": 11.94,
      "longitude": 108.44,
      "cluster_id": 0,
      "opening_hours": {
        "timezone": "Asia/Ho_Chi_Minh",
        "weekly_schedule": [{"weekday": 6, "open": "08:00", "close": "21:00", "is_closed": false}],
        "special_hours": []
      }
    },
    {
      "place_id": "p003",
      "types": ["restaurant", "dinner"],
      "score_places": 78,
      "visit_duration_typical": 90,
      "estimated_total_cost": {"min": 30000, "max": 50000, "currency": "VND"},
      "price_status": "ESTIMATED",
      "latitude": 11.93,
      "longitude": 108.46,
      "cluster_id": 1,
      "opening_hours": {
        "timezone": "Asia/Ho_Chi_Minh",
        "weekly_schedule": [{"weekday": 7, "open": "08:00", "close": "17:00", "is_closed": false}],
        "special_hours": []
      }
    }
  ],
  "must_visit_place_ids": [],
  "avoid_place_ids": [],
  "time_constraints": {
    "days": [
      {
        "day": 1,
        "date": "2026-11-14",
        "activity_window": {"start": {"value": "09:00", "is_hard": false}, "end": {"value": "20:00", "is_hard": false}},
        "target_activity_count": {
          "min": {"value": 2, "is_hard": true},
          "target": {"value": 3, "is_hard": false},
          "max": {"value": 4, "is_hard": true}
        },
        "pace": {"value": "relaxed", "is_hard": false},
        "meal_windows": [
          {
            "type": "dinner",
            "start": "17:30",
            "end": "19:30",
            "duration_minutes": 60,
            "required": false
          }
        ],
        "rest_minutes": {"value": 60, "is_hard": false},
        "preferences": [{"value": "nature", "is_hard": false}, {"value": "food", "is_hard": false}]
      },
      {
        "day": 2,
        "date": "2026-11-15",
        "activity_window": {"start": {"value": "09:00", "is_hard": true}, "end": {"value": "12:00", "is_hard": true}},
        "target_activity_count": {
          "min": {"value": 1, "is_hard": true},
          "target": {"value": 2, "is_hard": false},
          "max": {"value": 2, "is_hard": true}
        },
        "pace": {"value": "relaxed", "is_hard": false},
        "meal_windows": [],
        "rest_minutes": {"value": 0, "is_hard": true},
        "preferences": [{"value": "nature", "is_hard": false}, {"value": "food", "is_hard": false}]
      }
    ]
  },
  "travel_time_matrix": {
    "locations": ["p001", "p002", "p003"],
    "mode": "motorbike",
    "unit": "minutes",
    "values": [
      [0, 10, 25, 30, 35, 20],
      [10, 0, 15, 15, 10, 20],
      [25, 15, 0, 20, 15, 25],
      [30, 15, 20, 0, 25, 30],
      [35, 10, 15, 25, 0, 25],
      [20, 20, 25, 30, 25, 0]
    ]
  },
  "travel_distance_matrix": {
    "locations": ["p001", "p002", "p003"],
   “mode”: “motorbike”
    “unit”: “m”
    "values": [
      [0, 8000, 20000, 24000, 28000, 16000],
      [8000, 0, 12000, 12000, 8000, 16000],
      [20000, 12000, 0, 16000, 12000, 20000],
      [24000, 12000, 16000, 0, 20000, 24000],
      [28000, 8000, 12000, 20000, 0, 20000],
      [16000, 16000, 20000, 24000, 20000, 0]
    ],
  },
  "weights": {"alpha": 1.0, "beta": 0.3, "gamma": 0.2, "delta": 0.5, "normalized": true},
  "optimization": {
    "objective": "maximize_total_utility",
    "allow_optional_places_to_be_skipped": true,
    "cost_basis_hard_limit": "max",
    "cost_basis_objective": "midpoint"
  },
  "solver_config": {"time_limit_seconds": 30, "random_seed": 42, "max_retries": 3}
}
```

[BỔ SUNG] must_visit_place_ids, avoid_place_ids, price_status, is_hard, weights, solver_config, mode của ma trận, cùng các trường includes, excludes, flexibility, max_overrun_percent của budget. Mọi số liệu trong ví dụ (ma trận, trọng số, đơn giá) chỉ minh họa.
Ma trận phải tạo từ dữ liệu di chuyển thật, và locations phải chứa đủ điểm xuất phát, điểm kết thúc và các điểm ứng viên. Nên ghi mode vì xe máy và đi bộ cho ma trận khác nhau.
Nguồn dữ liệu của C_total. (1) Chi phí địa điểm, kể cả địa điểm ăn uống, lấy từ estimated_total_cost của từng candidate (do Budget Module C cung cấp, giữ nguyên tên và cấu trúc). (2) meal_windows chỉ là khung giờ, không chứa chi phí: bữa ăn được tính khi một địa điểm ăn uống (category = food ở Agent B) được xếp vào khung đó, nên chi phí ăn uống đã nằm trong (1). Nếu meal_windows có required = true mà không xếp được địa điểm ăn uống, Planning Engine trả infeasible hoặc đề xuất nới lỏng, không tự cộng một khoản ăn uống mặc định. Chỉ các khoản thuộc budget.includes mới được cộng vào C_total. Địa điểm ăn uống được nhận diện bằng types giao với danh sách FOOD_TYPES (cấu hình dùng chung với Validator), vì PlanningInput không có trường category.
Chi phí dạng khoảng. estimated_total_cost giữ {min, max} cùng price_status và price_confidence_score. Ràng buộc ngân sách cứng dùng cận trên (max); hàm mục tiêu dùng trung điểm (min + max) / 2. Địa điểm có price_status = UNKNOWN không bao giờ được truyền với chi phí 0: Builder yêu cầu Budget Module C ước tính lại, hoặc loại khỏi danh sách ứng viên và ghi vào diagnostics.warnings.
Ngân sách. budget giữ đủ phạm vi và độ linh hoạt từ TripRequest. Mức trần cứng B = amount × (1 + max_overrun_percent / 100). Khi flexibility = strict thì max_overrun_percent = 0 nên B = amount. Khi cho phép vượt, phần chi phí vượt amount nhưng chưa vượt B được tính vào P_soft (mục 7.3).
Giờ mở cửa. opening_hours giữ nguyên cấu trúc của PlaceCandidate (timezone, weekly_schedule, special_hours). weekday theo ISO 8601: 1 = thứ Hai, 7 = Chủ nhật. special_hours của một ngày cụ thể ghi đè weekly_schedule của ngày đó; Builder đổi ngày của chuyến sang weekday theo timezone của địa điểm trước khi kiểm tra giờ mở cửa.
Cụm địa điểm. cluster_id do Agent B gán bằng DBSCAN; Planning Engine chỉ đọc, không chạy lại DBSCAN.

### 7.2. Phân chia trách nhiệm thuật toán (tất cả là [CODE])

| Thành phần | Nhiệm vụ |
| --- | --- |
| cluster_id (DBSCAN chạy ở Agent B) | Planning Engine không chạy lại DBSCAN. Chỉ đọc cluster_id do Agent B gán để hỗ trợ phân vùng không gian (ví dụ phân cụm theo ngày, giảm kích thước bài toán) |
| TOPTW | Mô hình hóa việc chọn địa điểm có phần thưởng, thời gian phục vụ và khung giờ, nhiều ngày |
| OR-Tools | Mô hình hóa ràng buộc thời gian, chi phí và tìm nghiệm |
| ALNS | Cải thiện nghiệm bằng các bước loại, chèn, thay thế địa điểm |

Không bắt buộc dùng đồng thời. Trách nhiệm chạy DBSCAN chỉ thuộc Agent B (mục 5); Planning Engine nhận kết quả qua cluster_id. DBSCAN không xử lý ngân sách; ngân sách phải đưa vào mô hình tối ưu. TOPTW chuẩn cần mở rộng để xử lý chi phí và điều kiện theo ngày.

### 7.3. Hàm mục tiêu

max ( alpha * S_places - beta * T_travel - gamma * C_total - delta * P_soft )  Ràng buộc cứng:  C_max <= B, với B = amount × (1 + max_overrun_percent / 100)
- S_places = Σ score_places của các địa điểm được chọn / (100 × Σ max_activity_count của các ngày). Nằm trong [0, 1].
- T_travel = tổng thời gian di chuyển (kể cả chặng về) / tổng độ dài activity_window của các ngày (phút), tối đa 1.
- C_total = chi phí kỳ vọng (trung điểm min–max) của các địa điểm được chọn và các chặng di chuyển thuộc budget.includes, chia cho B. C_max là cùng phạm vi nhưng cộng cận trên max, dùng cho ràng buộc cứng.
- P_soft = trung bình cộng của 5 thành phần phạt, mỗi thành phần nằm trong [0, 1] và tính trung bình qua các ngày: (1) số hoạt động lệch khỏi target_activity_count.target, chia cho (max − min); (2) thời gian vượt activity_window mềm, chia cho độ dài khung giờ; (3) thời gian nghỉ (khoảng trống giữa các hoạt động, không dùng để di chuyển hay tham quan) thiếu so với rest_minutes mềm, chia cho rest_minutes; (4) phần chi phí vượt amount nhưng chưa vượt B, chia cho (B − amount), tính trên cận trên C_max; (5) tỷ lệ sở thích mềm (is_hard = false) bị vi phạm (một sở thích mềm của ngày bị coi là vi phạm khi không có hoạt động nào của ngày đó có types khớp sở thích theo bảng INTEREST_TYPES, cấu hình của Engine; Validator không kiểm tra thành phần này). Thành phần có mẫu số bằng 0 được tính là 0.
Ngân sách tối đa là ràng buộc cứng nếu người dùng nói rõ không được vượt. Không chỉ trừ điểm khi vượt ngân sách, vì bộ giải vẫn có thể chọn lịch trình vượt giới hạn nếu các điểm khác đủ cao. Mỗi đại lượng được chuẩn hóa về thang 0 đến 1 theo các công thức trên trước khi áp trọng số; weights.normalized = true nghĩa là bộ giải dùng đúng các công thức chuẩn hóa này, nếu không chi phí tính bằng đồng sẽ lấn át các điểm số còn lại.
score_budget (từ Budget Module C) không tham gia hàm mục tiêu và không được truyền vào PlanningInput. Trường này chỉ dùng để giải thích ngân sách và để Builder xếp hạng khi cắt danh sách xuống max_candidates. Ảnh hưởng của chi phí lên lịch trình chỉ đi qua C_total, ràng buộc B và thành phần (4) của P_soft.

### 7.4. Output: Itinerary

```jsonc
{
  "schema_version": "1.0", "trip_id": "trip_001", "status": "feasible",
  "currency": "VND",
  "days": [
    {
      "day": 1,
      "date": "2026-11-14",
      "activities": [
        {
          "place_id": "p001",
          "types": ["park", "tourist_attraction"],
          "arrival_time": "15:30",
          "start_time": "15:30",
          "departure_time": "17:00",
          "travel_minutes_from_previous": 25,
          "estimated_total_cost": {"min": 40000, "max": 60000}
        },
        {
          "place_id": "p002",
          "types": ["restaurant", "food"],
          "arrival_time": "17:20",
          "start_time": "17:30",
          "departure_time": "18:30",
          "travel_minutes_from_previous": 20,
          "estimated_total_cost": {"min": 120000, "max": 200000}
        }
      ],
      "day_total_cost": {"min": 208000, "max": 332000}
    },
    {
      "day": 2,
      "date": "2026-11-15",
      "activities": [
        {
          "place_id": "p003",
          "types": ["park", "tourist_attraction"],
          "arrival_time": "09:20",
          "start_time": "09:20",
          "departure_time": "10:50",
          "travel_minutes_from_previous": 10,
          "estimated_total_cost": {"min": 30000, "max": 50000}
        }
      ],
    ],
  "summary": {
    "total_scheduled_places": 3,
    "total_cost": {"min": 266000, "max": 424000},
    "total_travel_minutes": 95,
    "objective_value": 0.25,
    "summary_message": "Đã sắp xếp 3 địa điểm trong 2 ngày, tổng thời gian di chuyển 95 phút (gồm các chặng về). Lịch trình đáp ứng các ràng buộc thời gian và ngân sách."
  },
  "dropped_places": [],
  "relaxation_suggestions": [],
  "diagnostics": {
    "solver_status": "feasible", // infeasible , partial
    "optimality_proven": false,
    "unsatisfied_constraints": [],
    "warnings": []
  }
}

[BỔ SUNG] schema_version, trip_id, dropped_places, relaxation_suggestions, optimality_proven.
•         objective_value là giá trị hàm mục tiêu tính trên các đại lượng đã chuẩn hóa (mục 7.3), không phải phần trăm chất lượng.
•         solver_status phải phản ánh trạng thái thật của bộ giải. Với ALNS, trả feasible kèm optimality_proven: false, vì nghiệm tốt chưa chứng minh tối ưu toàn cục.
•         Các giá trị status hỗ trợ: feasible, infeasible (không có nghiệm thỏa toàn bộ ràng buộc đã mô hình hóa), partial (lịch trình một phần, chưa đủ yêu cầu), error (lỗi bộ giải hoặc dữ liệu).
•         Khi infeasible, relaxation_suggestions liệt kê các ràng buộc có thể nới (tăng ngân sách, kéo dài khung giờ, bỏ một địa điểm bắt buộc), do [CODE] sinh ra bằng cách chạy lại mô hình với từng ràng buộc được nới. [LLM] chỉ dùng để diễn đạt lại cho người dùng.
```

- Chi phí trong Itinerary giữ dạng khoảng {min, max}. Quy tắc nhất quán: day_total_cost = Σ estimated_total_cost của ngày đó, chỉ cộng các khoản thuộc budget.includes như C_total ở 7.3; summary; summary.total_scheduled_places = tổng số activities của mọi ngày.
- dropped_places liệt kê địa điểm ứng viên không được xếp lịch. Ví dụ trên xếp đủ cả 3 ứng viên nên mảng rỗng; khi có địa điểm bị bỏ, mỗi phần tử có dạng {"place_id": "...", "reason": "closed_at_arrival_time"}.

## 8. Validator

Loại: [CODE] hoàn toàn, không dùng LLM. Validator phải độc lập với Planning Engine, tính lại mọi thứ từ dữ liệu gốc thay vì tin vào số liệu mà bộ giải tự báo.

### 8.1. Nguyên tắc

- Tính lại từ PlanningInput. Thời gian di chuyển lấy từ travel_time_matrix, chi phí địa điểm từ candidate_places, giờ mở cửa từ opening_hours, khung giờ và số hoạt động từ time_constraints. Các số do Engine báo trong Itinerary (travel_minutes_from_previous, day_total_cost, summary) chỉ dùng để đối chiếu, không dùng làm đầu vào tính toán.
- Độc lập về mã, chung về dữ liệu. Validator không import hàm của Planning Engine. Hai bên chỉ dùng chung dữ liệu cấu hình (ví dụ danh sách FOOD_TYPES ở 8.5); nếu dùng chung cả mã thì một lỗi cài đặt ở Engine sẽ lặp lại ở Validator và không bị phát hiện.
- Chỉ đọc. Validator không sửa Itinerary; chỉ báo vi phạm và đề xuất hành động.
- Xác định. Cùng đầu vào cho cùng đầu ra; không gọi API, mạng hay LLM; mọi phép tính tiền và thời gian dùng số nguyên (VND, phút), không dùng số thực.
- Không âm thầm bỏ qua. Validator không dừng ở lỗi đầu tiên (trừ cổng input_integrity) để Orchestrator thấy đủ danh sách lỗi. Quy tắc nào không chạy được thì tính là lỗi; is_valid = true chỉ khi đủ 14 quy tắc bắt buộc nằm trong checked_rules và không có vi phạm cứng.
- Không biết lịch sử retry. Validator chỉ đề xuất hành động dựa trên kết quả kiểm tra; việc kết hợp với giới hạn retry thuộc Orchestrator (mục 9.3).

### 8.2. Đầu vào

| Đầu vào | Nội dung dùng |
| --- | --- |
| Itinerary (7.4) | Lịch trình cần kiểm tra, gồm status, days, summary, dropped_places, relaxation_suggestions, diagnostics. |
| PlanningInput (7.1) | Nguồn dữ liệu gốc: budget, candidate_places, must_visit_place_ids, avoid_place_ids, time_constraints, travel_time_matrix, travel_distance_matrix. Validator không đọc lại TripRequest hay PlaceCandidate vì 7.1 đã giữ nguyên các thông tin cần thiết. |
| Quy tắc nghiệp vụ bổ sung | Cấu hình dạng dữ liệu: LOW_PRICE_CONFIDENCE (ngưỡng độ tin cậy giá thấp, mặc định 0.5). |

```jsonc
{
  "itinerary": {
    "schema_version": "1.0",
    "trip_id": "trip_001",
    "status": "feasible",
    "currency": "VND",
    "days": [
      {
        "day": 1,
        "date": "2026-11-14",
        "activities": [
          {
            "place_id": "p001",
            "arrival_time": "09:20",
            "start_time": "09:30",
            "departure_time": "11:00",
            "travel_minutes_from_previous": null,
            "estimated_total_cost": {
              "min": 40000,
              "max": 60000
            }
          },
          {
            "place_id": "p002",
            "arrival_time": "11:30",
            "start_time": "12:00",
            "departure_time": "13:00",
            "travel_minutes_from_previous": 30,
            "estimated_total_cost": {
              "min": 120000,
              "max": 200000
            }
          }
        ],
        "day_total_cost": {
          "min": 160000,
          "max": 260000
        }
      }
    ],
    "summary": {
      "total_scheduled_places": 2,
      "total_cost": {
        "min": 160000,
        "max": 260000
      },
      "total_travel_minutes": 50
    },
    "dropped_places": [],
    "relaxation_suggestions": [],
    "diagnostics": {
      "unsatisfied_constraints": []
    }
  },
  "planning_input": {
    "schema_version": "1.0",
    "trip_id": "trip_001",
    "budget": {
      "amount": 3000000,
      "currency": "VND",
     “scope”: “whole trip”
      "includes": [
        "admission",
        "food"
      ],
      "excludes": [],
      "flexibility": "strict",
      "max_overrun_percent": 0
    },
    "candidate_places": [
      {
        "place_id": "p001",
         “category”: “nature”
        "types": ["park", "tourist_attraction"],
        "visit_duration_typical": 90,
        "estimated_total_cost": {
          "min": 40000,
          "max": 60000,
          "currency": "VND"
        },
        "price_status": "ESTIMATED",
        "price_confidence_score": 0.75,
        "opening_hours": {
          "timezone": "Asia/Ho_Chi_Minh",
          "weekly_schedule": [
            {
              "weekday": 6,
              "open": "07:30",
              "close": "17:00",
              "is_closed": false
            }
          ],
          "special_hours": []
        }
      },
      {
        "place_id": "p002",
        “category”: “food”
        "types": ["restaurant", "dinner"],
        "visit_duration_typical": 60,
        "estimated_total_cost": {
          "min": 120000,
          "max": 200000,
          "currency": "VND"
        },
        "price_status": "ESTIMATED",
        "price_confidence_score": 0.65,
        "opening_hours": {
          "timezone": "Asia/Ho_Chi_Minh",
          "weekly_schedule": [
            {
              "weekday": 6,
              "open": "08:00",
              "close": "21:00",
              "is_closed": false
            }
          ],
          "special_hours": []
        }
      }
    ],
    "must_visit_place_ids": ["p001"],
    "avoid_place_ids": [],
    "time_constraints": {
      "days": [
        {
          "day": 1,
          "date": "2026-11-14",
          "activity_window": {
            "start": {
              "value": "09:00",
              "is_hard": false
            },
            "end": {
              "value": "18:00",
              "is_hard": false
            }
          },
          "target_activity_count": {
            "min": {
              "value": 1,
              "is_hard": true
            },
            "target": {
              "value": 2,
              "is_hard": false
            },
            "max": {
              "value": 3,
              "is_hard": true
            }
          },
          "meal_windows": [
            {
              "type": "lunch",
              "start": "11:30",
              "end": "13:30",
              "duration_minutes": 60,
              "required": true
            }
          ],
          "rest_minutes": {
            "value": 30,
            "is_hard": false
          }
        }
      ]
    },
    "travel_time_matrix": {
      "locations": ["p001", "p002"],
      "mode": "motorbike",
      "unit": "minutes",
      "values": [
        [0, 30],
        [30, 0]
      ]
    },
"travel_distance_matrix": {
    "locations": ["p001", "p002"],
    “mode”: “motorbike”
    "unit": "m",
    "values": [
      [0, 12000],
      [12000, 0]
    ]
   }
  }
{
  },
  "validation_config": {
       "LOW_PRICE_CONFIDENCE": 0.5
  }
}
```

### 8.3. Đầu ra: ValidationResult

Ví dụ hợp lệ (Itinerary ở 7.4)

```jsonc
{
  "schema_version": "1.0",
  "trip_id": "trip_001",
  "is_valid": true,
  "violations": [],
  "warnings": [
    {
      "type": "estimated_cost",
      "rule": "price_integrity",
      "severity": "info",
      "place_id": "p001",
      "message": "Chi phí địa điểm chưa được xác minh"
    },
    {
      "type": "estimated_cost",
      "rule": "price_integrity",
      "severity": "info",
      "place_id": "p002",
      "message": "Chi phí địa điểm chưa được xác minh"
    },
    {
      "type": "estimated_cost",
      "rule": "price_integrity",
      "severity": "info",
      "place_id": "p003",
      "message": "Chi phí địa điểm chưa được xác minh"
    },
    {
      "type": "rest_shortfall",
      "rule": "rest_time",
      "severity": "soft",
      "day": 1,
      "actual": 10,
      "expected": 60,
      "message": "Thời gian nghỉ ngày 1 thiếu 50 phút so với mong muốn"
    },
    {
      "type": "activity_count_off_target",
      "rule": "activity_count",
      "severity": "soft",
      "day": 1,
      "actual": 2,
      "target": 3,
      "message": "Số hoạt động ngày 1 ít hơn mục tiêu 1 địa điểm"
    },
    {
      "type": "activity_count_off_target",
      "rule": "activity_count",
      "severity": "soft",
      "day": 2,
      "actual": 1,
      "target": 2,
      "message": "Số hoạt động ngày 2 ít hơn mục tiêu 1 địa điểm"
    }
  ],
  "checked_rules": [
    "input_integrity", "price_integrity", "travel_time", "overlap",
    "opening_hours", "visit_duration", "day_window", "day_end_window",
    "meal_window", "activity_count", "rest_time", "must_visit", "budget",
    "summary_consistency"
  ],
  "recomputed": {
    "cost_in_scope": {"min": 266000, "max": 424000},
    "budget_limit": 3000000,
    "total_travel_minutes": 95,
    "total_scheduled_places": 3
  },
  "suggested_action": "accept"
}
```

| Trường | Ý nghĩa |
| --- | --- |
| schema_version, trip_id | Phiên bản schema và mã chuyến đi, để ghép kết quả với đúng PlanningInput. |
| is_valid | true khi violations rỗng và checked_rules đủ 14 quy tắc ở 8.4. |
| violations | Chỉ chứa vi phạm cứng (severity = "hard"). Trường chung: type, rule, severity, message; tùy loại có thêm day, place_id, actual, limit hoặc deadline, cost_basis. |
| warnings | Điều không làm lịch trình sai nhưng cần báo. severity = "soft": lệch ràng buộc mềm (is_hard = false), có số đo tương ứng thành phần của P_soft ở 7.3. severity = "info": thông tin về chất lượng dữ liệu (chi phí ước tính, độ tin cậy thấp). |
| checked_rules | Tên các quy tắc đã chạy, để biết "hợp lệ" không phải do không kiểm tra. |
| recomputed | Số liệu Validator tự tính lại: chi phí trong phạm vi budget.includes (min, max), mức trần B, tổng thời gian di chuyển, số địa điểm đã xếp. Dùng để đối chiếu với summary và để Orchestrator, người kiểm thử đọc nhanh. |
| suggested_action | accept, replan, ask_user hoặc fail (quy tắc chọn ở 8.6). |

[BỔ SUNG] checked_rules, suggested_action, schema_version, trip_id, recomputed, phân loại severity của warnings.

### 8.4. Danh mục quy tắc kiểm tra

Mười bốn quy tắc dưới đây đều bắt buộc. Thứ tự bảng là thứ tự chạy; ngoài cổng input_integrity, thứ tự không ảnh hưởng kết quả. Ràng buộc có is_hard = false không bao giờ tạo vi phạm cứng mà chỉ tạo cảnh báo soft.

| # | Quy tắc | Kiểm tra | type tạo ra |
| --- | --- | --- | --- |
| 1 | input_integrity | Cổng chạy đầu tiên, lỗi ở đây thì dừng.<br>•Số ngày và ngày tương ứng trong Itinerary khớp với time_constraints; currency khớp budget.currency; schema_version cùng phiên bản chính<br>•Mọi place_id trong activities và dropped_places phải tồn tại trong candidate_places; các địa điểm được xếp lịch phải có trong locations của cả travel_time_matrix và travel_distance_matrix. Hai ma trận phải có cùng danh sách locations, kích thước hợp lệ và tương ứng với số lượng địa điểm.<br>•flexibility = strict thì max_overrun_percent = 0 (7.1).<br>•status thuộc feasible, partial, infeasible, error. Với infeasible hoặc error không có lịch để kiểm, dừng tại đây. | planning_input_inconsistent<br>itinerary_input_mismatch<br>unknown_place_id<br>itinerary_not_feasible (infeasible, partial)<br>solver_error (error) |
| 2 | price_integrity | Không coi giá chưa biết là 0 (checklist mục 11).<br>•Địa điểm đã xếp có price_status = UNKNOWN.<br>•estimated_total_cost.max = 0 mà price_status khác VERIFIED_FREE.<br>•min âm hoặc min > max.<br>•Cảnh báo khi ESTIMATED hoặc price_confidence_score < LOW_PRICE_CONFIDENCE. | unknown_price_scheduled<br>zero_cost_unverified<br>invalid_cost_range<br>cảnh báo: estimated_cost (info), low_price_confidence (soft) |
| 3 | travel_time | Chỉ kiểm tra thời gian di chuyển giữa hai hoạt động liên tiếp trong cùng ngày, không kiểm tra chặng đến hoạt động đầu tiên và chặng sau hoạt động cuối cùng. | Tra thời gian di chuyển trong travel_time_matrix theo place_id của hai hoạt động.<br>travel_minutes_from_previous của hoạt động sau phải bằng thời gian trong ma trận.<br>arrival_time của hoạt động sau phải ≥ departure_time của hoạt động trước + thời gian di chuyển trong ma trận.<br>travel_time_mismatch<br>travel_time_insufficient |
| 4 | overlap | •Mỗi hoạt động: arrival_time ≤ start_time ≤ departure_time; các hoạt động theo thứ tự thời gian; không qua nửa đêm.<br>•Hai hoạt động không chồng lấn (chạm biên thì không tính là chồng).<br>•Một địa điểm chỉ được xếp một lần trong cả chuyến. | invalid_time_order<br>activity_overlap<br>duplicate_place<br>cross_midnight |
| 5 | opening_hours | Toàn bộ khoảng thăm nằm trong giờ mở cửa của ngày đó (cách tính ở 8.5). | place_closed<br>outside_opening_hours<br>cảnh báo: opening_hours_unknown (info) |
| 6 | visit_duration |  | departure_time − start_time không nhỏ hơn visit_duration_typical. Ở lại lâu hơn thì hợp lệ.<br>visit_duration_insufficient |
| 7 | day_start_window | Hoạt động đầu tiên không sớm hơn activity_window.start. | day_start_violated (hard)<br>cảnh báo: soft_day_start (soft) |
| 8 | day_end_window  | Hoạt động kết thúc không muộn hơn day_end_window | day_end_violated<br>cảnh báo: soft_window_exceeded (soft) |
| 9 | meal_window | Mỗi meal_window có required = true phải có một hoạt động ăn uống nằm trọn trong khung giờ và ở lại đủ duration_minutes. | required_meal_missing |
| 10 | activity_count | Số hoạt động mỗi ngày so với min, max và target. | activity_count_below_min, activity_count_above_max (hard khi is_hard, ngược lại soft)<br>cảnh báo: activity_count_off_target (soft) |
| 11 | rest_time | Tổng thời gian nghỉ trong ngày so với rest_minutes. | rest_time_insufficient (hard)<br>cảnh báo: rest_shortfall (soft) |
| 12 | must_visit | Địa điểm bắt buộc phải được xếp; địa điểm trong avoid_place_ids không được xuất hiện. | must_visit_missing<br>avoid_place_scheduled |
| 13 | budget |  | Chi phí cận trên trong phạm vi includes không vượt mức trần B (cách tính ở 8.5).<br>budget_exceeded<br>cảnh báo: budget_overrun_within_tolerance (soft), budget_not_enforced (info) |
| 14 | summary_consistency | Số liệu tổng hợp của Itinerary khớp với số tính lại; trạng thái và dropped_places nhất quán (cách tính ở 8.5). | summary_mismatch<br>status_inconsistent<br>dropped_places_inconsistent<br>cảnh báo: dropped_places_incomplete (soft) |

### 8.5. Cách tính các quy tắc chính

Chặng di chuyển của một ngày
start_location_id → hoạt động 1 → … → hoạt động n. Mỗi chặng tra thời gian trong travel_time_matrix và travel_distance_matrix theo cặp (điểm đi, điểm đến). Các quy tắc 3, 7, 8, 11 và 13 dùng chung danh sách chặng này.
Ngân sách (quy tắc 13)
- Mức trần B = amount × (100 + max_overrun_percent) / 100, tính bằng số nguyên hoặc Decimal. Khi flexibility = strict thì B = amount.
- C_max = Σ cận trên max của chi phí các địa điểm đã xếp. C_min tính tương tự với min và values_min.
- Chỉ cộng chi phí địa điểm tham quan và ăn uống thuộc phạm vi budget.includes, không thuộc budget.excludes.
Tính tổng chi phí cận trên C_max = Σ estimated_total_cost.max.
Tính ngân sách tối đa cho phép B = budget.amount × (1 + budget.max_overrun_percent / 100).
Nếu C_max > B, tạo vi phạm budget_exceeded.
Không tính chi phí di chuyển.
Giờ mở cửa (quy tắc 5)
- Đổi ngày của chuyến sang weekday ISO 8601 (1 = Thứ Hai, 7 = Chủ nhật) theo opening_hours.timezone của địa điểm. special_hours của đúng ngày đó ghi đè weekly_schedule.
- Cả khoảng [start_time, departure_time] phải nằm trọn trong một khoảng mở cửa (địa điểm nghỉ trưa có hai khoảng). Bắt đầu đúng giờ mở cửa hoặc rời đúng giờ đóng cửa vẫn hợp lệ. Đến sớm rồi chờ mở cửa được phép.
- Ngày is_closed = true thì place_closed; nằm ngoài giờ thì outside_opening_hours.
- Không có dữ liệu cho weekday đó (và không có special_hours), hoặc khoảng có close ≤ open (qua nửa đêm, schema 5 chưa hỗ trợ): không kết luận được, ghi cảnh báo opening_hours_unknown thay vì coi là hợp lệ hay vi phạm.
Khung giờ hoạt động và giờ kết thúc (quy tắc 7, 8)
Giờ bắt đầu ngày = start_time của hoạt động đầu tiên. Phải ≥ activity_window.start.
Giờ kết thúc ngày = departure_time của hoạt động cuối cùng. Phải ≤ activity_window.end.
Nếu is_hard = true: Vi phạm giới hạn thời gian được xem là vi phạm cứng, lịch trình không hợp lệ.
Nếu is_hard = false: Vi phạm được ghi nhận dưới dạng cảnh báo soft, kèm số phút lệch để tính thành phần (2) của P_soft.
Validator kiểm tra thời gian di chuyển giữa các hoạt động liên tiếp bằng travel_time_matrix, bảo đảm hoạt động tiếp theo chỉ bắt đầu khi đã di chuyển đến nơi.
Không tính thời gian di chuyển đến hoạt động đầu tiên hoặc từ hoạt động cuối cùng về điểm kết thúc khi các điểm này không được cung cấp.
Số hoạt động và thời gian nghỉ (quy tắc 10, 11)
- Số hoạt động = số phần tử activities trong ngày (địa điểm ăn uống cũng là hoạt động, khớp với cách tính S_places ở 7.3). min, max cứng khi is_hard = true; target luôn mềm nên chỉ tạo cảnh báo.
- Thời gian nghỉ của ngày = Σ [start_time hoạt động sau − departure_time hoạt động trước − thời gian chặng giữa hai hoạt động], đúng định nghĩa thành phần 3 của P_soft (khoảng trống không dùng để đi hay tham quan, gồm cả thời gian chờ mở cửa). Ngày chỉ có một hoạt động thì thời gian nghỉ bằng 0.
Địa điểm bắt buộc, loại trừ, bữa ăn (quy tắc 9, 12)
- Mọi id trong must_visit_place_ids phải nằm trong activities; nằm trong dropped_places vẫn là vi phạm. Id trong avoid_place_ids không được xuất hiện.
- Điều kiện loại trừ dạng văn bản tự do (ví dụ "không muốn leo núi") đã phải được chuyển thành avoid_place_ids hoặc loại khỏi ứng viên ở các bước trước; Validator không diễn giải văn bản tự do.
- Bữa ăn: meal_window có required = true cần một hoạt động ăn uống với start_time ≥ start, departure_time ≤ end của khung giờ và thời gian ở lại ≥ duration_minutes. Khung required = false không kiểm tra (khớp 7.1: bữa ăn chỉ được tính khi có địa điểm ăn uống được xếp vào).
Số liệu tổng hợp (quy tắc 14)
- Chi phí của từng hoạt động phải khớp với estimated_total_cost trong candidate_places. Thời gian di chuyển giữa hai hoạt động liên tiếp phải khớp với travel_time_matrix. travel_distance_matrix được giữ làm dữ liệu khoảng cách nhưng không sử dụng để tính chi phí.
- day_total_cost = Tổng estimated_total_cost của các địa điểm được xếp trong ngày, chỉ cộng các khoản thuộc phạm vi ngân sách như quy tắc 13.
summary.total_cost = Tổng day_total_cost của tất cả các ngày.
summary.total_travel_minutes = Tổng thời gian di chuyển giữa các hoạt động liên tiếp trong từng ngày, tính lại bằng travel_time_matrix.
summary.total_scheduled_places = Tổng số activities trong tất cả các ngày.
Validator tự tính lại các giá trị từ PlanningInput và đối chiếu với Itinerary. Nếu không khớp, tạo vi phạm summary_mismatch, ghi rõ tên trường bị sai.

- status = feasible nhưng diagnostics.unsatisfied_constraints không rỗng: status_inconsistent.
- Một địa điểm vừa được xếp vừa nằm trong dropped_places: dropped_places_inconsistent (cứng). Ứng viên không được xếp mà cũng không có trong dropped_places: cảnh báo dropped_places_incomplete.
- objective_value và optimality_proven không được kiểm tra vì không phải ràng buộc.

### 8.6. Phân loại vi phạm và suggested_action

suggested_action được chọn bằng cách xét lần lượt từ trên xuống, dừng ở dòng đầu tiên khớp:

| # | Điều kiện | suggested_action | Lý do |
| --- | --- | --- | --- |
| 1 | Có lỗi dữ liệu hoặc hệ thống: planning_input_inconsistent, unknown_price_scheduled, zero_cost_unverified, invalid_cost_range, solver_error, hoặc một quy tắc bị lỗi khi chạy (validator_internal_error). | fail | Chạy lại Engine không sửa được lỗi dữ liệu đầu vào hay lỗi hệ thống. |
| 2 | status là infeasible hoặc partial. | ask_user nếu relaxation_suggestions không rỗng<br>fail nếu rỗng | Cần người dùng chọn nới ràng buộc. Không có phương án nới thì báo nguyên nhân từ diagnostics.unsatisfied_constraints, không âm thầm bỏ qua. |
| 3 | status = feasible nhưng có vi phạm cứng khác (kể cả itinerary_input_mismatch, unknown_place_id). | replan | Engine đã mô hình hóa mọi ràng buộc cứng, nên vi phạm nghĩa là nghiệm sai; có thể khác đi khi chạy lại với seed khác. |
| 4 | Không có vi phạm cứng. | accept | Cảnh báo soft và info không chặn việc trả lịch trình, nhưng được chuyển cho bước giải thích. |

Orchestrator kết hợp suggested_action = replan với giới hạn retry ở mục 9.3.

### 8.7. Kiểm thử

Dùng Itinerary mẫu ở 7.4 làm nghiệm hợp lệ chuẩn (kỳ vọng is_valid = true, accept). Mỗi quy tắc có ít nhất một test sửa đúng một thông tin để phá đúng quy tắc đó và kỳ vọng đúng vi phạm đó, không phát sinh vi phạm khác; kèm một test biên (rời p001 đúng 17:00, tổng chi phí đúng bằng B, về đúng 12:00). Thêm một test bảo đảm bỏ bất kỳ quy tắc nào khỏi danh sách chạy thì is_valid không bao giờ là true.

## 9. Orchestrator và WorkflowState

Loại: [CODE] (máy trạng thái). Orchestrator không dùng LLM để quyết định luồng. LLM chỉ xuất hiện ở ba chỗ: Request Parser (trích xuất giá trị từ prompt và từ câu trả lời), soạn câu hỏi hỏi lại và diễn đạt lại nội dung cho người dùng (phương án nới lỏng, lỗi, giải thích lịch trình).

### 9.1. WorkflowState

```jsonc
Toàn bộ trạng thái của một yêu cầu, gồm cả trạng thái hỏi lại, được quản lý ở WorkflowState (hoặc một đối tượng trạng thái tương đương), không nằm rải rác trong từng agent.
{
  "request_id": "req_001",
  "schema_version": "1.0",
  "status": "planning",
  "current_step": "planning_engine",
  "completed_steps": [
    "request_parser", "destination_agent", "constraint_planner", "place_agent",
    "budget_module", "planning_input_builder"
  ],
  "artifacts": {
    "trip_request_id": "req_001",
    "destination_result_id": "dest_001",
    "time_constraints_id": "time_001",
    "candidates_id": "candidates_001",
    "costed_candidates_id": "costs_001",
    "planning_input_id": "plan_in_001",
    "itinerary_id": "iti_001",
    "validation_result_id": "val_001"
  },
  "clarification_round": 1,
  "max_clarification_rounds": 3,
  "pending_fields": [],
  "pending_questions": [],
  "answers_history": [
    {
      "round": 1,
      "asked_fields": ["trip.start_date", "trip.end_date", "travelers.adults"],
      "question": "Bạn dự định đi vào ngày nào, trong bao lâu và có bao nhiêu người?",
      "answer_raw": "Đi 14/11, 3 ngày, 2 người",
      "resolved_fields": ["trip.start_date", "trip.end_date", "travelers.adults"],
      "declared_unknown_fields": []
    }
  ],
  "attempts": [
    {
      "attempt": 1,
      "step": "planning_engine",
      "random_seed": 42,
      "result": "hard_violation",
      "violations": ["budget_exceeded"],
      "itinerary_id": "iti_001",
      "validation_result_id": "val_001"
    }
  ],
  "retry_count": 1,
  "errors": []
}
```

| Trường | Ý nghĩa |
| --- | --- |
| request_id, schema_version | Mã yêu cầu và phiên bản schema. |
| status | Một trong các giá trị ở bảng dưới. |
| current_step, completed_steps | Bước đang chạy và các bước đã xong, dùng mã bước ở bảng dưới. |
| artifacts | ID kết quả đã lưu của từng bước (bản mới nhất). Kết quả đã lưu không bị sửa; thay đổi tạo ID mới để giữ lịch sử. Nếu dùng Python đơn giản có thể lưu thẳng object. |
| clarification_round, max_clarification_rounds, pending_fields, pending_questions, answers_history | Trạng thái hỏi lại thông tin thiếu, mô tả ở 9.2. |
| attempts, retry_count | Lịch sử các lần chạy Planning Engine và số lần chạy lại, mô tả ở 9.5. |
| errors | Lỗi kỹ thuật đã xảy ra (9.5). |

| status | Ý nghĩa |
| --- | --- |
| parsing | Đang chạy Request Parser (cho prompt đầu hoặc cho câu trả lời của người dùng). |
| clarifying | Đã gửi pending_questions, chờ người dùng trả lời. |
| planning | Đang chạy các bước từ Agent A đến Planning Engine; current_step cho biết bước nào. |
| validating | Đang chạy Validator. |
| awaiting_relaxation | Chờ người dùng chọn phương án nới lỏng (suggested_action = ask_user). |
| completed | Đã trả lịch trình hợp lệ. |
| failed | Dừng vì lỗi không phục hồi được; errors cho biết lý do. |

| Mã bước (current_step) | Thành phần | Mục | Loại |
| --- | --- | --- | --- |
| request_parser | Request Parser | 2 | [HYBRID] |
| destination_agent | Agent A | 4 | [HYBRID] |
| constraint_planner | Constraint Planner | 3 | [CODE] |
| place_agent | Agent B | 5 | [HYBRID] |
| budget_module | Budget Module C | 6 | [HYBRID] |
| planning_input_builder | Planning Input Builder | 7.1 | [CODE] |
| planning_engine | Planning Engine | 7.2 đến 7.4 | [CODE] |
| validator | Validator | 8 | [CODE] |
| explainer | Giải thích lịch trình cho người dùng | 9.3 | [LLM], CODE đối chiếu số liệu |

[BỔ SUNG] schema_version, pending_questions, attempts (đã có), cùng clarification_round, max_clarification_rounds, pending_fields, answers_history, danh sách status, mã bước, random_seed trong attempts, cấu trúc errors.

### 9.2. Hỏi lại thông tin thiếu (clarification)

Các trạng thái hỏi lại nên được quản lý ở WorkflowState hoặc một đối tượng trạng thái tương đương. Ví dụ:

```jsonc
{
  "request_id": "req_001",
  "status": "clarifying",
  "clarification_round": 1,
  "max_clarification_rounds": 3,
  "pending_fields": ["trip.start_date", "trip.end_date", "travelers.adults"],
  "pending_questions": [
    {
      "question": "Bạn dự định đi vào ngày nào, trong bao lâu và có bao nhiêu người?",
      "fields": ["trip.start_date", "trip.end_date", "travelers.adults"]
    }
  ],
  "answers_history": []
}
```

Trong đó:
- pending_fields do CODE xác định.
- pending_questions do LLM tạo ra dựa trên những trường còn thiếu.
- clarification_round do Orchestrator quản lý.
- answers_history lưu các câu trả lời đã nhận để tránh hỏi trùng.
Mỗi lần người dùng trả lời, CODE cập nhật TripRequest, xác định lại các trường thiếu và quyết định có cần hỏi tiếp hay không.

| Trường | Do ai | Chi tiết |
| --- | --- | --- |
| pending_fields | CODE | Đường dẫn các trường còn thiếu, cùng cú pháp với meta.field_sources (ví dụ trip.start_date), lấy từ danh sách trường bắt buộc ở mục 2. Một trường được tính là thiếu khi giá trị là null và source chưa phải user (người dùng đã trả lời "chưa biết" thì null kèm source = user, không hỏi lại). |
| pending_questions | LLM soạn, CODE kiểm tra | Mỗi phần tử có question và fields (các trường mà câu hỏi nhắm tới). CODE kiểm tra fields chỉ nằm trong pending_fields và mọi trường thiếu đều được ít nhất một câu bao phủ. Một câu có thể gộp nhiều trường, như ví dụ trên. |
| clarification_round | Orchestrator | Số lượt hỏi đã gửi cho yêu cầu này, bắt đầu từ 0 và tăng 1 mỗi lần gửi câu hỏi. Giá trị 1 trong ví dụ nghĩa là lượt hỏi đầu tiên đang chờ trả lời. |
| max_clarification_rounds | Cấu hình | Bằng 3, đúng quy tắc ở mục 2: tối đa 3 lần hỏi cho một yêu cầu lập lịch trình. |
| answers_history | CODE | Mỗi lượt hỏi một bản ghi: round, asked_fields, question, answer_raw, resolved_fields (trường đã có giá trị), declared_unknown_fields (trường người dùng nói chưa biết). Được đưa vào prompt soạn câu hỏi để LLM không lặp lại câu cũ. |

Vòng lặp hỏi lại
- CODE tính pending_fields sau mỗi lần Request Parser tạo hoặc cập nhật TripRequest. Rỗng thì đi tiếp sang Agent A.
- Nếu Agent A trả missing_fields (ví dụ request_type = INSUFFICIENT), CODE gộp vào pending_fields và dùng chung bộ đếm clarification_round; ba lượt hỏi là giới hạn cho cả yêu cầu, không tính riêng theo từng agent.
- Còn pending_fields và clarification_round < max_clarification_rounds: Orchestrator tăng clarification_round, gọi LLM soạn pending_questions chỉ cho các trường còn thiếu rồi đặt status = clarifying và chờ. Orchestrator chỉ gửi người dùng các câu trong pending_questions.
- Người dùng trả lời: Request Parser (LLM) trích xuất giá trị từ câu trả lời; CODE kiểm tra bằng Pydantic, ghi vào TripRequest với source = user, thêm bản ghi vào answers_history, xóa pending_questions rồi tính lại pending_fields. Giá trị dạng "trong bao lâu" được CODE đổi thành end_date hoặc duration_days.
- Hết max_clarification_rounds mà vẫn thiếu: CODE áp giá trị mặc định cho các trường còn thiếu, ghi source = default, rồi đi tiếp (đúng quy tắc "hết 3 lần thì xử lý giá trị mặc định" ở mục 2). Trường không có giá trị mặc định hợp lệ thì status = failed kèm thông báo thiếu trường nào.
- LLM soạn câu hỏi sai (không qua bước kiểm tra, thử lại hết giới hạn ở mục 10): dùng câu hỏi mẫu cố định theo từng trường thay vì dừng, vì nội dung câu hỏi không ảnh hưởng tính đúng của dữ liệu.
[BỔ SUNG] Toàn bộ mục 9.2. Phần fields trong pending_questions là bổ sung để CODE biết câu hỏi nào nhắm tới trường nào.

### 9.3. Quy tắc điều phối

| Điều kiện | Hành động | status sau đó |
| --- | --- | --- |
| TripRequest hợp lệ, còn pending_fields, clarification_round < max_clarification_rounds | Soạn pending_questions, hỏi người dùng (9.2) | clarifying |
| Còn pending_fields, đã hết số lượt hỏi | Áp giá trị mặc định (9.2); trường không có mặc định thì dừng | planning hoặc failed |
| Hết pending_fields | Chạy Agent A (EXPLICIT thì CODE xác minh điểm đến) | planning |
| Đã có điểm đến | Chạy Constraint Planner rồi Agent B | planning |
| Đã có danh sách địa điểm | Chạy Budget Module C để mọi ứng viên có chi phí (kể cả khi budget.amount = null, lúc đó Engine không áp ràng buộc ngân sách) | planning |
| Đủ dữ liệu | Planning Input Builder kiểm tra nhất quán rồi gọi Planning Engine; Builder báo không nhất quán thì dừng | planning hoặc failed |
| Có Itinerary | Chạy Validator | validating |
| suggested_action = accept | Chạy bước giải thích (LLM viết từ Itinerary đã validate; CODE đối chiếu địa điểm, giờ, số tiền trong văn bản với Itinerary, lệch thì sinh lại có giới hạn rồi dùng summary_message), trả lịch trình | completed |
| suggested_action = replan và retry_count < solver_config.max_retries | Tăng retry_count, chạy lại Engine với random_seed khác, ghi attempts | planning |
| suggested_action = replan và đã hết số lần retry | Dừng, ghi errors. Engine đã mô hình hóa mọi ràng buộc cứng nên vi phạm lặp lại là lỗi hệ thống, cần ghi log để điều tra | failed |
| suggested_action = ask_user | Trình bày relaxation_suggestions (LLM chỉ diễn đạt lại, không đổi nội dung). Người dùng chọn thì CODE cập nhật TripRequest với source = user rồi chạy lại theo 9.4; Engine không tự nới ràng buộc. Lượt này không tính vào clarification_round và đặt lại retry_count về 0 | awaiting_relaxation |
| suggested_action = fail | Báo nguyên nhân từ violations hoặc diagnostics.unsatisfied_constraints (LLM diễn đạt), ghi errors | failed |

Các hàng trên giữ nguyên các quy tắc điều phối ban đầu (thiếu thông tin thì hỏi, có điểm đến thì chạy B, có dữ liệu thì chạy C và Engine, vi phạm cứng thì tối ưu lại trong giới hạn max_retries, không có nghiệm thì báo nguyên nhân kèm lựa chọn nới lỏng, hợp lệ thì trả lịch trình) và bổ sung điều kiện chuyển trạng thái cụ thể.

### 9.4. Tái sử dụng kết quả

Khi người dùng đổi yêu cầu, Orchestrator chạy lại từ bước đầu tiên có trường đó trong đầu vào và mọi bước phía sau; Planning Input Builder, Planning Engine và Validator luôn chạy lại.

| Người dùng đổi | Chạy lại từ | Giữ lại được |
| --- | --- | --- |
| destination.* | Agent A (điểm đến mới, các địa điểm cũ không còn hợp lệ nên phải chạy lại B) | Không giữ kết quả bước nào |
| travelers.*, preferences.*, must_do, additional_constraints | Constraint Planner, rồi Agent B | Kết quả Agent A |
| trip.*, daily_preferences | Constraint Planner; Agent B chỉ chạy lại khi total_days hoặc khung giờ mở, đóng cửa (đầu vào của B) thay đổi | Kết quả Agent A; kết quả B khi B không chạy lại |
| budget.* | Budget Module C | Kết quả Agent A và Agent B |

### 9.5. Retry và lỗi

- attempts: mỗi phần tử là một lần chạy Engine kèm Validator, gồm attempt, step, random_seed, result (accepted, hard_violation, infeasible, error), mã violations và ID kết quả đã lưu.
- retry_count: số lần Engine đã được chạy lại sau replan, tăng ngay khi bắt đầu chạy lại. Giới hạn lấy từ solver_config.max_retries của PlanningInput (một nguồn duy nhất), nên với giá trị 3 có tối đa 4 lần chạy.
- Mỗi lần chạy lại phải khác lần trước. solver_config.random_seed cố định thì chạy lại cho đúng nghiệm cũ, nên lần chạy thứ n dùng random_seed = seed gốc + retry_count. Vi phạm của lần trước được ghi trong attempts để điều tra.
- errors: mỗi phần tử có step, code, message, retryable. Các code chính: llm_output_invalid (sai Pydantic sau khi hết số lần thử), external_api_error (Places API, bản đồ), planning_input_inconsistent, solver_error, validator_internal_error.
[BỔ SUNG] Quy tắc đổi random_seed mỗi lần chạy lại và cấu trúc errors.

## 10. Quy ước chung cho mọi schema

Tất cả mục dưới đây đều thuộc [BỔ SUNG] (dòng 11 trong bảng 0.2).
Số, tiền và thời gian
- Tiền tệ lưu bằng số nguyên theo đơn vị nhỏ nhất của tiền tệ (VND không có phần thập phân). Tính toán bằng số nguyên hoặc Decimal, không dùng số thực. Chi phí dạng khoảng luôn có min ≤ max.
- Thời gian di chuyển và thời lượng lưu bằng số phút nguyên; nếu nguồn trả về giây thì làm tròn lên để không lạc quan hơn thực tế.
- Ngày dùng YYYY-MM-DD. Thời điểm tuyệt đối (ví dụ arrival.datetime) dùng ISO 8601 có múi giờ. Giờ trong ngày dùng HH:MM theo timezone của chuyến đi (giờ mở cửa theo timezone của địa điểm). Weekday theo ISO 8601: 1 = Thứ Hai, 7 = Chủ nhật.
- So sánh bao gồm biên: đến đúng giờ đóng cửa, về đúng giờ phải về, tổng chi phí đúng bằng mức trần đều hợp lệ; hai khoảng thời gian chạm nhau không tính là chồng lấn.
Giá trị thiếu, nguồn và độ tin cậy
- null nghĩa là chưa biết. Không thay null bằng 0 hoặc giá trị mặc định một cách âm thầm: chi phí bằng 0 chỉ khi price_status = VERIFIED_FREE; giá trị mặc định do hệ thống đặt phải ghi source = default.
- Mọi giá trị ước tính (giá, thời lượng tham quan) có source. Giá trị do LLM suy luận hoặc mô hình ước tính còn có độ tin cậy (field_confidences, price_confidence_score). Giá trị người dùng nói rõ, mặc định hệ thống và giá trị CODE tính ra theo đúng bảng quy tắc meta ở mục 2.
Schema và kiểm tra
- Mọi schema được lưu hoặc truyền giữa các bước có schema_version dạng "chính.phụ" (ví dụ 1.0). Khác phiên bản chính thì từ chối xử lý.
- Giữ đúng chữ hoa, chữ thường của các giá trị liệt kê như đã định nghĩa (ví dụ price_status và request_type viết hoa, selection_mode, status, flexibility, source viết thường). Pydantic dùng kiểu liệt kê nghiêm ngặt, không tự chuẩn hóa.
- Mỗi bước kiểm tra schema bằng Pydantic trước khi chuyển sang bước sau, với extra = "forbid" cho dữ liệu nội bộ để phát hiện trường sai tên. Đầu ra LLM không hợp lệ thì thử lại tối đa N lần (mặc định N = 2), kèm thông báo lỗi Pydantic trong prompt, rồi ghi errors (llm_output_invalid) và áp dụng cách xử lý của từng bước (ví dụ câu hỏi mẫu ở 9.2).
ID và tái lập kết quả
- place_id ổn định giữa Agent B, Budget Module C, Planning Engine và Validator. ID kết quả lưu trong artifacts không bị sửa nội dung; thay đổi tạo ID mới.
- Kết quả của phần CODE phải tái lập được: solver_config.random_seed và time_limit_seconds được lưu cùng mỗi lần chạy trong attempts.

## 11. Checklist triển khai

### Thông tin chuyến đi

- [ ] Ngày đi và ngày về
- [ ] Giờ đến và giờ rời điểm đến
- [ ] Múi giờ
- [ ] Số người lớn và trẻ em
- [ ] Điểm xuất phát và điểm kết thúc
- [ ] Khách sạn hoặc nơi lưu trú nếu có

### Hỏi lại thông tin thiếu

- [ ] pending_fields do CODE tính từ danh sách trường bắt buộc, dùng đúng đường dẫn JSON
- [ ] pending_questions do LLM soạn, CODE kiểm tra bao phủ đủ trường thiếu
- [ ] Tối đa 3 lượt hỏi cho một yêu cầu (gồm cả câu hỏi phát sinh từ Agent A)
- [ ] Người dùng trả lời "chưa biết" thì để null, source = user, không hỏi lại
- [ ] Hết lượt hỏi thì áp giá trị mặc định (source = default); trường không có mặc định thì báo rõ thiếu gì
- [ ] answers_history được ghi và đưa vào prompt soạn câu hỏi

### Thời gian

- [ ] Khung giờ riêng từng ngày
- [ ] Giờ phải về và điểm cần về
- [ ] Thời lượng tham quan từng địa điểm
- [ ] Giờ mở cửa và ngày đóng cửa đặc biệt
- [ ] Thời gian di chuyển giữa các địa điểm
- [ ] Khung giờ ăn và thời gian nghỉ

### Ngân sách

- [ ] Tổng ngân sách và đơn vị tiền
- [ ] Ngân sách tính cho cá nhân hay cả nhóm
- [ ] Các khoản được bao gồm và loại trừ
- [ ] Giá vé, giá hoạt động, chi phí ăn uống
- [ ] Chi phí di chuyển và lưu trú nếu thuộc phạm vi
- [ ] Nguồn giá, độ tin cậy và khoản chưa biết

### Tối ưu hóa

- [ ] Điểm phù hợp của địa điểm
- [ ] Địa điểm bắt buộc và địa điểm cần tránh
- [ ] Ràng buộc cứng và sở thích mềm
- [ ] Giới hạn số địa điểm ứng viên
- [ ] Hàm mục tiêu và trọng số (đã chuẩn hóa)
- [ ] Trạng thái nghiệm và lý do thất bại

### Kiểm tra và phục hồi

- [ ] Schema validation ở mỗi bước
- [ ] Phát hiện dữ liệu thiếu hoặc mâu thuẫn
- [ ] Không coi chi phí chưa biết là 0
- [ ] Không âm thầm bỏ qua ràng buộc cứng
- [ ] Có phương án khi không tìm được lịch trình khả thi
- [ ] Validator tính lại độc lập từ PlanningInput, không tin số liệu do Engine tự báo
- [ ] checked_rules đủ 14 quy tắc; thiếu quy tắc thì is_valid không là true
- [ ] suggested_action chọn theo bảng ở 8.6
- [ ] Giới hạn số lần tối ưu lại theo solver_config.max_retries, mỗi lần chạy lại đổi random_seed
- [ ] Bước giải thích đối chiếu địa điểm, giờ, số tiền với Itinerary

### Tái sử dụng kết quả

- [ ] Đổi ngân sách chỉ chạy lại C, Builder, Engine, Validator; đổi điểm đến chạy lại từ Agent A (xem 9.4)

## 12. Tóm tắt ranh giới LLM và CODE

| Giai đoạn | LLM/Agent làm | CODE làm |
| --- | --- | --- |
| Hiểu yêu cầu | Trích xuất từ prompt và từ câu trả lời của người dùng | Pydantic validation, ghi giá trị vào TripRequest, tính trường thiếu |
| Hỏi lại thông tin thiếu | Soạn pending_questions từ các trường thiếu | Xác định pending_fields, đếm lượt hỏi, kiểm tra câu hỏi bao phủ, ghi answers_history, áp giá trị mặc định |
| Chọn điểm đến | Gợi ý và giải thích | Kiểm tra điểm đến hợp lệ |
| Ràng buộc thời gian | Không | Toàn bộ |
| Tìm địa điểm | Chấm mức phù hợp, viết lý do, ước tính thời lượng khi thiếu | Gọi API, lọc, gán ID, DBSCAN |
| Chi phí | Ước tính giá khi thiếu | Chuẩn hóa, nhân số người, tổng hợp, tính  từ đơn giá |
| Dựng PlanningInput | Không | Gom dữ liệu, kiểm tra nhất quán, dựng ma trận thời gian và chi phí |
| Tối ưu lịch trình | Không | TOPTW, OR-Tools, ALNS, sinh relaxation_suggestions |
| Kiểm tra | Không | Toàn bộ (14 quy tắc ở 8.4) |
| Điều phối | Diễn đạt lại phương án nới lỏng và lỗi cho người dùng | Máy trạng thái, retry, lưu trạng thái, chọn bước tiếp theo theo suggested_action |
| Giải thích lịch trình | Viết văn bản từ Itinerary đã validate, không đổi dữ liệu | Đối chiếu địa điểm, giờ, số tiền trong văn bản với Itinerary |
