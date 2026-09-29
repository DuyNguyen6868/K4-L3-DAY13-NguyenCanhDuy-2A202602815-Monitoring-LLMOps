# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Cảnh Duy
- **MSSV:** 2A202602815
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/DuyNguyen6868/K4-L3-DAY13-NguyenCanhDuy-2A202602815-Monitoring-LLMOps.git
- **Commit SHA cuối:**
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4)
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602815`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.txt` |
| Log validator | `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png`, `evidence/13-incident-log.txt` (bản đầy đủ, không bị cắt cột) |
| Incident trace | `evidence/14-incident-trace.png` |

Ảnh 06, 07, 09, 10 được che email tài khoản ở góc trái dưới; ngoài vùng đó không chỉnh sửa gì.

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | 245 bản ghi, 0 thiếu field/enrichment, 114 correlation ID, 0 PII leak. |
| `validate_dashboard.py` | 6/6 | 6/6 | Contract giữ nguyên; `scripts/dashboard.py` dựng đủ 6 panel từ log (ảnh 11, 12). |
| `pytest` | 22 passed | 46 passed | Thêm test cho correlation ID, PII trong log, child observations, dashboard và alert config. |
| Số traces hợp lệ | Chỉ có root `lab-agent-run`, chưa có child | 44 trace đủ `retrieval` + `llm-generation` trong ảnh 06 (20:10), sau đó thêm 55 request có trace cùng cấu trúc | Mỗi trace có metadata `correlation_id` khớp log; 15 trace của CP3 đã kiểm tra lại qua Langfuse API. |
| Số PII leak | 0 | 0 | Log chỉ ghi preview đã scrub; trace không nhận input/output thô. |
| Latency P95 / TTFT P95 | 1556 ms / 50 ms (CP0, 10 request) | 173 ms / 50 ms khi bình thường (22:13); 2655 ms / 50 ms trong incident | `latency_ms` phía server lấy từ `data/logs.jsonl`. |
| Retrieval success rate | 100% (10/10) | 100% (112/112) | Không có `request_failed`; incident `rag_slow` chỉ làm chậm, không gây lỗi. |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` (`app/middleware.py`) nhận header `x-request-id` nếu đúng dạng `req-<8 hex>`, nếu không thì tạo mới `req-` + 8 ký tự hex từ `uuid4`. ID được bind vào structlog contextvars nên mọi log line của request đều có `correlation_id`, được lưu ở `request.state` để `/chat` truyền vào `LabAgent.run` (ghi vào metadata trace), và trả lại cho client qua header `x-request-id` cùng `x-response-time-ms`. Đầu mỗi request gọi `clear_contextvars()` để context của request trước không lọt sang.
- **Các metadata được ghi vào structured log:** `ts` (ISO, UTC), `level`, `event`, `service`, `correlation_id`, `user_id_hash`, `session_id`, `feature`, `model`, `env`. Riêng `response_sent` có thêm `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success` và `payload.answer_preview`; `request_failed` có `error_type` và `tool_success=false`.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` trong chuỗi structlog (`app/logging_config.py`) chạy sau `format_exc_info` và trước `JSONRenderer`, scrub đệ quy mọi chuỗi trong dict/list bằng `scrub_text` (`app/pii.py`): email, số điện thoại VN, CCCD, thẻ tín dụng, hộ chiếu được thay bằng `[REDACTED_<LOẠI>]`, và pattern email chạy trước để pattern số điện thoại không cắt mất email. Message và answer chỉ được ghi dưới dạng preview đã scrub, cắt 80 ký tự; user ID chỉ ghi SHA-256 rút gọn 12 ký tự; header `x-request-id` sai định dạng bị bỏ qua để không đưa text tùy ý vào log.
- **Cách kiểm chứng kết quả:** `validate_logs.py` đạt 100/100 với 0 PII leak trên 245 bản ghi (`evidence/02-log-validator.txt`); test `test_pii.py`, `test_logging_pii.py`, `test_correlation_id.py` nằm trong 46 test pass; ảnh 04 và 05 cho thấy log JSON có đủ field và email/số điện thoại đã thành `[REDACTED_...]`.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** trace nằm trong project `day13-k4-l3a-2A202602815` (ảnh 06, 14 thấy tên project), và `correlation_id` trong metadata trace trùng với log do API trên máy tôi ghi, ví dụ trace `a08c6f7dcd7e9d1fc4713c931e85a727` ↔ log `req-5d28767c`.
- **Cấu trúc root/retrieval/generation observations:** root `lab-agent-run` (agent, trace name `day13-agent-request`, metadata `correlation_id`, `feature`, `model`, `prompt_*`, user ID đã hash, session ID) có hai con: `retrieval` (retriever; input chỉ có `query_preview` đã scrub, output là `doc_count`) và `llm-generation` (generation; model, usage input/output, cost input/output/total, `completion_start_time` = lúc bắt đầu + TTFT). Không gửi prompt hay answer thô (ảnh 07, 08).
- **Cách nối trace với log:** `correlation_id` do middleware tạo được gắn vào metadata của mọi observation qua `propagate_attributes`. Trên Langfuse lọc `metadata.correlation_id` bằng ID lấy từ log (ảnh 14 lọc `req-5d28767c`).
- **Prompt name:** `day13-chat` (text prompt, giữ 3 biến `feature`, `docs`, `message`).
- **Version/label baseline:** version 1, label `baseline` (đồng thời là `production` sau rollback).
- **Version/label candidate:** version 2, label `candidate` (được gắn tạm `production` khi promote).
- **Trace ID theo từng lần chạy:**

