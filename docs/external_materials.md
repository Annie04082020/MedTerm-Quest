# 外部本機教材庫

原始教材留在 **`D:\NTU\Human_Anatomy_and_Physiology`**；程式位於 **`D:\Repositories\MedTerm-Quest`**。教材庫只讀取原始檔案，沒有搬移、重新命名、刪除或覆寫原檔的功能。

## 設定與啟動

後端現在會載入 `backend/.env`。這次已建立忽略於 Git 的設定檔：

```dotenv
COURSE_MATERIALS_DIR=D:/NTU/Human_Anatomy_and_Physiology
```

其他電腦可將根目錄 `.env.example` 複製為 `backend/.env` 並修改路徑。使用絕對路徑；PowerShell 環境變數若已設定同名值，會優先於 `.env`。變更設定後需重啟後端。沒有設定或找不到資料夾時，教材庫會顯示說明，一般遊戲仍正常運作。

依賴新增小型 `python-dotenv`；更新環境及重建介面：

```powershell
python -m pip install -r backend/requirements.txt
npm run build
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

開啟 [http://127.0.0.1:8000](http://127.0.0.1:8000)，選 **Course materials**。保持單一 backend worker。

## 先掃描，再選擇處理

1. 按 **Rescan materials**，遞迴發現 MP4、PDF、Markdown (`.md`)、TXT、SRT、VTT。副檔名大小寫皆可。其他格式略過。
2. 掃描串流讀取各檔案計算 SHA-256，每次只讀 1 MiB。**掃描不會解析文字、轉錄影片或呼叫 Ollama**。大影片首次掃描及重新掃描需要讀取完整內容，可能花一些時間；可在佇列取消。
3. 清單顯示檔名、相對路徑、類型、大小、修改日期、內容雜湊、重複提示、處理狀態，以及課程／週次／主題。支援搜尋、類型與狀態篩選、每頁 50 筆。
4. 按 **Edit association** 手動設定課程、週次與主題。新檔案的週次一律未指定，即使檔名有 `Week99` 或日期也不會猜測。可以先只分類；擷取前才要求有週次與主題。
5. 對 PDF / MD / TXT / SRT / VTT 按 **Extract text locally**。PDF 頁碼、字幕原始起訖時間、Markdown／TXT 行號都會保留。PDF 功能仍需可選的 PyMuPDF，掃描 PDF 沒有 OCR 時會清楚報錯。
6. 完成後可 **Inspect extracted text**，或 **Use in Local AI studio**。後者只預選來源，不會自動產題；須另按 Queue generation，並經既有草稿審核流程核准。

## 影片優先使用現有字幕／筆記

影片會列出目前教材目錄中的配對候選：

- 相同基本檔名，以及常見 `_transcript`、`_notes`、字幕語言等後綴；可以跨 `videos/`、`notes/` 等資料夾。
- 或你已手動設定成相同課程、週次及非空白主題的文字教材。

這些只是候選，不會從檔名推測週次。按 **Use transcript / notes** 時優先選 SRT，其次 VTT、TXT；沒有字幕再選 MD、PDF。同優先序且無法唯一判斷時會要求你在下拉選單選擇。可明確改選另一份候選。

沒有配對材料時，不會默默開始轉錄。只有按 **Transcribe video** 才會排入 FFmpeg＋faster-whisper small 工作。如果已有配對檔案，必須先勾選「略過既有配對，仍要重新轉錄」才能轉錄。GPU／CPU 選項與資源釋放沿用既有循序佇列。

這個動作不會安裝或下載模型。可選套件、模型準備與 CUDA／CPU fallback 詳見 [本機 AI 使用說明](local_ai.md)。

## 內容變更、重複與來源版本

- 每次重新掃描會重算雜湊，因此檔案即使大小及修改時間相同，內容變更仍可偵測。
- 相同內容顯示為重複，不會刪除任何副本。相容類型的擷取結果可重用快取，但各檔案保留獨立路徑及來源版本。
- 內容變更會清除該檔案的目前擷取連結，標示需重新擷取。配對字幕／筆記變更或遺失時，使用它的影片也會標示過期。
- 修改課程關聯後，需要重新擷取以建立新關聯的來源快照；原文內容相同可重用快取。
- 舊來源快照、已生成／核准的題目及作答紀錄不會被改寫或刪除。既有 AI studio 中的來源是不可變版本；教材庫則顯示目前版本。
- 掃描未找到的檔案標為 Missing，保留歷史；不會刪除原有題目。未完成或取消的掃描不會將尚未掃到的檔案誤標為遺失。
- 擷取前會再驗證實際讀取的內容雜湊。檔案若在掃描後改變，會拒絕沿用舊版本並要求重新掃描。

## 資料位置與存取限制

新增 SQLite 表：`material_files`（索引與關聯）、`material_extract_cache`（擷取快取）、`material_source_links`（不可變來源版本的連結）。原有 `questions`、`attempts`、`local_jobs`、`local_drafts` 繼續使用；`local_sources` 以新增欄位保留課程名稱。沒有破壞性資料庫重建。

解析及 FFmpeg 只使用 `data/processing/` 中經雜湊驗證的臨時快照，完成或失敗後清理；原始教材以唯讀模式開啟。擷取文字、轉錄結果及題目保存在 SQLite；不會把字幕／筆記寫回教材目錄。

API 只接受掃描清單中的 opaque 檔案 ID，不接受任意檔案路徑。每次原檔存取都檢查設定目錄、正規化路徑、檔案類型及實際位置；跳過符號連結與 Windows junction。Windows 另外檢查開啟的檔案 handle 實際位置。沒有提供任意原始檔案下載端點；文字預覽回傳已保存的擷取內容。

`backend/.env`、SQLite、`data/`、`imports/`、模型、暫存音訊及轉錄快取都由 `.gitignore` 排除；原始教材本身位於 repository 外。備份時除資料庫外，也請自行保留外部教材；不必把教材加入 Git。

## API

| Endpoint | 用途 |
| --- | --- |
| `GET /api/materials` | 設定狀態、搜尋、篩選及分頁清單 |
| `POST /api/materials/scan` | 明確觸發唯讀掃描 |
| `PATCH /api/materials/{id}/association` | 設定 course、week（可為 null）、topic |
| `POST /api/materials/{id}/extract` | 明確觸發文字擷取／使用配對材料 |
| `POST /api/materials/{id}/transcribe` | 明確觸發 MP4 轉錄，需 confirm=true |
| `GET /api/materials/{id}/content` | 預覽目前版本已保存的文字 |

工作進度、取消及重試沿用 `/api/local/jobs`。AI 產題仍使用本機 Ollama，不需要付費 API 或雲端金鑰。
