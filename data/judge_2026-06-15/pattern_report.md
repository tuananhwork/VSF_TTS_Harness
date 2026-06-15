# Pattern report — 2026-06-15

| Field | Value |
| --- | --- |
| Date range | sessions_2026-06-15_runAt_20260615-173114 |
| Sessions scanned | 10 |
| Clusters found | 8 |
| Candidates emitted | 4 |
| Candidates passed critique | 3 |

## Clusters

### Cluster 1 (unclear)
- recurrence: 2, retry_rate: 0.094, correction_rate: 0.167
- representative tools: `TaskUpdate, mcp__computer-use__screenshot, mcp__workspace__bash`
- tool_sequence: `ToolSearch → mcp__cowork__request_cowork_directory → mcp__mcp-registry__search_mcp_registry → mcp__workspace__bash×4 → TaskCreate×4 → TaskUpdate → AskUserQuestion → ToolSearch → mcp__computer-use__request_access → mcp__workspace__bash → mcp__computer-use__open_application → mcp__computer-use__screenshot → mcp__computer-use__key → TaskUpdate → mcp__computer-use__type → mcp__computer-use__key → mcp__computer-use__screenshot → mcp__computer-use__double_click → mcp__computer-use__wait → mcp__workspace__bash → mcp__computer-use__screenshot → mcp__workspace__bash → TaskUpdate×2 → mcp__computer-use__open_application → mcp__computer-use__screenshot → mcp__computer-use__write_clipboard → mcp__computer-use__left_click → mcp__computer-use__key → mcp__computer-use__screenshot → mcp__computer-use__key → mcp__computer-use__screenshot → TaskUpdate×2` | `ToolSearch → mcp__cowork__request_cowork_directory → mcp__mcp-registry__search_mcp_registry → TaskCreate×4 → TaskUpdate → mcp__workspace__bash → Read×2 → mcp__workspace__bash → Read → TaskUpdate×2 → mcp__workspace__bash×8 → TaskUpdate×2 → mcp__workspace__bash → AskUserQuestion → ToolSearch → mcp__computer-use__request_access → mcp__computer-use__open_application → mcp__computer-use__screenshot → AskUserQuestion → TaskUpdate×2 → mcp__computer-use__left_click → mcp__computer-use__screenshot → mcp__computer-use__left_click → mcp__computer-use__screenshot → mcp__computer-use__left_click → mcp__computer-use__write_clipboard → mcp__computer-use__key → mcp__computer-use__screenshot → mcp__computer-use__key → mcp__computer-use__screenshot → TaskUpdate → mcp__workspace__bash → Read → Edit`
- titles: MobileAutoDesktop project testing | MobileAutoDesktop project setup
- sessions: adoring-loving-dirac, ecstatic-elegant-ramanujan

### Cluster 2 (unclear)
- recurrence: 1, retry_rate: 0.0, correction_rate: 0.0
- representative tools: `AskUserQuestion`
- tool_sequence: `AskUserQuestion`
- titles: Export reports Excel feature
- sessions: blissful-peaceful-feynman

### Cluster 3 (unclear)
- recurrence: 1, retry_rate: 0.043, correction_rate: 0.5
- representative tools: `TaskCreate, TaskUpdate, mcp__workspace__bash`
- tool_sequence: `ToolSearch → mcp__cowork__request_cowork_directory → mcp__mcp-registry__search_mcp_registry → mcp__workspace__bash×4 → AskUserQuestion → TaskCreate×4 → TaskUpdate → mcp__workspace__bash×4 → ToolSearch → Write → mcp__computer-use__request_access → mcp__computer-use__open_application → mcp__computer-use__screenshot → mcp__computer-use__left_click → mcp__computer-use__key → mcp__computer-use__type → mcp__computer-use__key → mcp__workspace__bash → mcp__computer-use__wait → mcp__workspace__bash×2 → TaskUpdate×3 → ToolSearch → mcp__Claude_in_Chrome__navigate → mcp__computer-use__open_application → mcp__computer-use__screenshot → mcp__computer-use__left_click → mcp__computer-use__write_clipboard → mcp__computer-use__key → mcp__computer-use__screenshot → mcp__computer-use__key → mcp__computer-use__screenshot → TaskUpdate×2 → mcp__workspace__bash`
- titles: MobileAutoDesktop testing and release
- sessions: busy-hopeful-knuth