| Lần chạy | Prompt name | Version | Label | Prompt source | Trace ID | Correlation ID |
|---|---|---:|---|---|---|---|
| Baseline | `day13-chat` | 1 | `baseline` | `langfuse` | `1eac84ee7d5d888c49526ce8a34629de` | `req-1fd84ed5` |
| Candidate | `day13-chat` | 2 | `candidate` | `langfuse` | `033b873dda5c01ad5328fa555264b59a` | `req-05cfa10c` |
| Promote production | `day13-chat` | 2 | `production` | `langfuse` | `055f7542a014589d34b2654c2c5ffe7f` | `req-4492baba` |
| Rollback production | `day13-chat` | 1 | `production` | `langfuse` | `1880d7ebfe9d78a53825b095301de723` | `req-77b45daf` |

- **Trace baseline v1:** model `claude-sonnet-4-5`, 119 tokens, cost `$0.001449`; metadata xác nhận `prompt_source=langfuse`.
- **Trace candidate v2:** model `claude-sonnet-4-5`, 162 tokens, cost `$0.002094`; metadata xác nhận `prompt_source=langfuse`.
- **Trace production v2 sau promote:** model `claude-sonnet-4-5`, 193 tokens, cost `$0.002559`; metadata xác nhận `prompt_source=langfuse`.
- **Trace production v1 sau rollback:** model `claude-sonnet-4-5`, 119 tokens, cost `$0.001449`; metadata xác nhận `prompt_source=langfuse`.
- **Cách promote và rollback `production`:** app lấy prompt theo `LANGFUSE_PROMPT_NAME=day13-chat` và `LANGFUSE_PROMPT_LABEL` trong `.env`; cả bốn lần chạy dùng cùng input "How should alerts be designed?".
  - Candidate: đặt `LANGFUSE_PROMPT_LABEL=candidate`, restart API (19:27) rồi gửi request, trace dùng v2 (`req-05cfa10c`).
  - Promote: trên Langfuse UI (Prompts → `day13-chat`) gán label `production` cho version 2, đưa `.env` về `LANGFUSE_PROMPT_LABEL=production`, restart API (19:37) và gửi lại request, trace `production` dùng v2 (`req-4492baba`).
  - Rollback: gán lại `production` cho version 1 trên UI, restart API (19:48) và gửi request, trace `production` dùng lại v1 (`req-77b45daf`).
  - Phải restart sau mỗi lần đổi vì `--reload` không theo dõi `.env` và SDK cache prompt 60 giây. Rollback chỉ là chuyển label, không sửa code hay deploy lại; kiểm chứng bằng `prompt_version` trong metadata trace đổi 2 → 1 trong khi `prompt_label` vẫn là `production`.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `scripts/dashboard.py` đọc `data/logs.jsonl` theo contract `config/dashboard.yaml` (không sửa contract) và tạo `data/dashboard.html` bằng Chart.js, cửa sổ 60 phút, trang tự refresh 30 giây, chế độ `--watch` tạo lại file mỗi 30 giây. Sáu panel: latency P50/P95/P99 + TTFT P95 (ms, threshold P95 ≤ 3000), request traffic theo phút (≥ 1/phút), error rate + retrieval success (%, error ≤ 2%), cost cộng dồn (USD, ≤ 2.5), tokens input/output (≤ 50,000) và quality proxy (≥ 0.8). Ảnh 11 là lúc bình thường, ảnh 12 là lúc có incident.
