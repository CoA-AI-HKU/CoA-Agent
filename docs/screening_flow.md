# 非診斷小檢查流程

## 部署與網址

GitHub Pages 應以 repository 的 `docs/` 目錄部署。頁面路徑是 `docs/screening/index.html`，公開網址是：

`https://ako-saka.github.io/CoA-Agent/screening/?token=SCREENING_TOKEN`

頁面不連接首頁、問卷或照顧者儀表板。它預設使用繁體中文，並可在沒有後端服務時完全靜態運作。

## Bot 發送流程

一次輕微記憶關注只會收到支持性回應。使用者主動要求小檢查、七日內出現兩次或以上相關關注訊號，或照顧者提出跟進時，bot 才先發送非診斷說明並徵求同意。使用者同意後才會建立連結。群組或 supergroup 不會收到 token；使用者須改用私人聊天。

已配對照顧者可使用 `/send_screening` 或 `/start_check`。邀請會先送給使用者徵求同意，不會直接發出小檢查連結。

## Token

Token 的用途固定為 `screening`，版本為 `cognitive_concern_screening_v1`，只對一個 `user_id` 有效且只能提交一次。自行開始的 token 預設 30 分鐘到期；照顧者建立的 token 預設 24 小時到期。網頁只把 URL token 保留在頁面記憶體，不顯示或寫入瀏覽器儲存空間。

## 結果標記

- `no_immediate_concern`：未見即時關注
- `monitor`：建議留意
- `follow_up_suggested`：建議跟進
- `urgent_safety`：安全問題需即時處理

這些是簡單的非診斷跟進標記，不是疾病判斷或分數。任何走失或安全關注會優先顯示即時安全指引；用藥不確定至少標記為建議留意；多項記憶、方向或日常工作關注會建議跟進。

## 私隱與提交

頁面只在記憶體計算逐題答案。預設不儲存原始答案，事件中的 `raw_answers_saved` 永遠是 `false`。如部署的同源服務提供 `POST /api/screening/submit`，頁面會提交 token、版本及以下結構化結果；純 GitHub Pages 部署則只在本機顯示結果，讓使用者自行分享。

```json
{
  "event_type": "screening_completed",
  "user_id": "resolved-from-token",
  "screening_version": "cognitive_concern_screening_v1",
  "risk_flag": "monitor",
  "total_score": 2,
  "max_score": 12,
  "raw_answers_saved": false
}
```

儀表板只顯示最近提出、最近完成、最近結果標記和非診斷跟進狀態，不顯示逐題答案。

## 用語政策

所有頁面、bot 訊息及儀表板均須清楚說明這不是診斷，也不能判斷一個人是否有腦退化症。結果只描述記憶與日常功能的關注訊號，以及是否建議留意、跟進或先處理安全問題。