### Cluster 4 (unclear)
- recurrence: 2, retry_rate: 0.0, correction_rate: 0.0
- representative tools: `Read, mcp__workspace__bash`
- tool_sequence: `Read → mcp__workspace__bash×2` | `Read → mcp__workspace__bash×2 → Read×2`
- titles: ConvMixer file summary | CV summary
- sessions: charming-awesome-maxwell, gracious-dazzling-hopper

### Cluster 5 (unclear)
- recurrence: 1, retry_rate: 0.0, correction_rate: 0.0
- representative tools: ``
- tool_sequence: ``
- titles: Dark mode web app PRD
- sessions: funny-beautiful-hypatia

### Cluster 6 (unclear)
- recurrence: 1, retry_rate: 0.0, correction_rate: 0.0
- representative tools: `Read`
- tool_sequence: `Read`
- titles: VSF confidentiality commitment summary
- sessions: gracious-keen-cori

### Cluster 7 (unclear)
- recurrence: 1, retry_rate: 0.0, correction_rate: 0.0
- representative tools: `Write, mcp__cowork__present_files`
- tool_sequence: `Write → mcp__cowork__present_files`
- titles: Water reminder app PRD
- sessions: jolly-serene-hopper

### Cluster 8 (unclear)
- recurrence: 1, retry_rate: 0.0, correction_rate: 0.0
- representative tools: `AskUserQuestion, TaskCreate, TaskUpdate`
- tool_sequence: `AskUserQuestion → ToolSearch → TaskCreate×2 → TaskUpdate → Write → mcp__workspace__bash → TaskUpdate×2 → mcp__cowork__present_files`
- titles: Mobile app UIUX testcase
- sessions: vigilant-awesome-hopper


## Top candidates (passed critique)

### 1. `test-and-report-ci-to-teams` — process_macro (process)
- Trigger (VI): Khi user muốn kiểm tra/chạy test một dự án rồi báo cáo trạng thái CI vào app Teams (tài khoản cá nhân) qua thao tác desktop.
- Trigger (EN): When the user wants to check/run a project's tests and report CI status into the Teams app (personal account) via desktop control.
- Score total: 13
- Flow (action template):
- Debate (judge verdicts):
  - **efficiency** [approve, 5/5]: Chuỗi rất dài và lặp gần như y hệt qua cả 3 session: ToolSearch → request_cowork_directory → search_mcp_registry → nhiều lượt mcp__workspace__bash chạy test → rồi loạt thao tác computer-use thủ công (open_application, write_clipboard, left_click, key, screenshot) để dán báo cáo vào Teams, kèm nhiều lần 'retry' screenshot. Đóng gói macro này cắt được hàng chục bước thủ công và việc gõ lại cùng một yêu cầu mỗi lần, nên tiết kiệm năng suất rất cao.
  - **quality** [neutral, 3/5]: Chỉ có 1 correction ý định thật từ user (trace c740302f: 'phải dùng .venv... đừng dùng python global'), cho thấy thiếu ngữ cảnh môi trường mà skill có thể cố định. Các 'retry' còn lại đều ở bước screenshot computer-use (gửi Teams) — là flakiness thao tác desktop chứ không phải user phải sửa sai ý định, nên áp lực correction chỉ ở mức trung bình.
- Consolidator: Pattern process_macro lặp gần y hệt qua 3 session (efficiency chấm 5, tiết kiệm hàng chục bước test→báo cáo Teams) nên đáng đóng gói, dù quality chỉ neutral (3) vì các 'retry' chủ yếu là flakiness screenshot desktop chứ không phải sửa sai ý định — bất đồng này hạ trục cohesion về 4. Personalization 5 nhờ Teams cá nhân + ràng buộc môi trường .venv; lưu ý facts bị extract_error nên quyết nghị dựa chính vào verdicts.
- Evidence sessions: local_9590c9ea-0194-4cba-83e3-b4cfe158b151, local_c740302f-169d-480f-9db6-db907ab210c0, local_902a32c7-7c3a-4c11-8b55-cbaf104b102d
- Risk flags: none