- **SLO và lý do chọn:** SLI là tỉ lệ request có `response_sent` với `latency_ms ≤ 2000` trên tổng `request_received`, target 99.5% trong 28 ngày (`config/slo.yaml`). Mức 2000 ms nằm giữa latency bình thường (P95 152–173 ms) và mức của `rag_slow` (khoảng 2655 ms), nên incident vi phạm SLO sớm hơn threshold 3000 ms của dashboard contract. Guardrails đi kèm: error rate ≤ 2%, cost ≤ $2.5/ngày, quality ≥ 0.75, retrieval success ≥ 90%.
- **Cách tính error budget:** budget = 100% − 99.5% = 0.5% số request được phép "xấu" (chậm hơn 2000 ms hoặc lỗi). Log của ngày lab có 112 request, 6 request xấu (5 request của incident và 1 request đầu tiên sau khi khởi động API lúc 16:58, 2247 ms), tức SLI 94.64% và đã tiêu 5.36%, khoảng 10.7 lần budget. Với lưu lượng nhỏ như lab, một incident 26 giây đã đủ đốt hết budget, nên lúc đó phải ưu tiên sửa độ tin cậy thay vì đổi thêm prompt hay feature.
- **Ba alert và runbook tương ứng** (`config/alert_rules.yaml`, runbook trong `docs/alerts.md`, gửi Slack `#llmops-alerts`, owner Nguyen Canh Duy):
  - `high_latency_p95` (P2, symptom-based): P95 của `response_sent.latency_ms` trong 5 phút > 2000 ms, kéo dài 5 phút. Runbook `docs/alerts.md#alert-1`.
  - `high_error_rate_or_retrieval_failure` (P1): error rate > 2% hoặc retrieval success < 90%. Runbook `docs/alerts.md#alert-2`.
  - `cost_burn_high` (P3): tổng `cost_usd` trong 1 giờ > `daily_cost_usd_max / 24` (khoảng $0.104). Runbook `docs/alerts.md#alert-3`.
  - Mỗi runbook có phần kiểm tra (panel nào, lọc log thế nào, mở trace nào) và mitigation.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4).
- **Khoảng thời gian điều tra:** 22:05–22:15 ngày 29/09/2026 (UTC+7). Incident bật lúc 22:11:24 (log `incident_enabled`, `req-5e93f2dc`) và tắt lúc 22:11:50 (log `incident_disabled`, `req-635b1bbf`), tức 15:11:24–15:11:50 UTC. Năm request của challenge được nhận từ 22:11:33.8 đến 22:11:44.4 và trả lời từ 22:11:36.4 đến 22:11:47.1.
- **Triệu chứng từ metrics:** dashboard (ảnh 12, cửa sổ 21:58–22:58) cho thấy latency P95 2654 ms, P99 2655 ms trong khi P50 chỉ 153 ms, vượt SLO 2000 ms và điều kiện của alert `high_latency_p95`. TTFT P95 giữ 50 ms, error rate 0%, retrieval success 100%, cost và tokens bình thường. So theo từng pha:

  | Pha | Số request | P50 / P95 latency | TTFT P95 | Error rate |
  |---|---:|---|---|---|
  | Trước (22:09) | 10 | 153 / 1347 ms (1 request đầu sau khi khởi động; 9 request còn lại 151–156 ms) | 50 ms | 0% |
  | Trong incident (22:11) | 5 | 2654 / 2655 ms | 50 ms | 0% |
  | Sau khi tắt (22:13) | 10 | 152 / 173 ms | 50 ms | 0% |

  Chỉ latency tăng thêm khoảng 2.5 s mỗi request, không có lỗi và không tăng token hay cost, nên nghi phần thời gian thêm nằm ở bước trước generation.
