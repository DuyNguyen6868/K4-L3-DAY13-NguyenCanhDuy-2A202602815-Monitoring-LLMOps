# Alert và Runbook

Các ngưỡng là symptom-based. Kênh `#llmops-alerts` là tên minh họa, không cấu hình webhook thật. Chuỗi điều tra cho mọi alert là metrics → log theo `correlation_id` → trace/span.

## Alert 1

- **Tên:** `high_latency_p95`
- **Severity/duration:** P2, duy trì 5 phút.
- **SLI/SLO:** P95 latency mục tiêu ≤ 2,000 ms.
- **Điều kiện:** P95 `response_sent.latency_ms` > 2,000 ms trong 5 phút.
- **Ảnh hưởng:** người dùng gặp phản hồi chậm, có thể timeout ở phía client.
- **Kiểm tra:** xác nhận time range và P95; lọc `response_sent` theo latency/correlation ID; mở trace tương ứng và so sánh retrieval với generation.
- **Mitigation:** nếu retrieval là nguyên nhân, giảm tải/tắt tạm feature bị ảnh hưởng hoặc bật đường fallback đã được kiểm chứng; rollback thay đổi prompt/model gần nhất nếu generation chiếm thời gian.
- **Owner/kênh:** Nguyen Canh Duy, Slack `#llmops-alerts`.

## Alert 2

- **Tên:** `high_error_rate_or_retrieval_failure`
- **Severity/duration:** P1, duy trì 5 phút.
- **SLI/SLO:** error rate tối đa 2%; retrieval success tối thiểu 90%.
- **Điều kiện:** error rate > 2% hoặc retrieval success < 90%.
- **Ảnh hưởng:** request lỗi hoặc câu trả lời thiếu dữ liệu truy xuất.
- **Kiểm tra:** xem error rate và retrieval success; nhóm log `request_failed` theo `error_type` và `correlation_id`; kiểm tra trạng thái/thời lượng retriever span.
- **Mitigation:** chuyển traffic sang nguồn retrieval dự phòng hoặc fallback an toàn; tạm giảm/tắt feature bị ảnh hưởng; khôi phục dependency trước khi nhận lại traffic.
- **Owner/kênh:** Nguyen Canh Duy, Slack `#llmops-alerts`.

## Alert 3

- **Tên:** `cost_burn_high`
- **Severity/duration:** P3, duy trì 15 phút.
- **SLI/SLO:** guardrail chi phí ngày $2.50; tốc độ chi trong một giờ nên thấp hơn $2.50 / 24 ≈ $0.1042.
- **Điều kiện:** tổng `response_sent.cost_usd` trong một giờ > `daily_cost_usd_max / 24`.
- **Ảnh hưởng:** tốc độ sử dụng có thể vượt ngân sách ngày.
- **Kiểm tra:** so sánh cost với traffic; xem `tokens_in`/`tokens_out` và model; kiểm tra trace generation để phát hiện prompt dài hoặc output tăng.
- **Mitigation:** giới hạn output token/traffic theo chính sách; rollback prompt/model mới nếu gây tăng usage; giữ fallback đã kiểm tra chất lượng.
- **Owner/kênh:** Nguyen Canh Duy, Slack `#llmops-alerts`.