### 2. `write-short-prd` — process_macro (process)
- Trigger (VI): Khi user yêu cầu viết PRD ngắn gọn cho một feature/ý tưởng/bài toán (hỏi làm rõ scope rồi xuất file PRD).
- Trigger (EN): When the user asks for a short PRD for a feature/idea/problem (clarify scope, then produce the PRD file).
- Score total: 10
- Flow (action template):
- Debate (judge verdicts):
  - **efficiency** [approve, 4/5]: Chuỗi clarify-scope → write → present lặp lại qua cả 4 session; riêng local_2fc0fafb là chuỗi ~10 bước thủ công (AskUserQuestion, ToolSearch, TaskCreate×2, TaskUpdate×3, Write, bash, present_files) mà đóng gói skill sẽ template hóa được. Tuy có session ngắn (local_58a12280 chỉ 2 lượt) làm giảm độ đồng đều, nhưng tần suất lặp + độ dài chuỗi dài nhất đủ để tiết kiệm đáng kể thao tác orchestration mỗi lần.
  - **quality** [reject, 1/5]: Cả 4 trace đều không có một correction/retry nào (feedback=null toàn bộ), user ra prompt một lần là pipeline chạy thẳng tới Write/present_files. Ở các phiên có rủi ro mơ hồ scope, assistant đã chủ động AskUserQuestion ngay (session 69da99fc, 2fc0fafb) nên không phát sinh sửa sai. Trên trục Quality không có tín hiệu user phải đính chính ý định → không có nhu cầu cố định khung bằng skill.
- Consolidator: Candidate là process_macro nên giá trị nằm ở việc template hóa chuỗi orchestration lặp lại (clarify-scope → write → present qua cả 4 session, dài nhất ~10 bước thủ công) — đúng trục PROCESS_ORCHESTRATION mà efficiency judge ủng hộ. Bất đồng với quality judge: judge này reject vì không thấy correction/retry, nhưng đó là trục INEFFICIENT_RETRY, không phải tiêu chí loại của một process_macro (chạy trơn không sửa sai là điểm cộng, không phải lý do bác). Hạ recurrence/cohesion/personalization so với prelim vì có 1 session chỉ 2 lượt làm giảm độ đồng đều và facts trích bị lỗi nên personalization chưa được củng cố bằng evidence.
- Evidence sessions: local_69da99fc-6485-427f-ac53-76afd677467c, local_58a12280-1630-4541-a772-71b2f05f241c, local_1ad3485a-e559-49cb-ba67-90c5f9b5882b, local_2fc0fafb-26a4-4eb9-83e6-d201ce23199e
- Risk flags: none

### 3. `attach-to-running-desktop-app` — improvement_lesson (inefficient)
- Trigger (VI): Khi cần thao tác trên một app desktop (Teams) để báo cáo: dùng cửa sổ app đang mở sẵn trên máy, KHÔNG khởi chạy lại từ terminal — bài học từ việc user phải sửa lại nhiều lần.
- Trigger (EN): When operating a desktop app (Teams) to report: attach to the already-open window, do NOT relaunch from terminal — lesson from repeated user corrections.
- Score total: 10
- Flow (action template):
- Debate (judge verdicts):
  - **efficiency** [neutral, 3/5]: Cả hai trace đều là chuỗi dài (mỗi phiên ~47 bước bị lược + nhiều vòng computer-use screenshot 'retry') và lặp lại qua 2 session, cho thấy có chi phí thủ công thật. Nhưng bài học đóng gói chỉ bỏ được bước 'relaunch từ terminal', còn phần tốn thao tác nhất — vòng lặp screenshot/key retry khi điều khiển Teams — không được skill này giải quyết, nên tiết kiệm chỉ ở mức vừa.
  - **quality** [reject, 2/5]: Các correction/retry thực tế trong trace KHÔNG khớp với intent của candidate: 'retry' chỉ xuất hiện trên các screenshot computer-use (friction thao tác UI Teams), còn correction rõ ràng duy nhất ('lần sau nhớ phải dùng .venv trong project, đừng dùng python global') là về môi trường Python — không phải về việc relaunch vs attach app desktop. Không có bằng chứng user phải sửa sai 'nhiều lần' vì agent khởi chạy lại Teams từ terminal, nên skill này không cố định đúng khung mà user thực sự phải đính chính.
- Evidence sessions: local_902a32c7-7c3a-4c11-8b55-cbaf104b102d, local_c740302f-169d-480f-9db6-db907ab210c0
- Risk flags: none


## Rejected candidates

- `read-and-summarize-file` — low_score