- **Log line và correlation ID liên quan:** `response_sent` lúc `2026-09-29T15:11:41.732735Z` (22:11:41) có `correlation_id=req-5d28767c`, `feature=monitoring`, `session_id=k4-l3a-challenge-s04`, `latency_ms=2655`, `ttft_ms=50`, `tokens_out=117`, `tool_name=retrieval`, `tool_success=true` (ảnh 13, `evidence/13-incident-log.txt`). Bốn request còn lại của challenge (`req-bd70f477`, `req-3e8c43aa`, `req-d0485d29`, `req-c4758e7f`) đều mất 2654 ms.
- **Trace ID và span gây ảnh hưởng:** trace `a08c6f7dcd7e9d1fc4713c931e85a727` có metadata `correlation_id=req-5d28767c` (ảnh 14). Trong 2655 ms của `lab-agent-run`, span `retrieval` chiếm 2501 ms (94%), còn `llm-generation` chỉ 153 ms. Cả 5 trace trong incident đều có `retrieval` 2501–2510 ms; sau khi tắt incident, `retrieval` chỉ còn 0–5 ms. Span gây ảnh hưởng là `retrieval`.
- **Root cause:** bước retrieval (mock RAG) bị chậm thêm khoảng 2.5 s mỗi request vì incident `rag_slow` được bật lúc 22:11:24 (log control `incident_enabled` có `payload.name=rag_slow`); LLM không chậm (TTFT 50 ms, generation 153 ms). Tác động còn bị khuếch đại: `/chat` là hàm `async` nhưng chạy retrieval blocking, nên 5 request gửi đồng thời bị xử lý lần lượt (server nhận lúc 22:11:33.8 → 36.4 → 39.1 → 41.7 → 44.4). Theo timestamp log, request thứ năm phải chờ khoảng 10.6 s trước khi được xử lý, nên phía client chờ khoảng 13 s.
- **Fix action:** tắt incident bằng `python scripts/inject_incident.py --disable` lúc 22:11:50 (log `incident_disabled`, `req-635b1bbf`). Kiểm chứng bằng load test phục hồi lúc 22:13: 10/10 request thành công, P95 173 ms, và trong trace `retrieval` chỉ còn 0–5 ms.
- **Preventive measure:**
  - Đặt timeout khoảng 500 ms cho retrieval kèm fallback (trả lời không kèm docs hoặc dùng cache) để một dependency chậm không kéo cả request vượt SLO.
  - Chạy phần blocking của agent ngoài event loop (endpoint `def` hoặc `run_in_threadpool`) để một request chậm không bắt các request khác xếp hàng.
  - Ghi thêm `retrieval_ms` vào log và dashboard, thêm alert riêng cho P95 của retrieval bên cạnh `high_latency_p95` (P2) đã có runbook.
  - Mọi thay đổi cấu hình đều ghi log sự kiện control (như `incident_enabled`) để đối chiếu thời điểm thay đổi với lúc alert bắn.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** không gửi input/output thô lên Langfuse: dùng `@observe(capture_input=False, capture_output=False)`, span `retrieval` chỉ nhận `query_preview` đã scrub và `doc_count`, generation chỉ nhận model, usage, cost và TTFT. Trace đi ra dịch vụ bên ngoài nên phải theo cùng quy tắc PII như log. Cost được tính một lần (`_cost_breakdown`) và dùng chung cho `cost_usd` trong log và `cost_details` trong trace, nên hai nguồn luôn khớp nhau.
- **Một lỗi/blocker đã gặp:** mở `data/dashboard.html` thì trang dài ra vô hạn, không chụp được dashboard trong một màn hình. Ngoài ra, sau khi đổi label prompt trên UI, app vẫn dùng version cũ.
- **Cách tìm nguyên nhân và xử lý:** đo DOM bằng Edge headless thì thấy canvas Chart.js (`responsive`, `maintainAspectRatio: false`) dùng chung khối cha với tiêu đề panel; mỗi lần resize canvas lấy chiều cao của khối cha rồi lại làm khối cha cao thêm, thành vòng lặp. Sửa bằng cách cho mỗi canvas một container riêng `.chart-box` có kích thước do grid quyết định, và thêm test `test_each_chart_gets_a_container_of_its_own`. Với prompt, SDK cache prompt 60 giây và `--reload` không theo dõi `.env`, nên phải restart API sau mỗi lần đổi label.
- **Cách hiểu luồng Metrics → Logs → Traces:** metrics trả lời "có vấn đề gì, từ khi nào" (P95 2654 ms lúc 22:11, lỗi 0%, TTFT không đổi); logs trả lời "request nào bị ảnh hưởng" (`req-5d28767c`, `latency_ms=2655`); traces trả lời "bước nào gây ra" (`retrieval` 2501/2655 ms). `correlation_id` là khóa nối log với trace, và kết luận chỉ đáng tin khi cả ba cùng chỉ về một nguyên nhân.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** prompt version và label cho biết mỗi request dùng prompt nào, và rollback chỉ cần chuyển label `production` chứ không phải deploy lại. Token và cost theo từng request cho thấy tác động của prompt (với cùng input, v2 dùng 162–193 tokens so với 119 của v1) và giúp bắt cost spike. SLO cùng error budget biến "chậm" thành con số, để quyết định khi nào dừng thay đổi và ưu tiên sửa lỗi.
- **Điều quan trọng nhất đã học:** observability phải được thiết kế ngay từ đầu. Nếu không có `correlation_id` chung giữa log và trace, P95 chỉ cho biết hệ thống đang chậm chứ không chỉ ra được request nào và bước nào gây chậm.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
  - `/chat` là hàm `async` nhưng chạy code blocking, nên dưới tải các request bị xử lý tuần tự (thấy rõ trong CP3); phần này chưa sửa trong code.
  - Panel latency là percentile gộp cả cửa sổ 60 phút, chưa có đường P95 theo thời gian; threshold 3000 ms của contract cũng lỏng hơn SLO 2000 ms.
  - Alert mới dừng ở cấu hình và runbook, chưa có engine gửi Slack thật.
  - Ảnh 10 chỉ chụp trạng thái sau rollback (`production` ở v1); trạng thái sau promote được chứng minh bằng trace `055f7542a014589d34b2654c2c5ffe7f`.
  - `quality_score` chỉ là heuristic.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
