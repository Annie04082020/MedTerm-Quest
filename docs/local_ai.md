# 本機 AI 使用方式

所有 AI 功能皆由使用者自行觸發，不需要信用卡、訂閱或雲端 API 金鑰。沒有 Ollama 或轉錄模型時，原有六種遊戲、題庫、作答紀錄及自我評估照常運作。

## 硬體與起始設定

本機檢測：RTX 3060 Laptop、6144 MiB VRAM、約 15.7 GiB RAM。檢測當時僅約 1.1 GiB RAM 可用；請先關閉耗記憶體程式。預設 Qwen3 4B 量化模型，較小備選 qwen3:1.7b；轉錄預設 faster-whisper small。這些配置仍須用實際教材檢查品質及記憶體用量。

- Ollama context 固定 4096 tokens，關閉 thinking；每次一題，輸出最多 1200 tokens。
- 來源片段上限 1200 字元，一個工作最多 8 個片段，避免整份講義塞進 prompt。
- 每個 request 設 `keep_alive: 0` 並確認卸載；輸出驗證失敗時也會嘗試卸載。
- 轉錄在獨立子程序中執行；CUDA 失敗時先結束子程序，再嘗試 CPU int8。
- 無法確認 Ollama GPU 狀態，或其他 Ollama 模型仍佔用 GPU 時，轉錄採 CPU 安全模式。請自行停止其他 GPU 程式以使用 CUDA 轉錄。
- CPU fallback 仍需要 RAM；LLM fallback 可用 RAM 少於 3 GiB、small 轉錄少於 2 GiB 時會停止並提示，不會反覆耗盡記憶體。

## 一、維持原本啟動方式

```powershell
npm run build
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

開啟 [http://127.0.0.1:8000](http://127.0.0.1:8000)，進入 **Local AI studio**。請使用單一 backend worker，不要加 `--workers 2` 或更大的數字。既有 SQLite 不需刪除；新資料表在啟動時新增。

## 二、Ollama（自行安裝及下載）

先自行從 [Ollama 官方網站](https://ollama.com/download)安裝。程式不會替你安裝或下載模型。

在啟動 Ollama 的 PowerShell 視窗中設定：

```powershell
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
ollama serve
```

如果 Ollama 桌面程式已在執行，先退出它再套用設定並重啟；不要在同一個 port 同時啟動兩個服務。環境變數必須作用於 **Ollama 程序**，僅設定在 FastAPI 的視窗不會改變既有 Ollama 服務。亦可依官方文件在使用者的 `.ollama/server.json` 設定 `"disable_ollama_cloud": true`。

確認你願意下載後，在另一個終端機自行執行：

```powershell
ollama pull qwen3:4b
```

此 tag 的量化模型約 2.5 GB；執行時另外需要 context 及 runtime 記憶體。較小備選也需你自行決定是否下載：

```powershell
ollama pull qwen3:1.7b
```

下載完成後，按 **Check hardware & models**，選取已安裝模型。可以選其他已安裝的本機模型，但本機 6 GB VRAM 不適合大模型。應用程式僅連線固定的 `127.0.0.1:11434`，停用 HTTP proxy/redirect，並拒絕 cloud 名稱及 Ollama metadata 中的遠端模型別名。不要自行把該 loopback port 代理到遠端服務。

## 三、匯入講義或字幕

若原始教材位於 repository 外，建議優先使用新 **Course materials** 外部教材庫。設定 `backend/.env` 的 `COURSE_MATERIALS_DIR` 後，可直接掃描與處理原位置的檔案，不必手動上傳或搬到 repository。詳見 [外部教材庫說明](external_materials.md)。以下手動上傳方式仍保留。

TXT、SRT、VTT 不需 AI 套件。PDF 功能需要可選套件：

```powershell
python -m pip install -r backend/requirements-import.txt
```

在 **Import material** 選取檔案、週次與主題，再按 **Import locally**。檔案送到本機 FastAPI，存入忽略於 Git 的 `imports/`，不會送到外部服務。PDF 保留頁碼；SRT/VTT 保留每個原始字幕的起訖時間；TXT 保留行號。相鄰文字會合併成小片段，同時保留各段的原始位置。掃描 PDF 需自行先做 OCR。

原始 PDF/TXT/SRT/VTT 上限 50 MB（文字解析另有 20 MB / 500 萬字元保護）；媒體上限 500 MB。可用 `MEDTERM_IMPORTS_PATH` 指定別的本機存放資料夾。不要提交個人教材到 Git。

## 四、媒體轉錄（可選）

若已有字幕，可完全略過這一步。需要從影片產生逐字稿時，先自行安裝：

```powershell
python -m pip install -r backend/requirements-transcription.txt
```

另需 FFmpeg 在 PATH 中。faster-whisper 的 GPU 模式還需要相容的 CUDA 12 cuBLAS 與 cuDNN 9 runtime；NVIDIA driver 本身不代表這些程式庫已安裝。缺少或不相容時會顯示 CUDA 錯誤並在允許時改用 CPU。**本次開發沒有自動安裝 CUDA、faster-whisper 或模型。**

small 模型須先由你自行下載至 `models/faster-whisper-small/`。可使用官方 Hugging Face CLI（以下指令會連網下載模型檔案，不會傳送教材）：

```powershell
# 僅在決定下載模型後執行；公開模型不需要登入或付費。
hf download Systran/faster-whisper-small --local-dir models/faster-whisper-small
```

`hf` 工具由 huggingface-hub 套件提供。模型資料夾至少須有 `model.bin`、`config.json`、`tokenizer.json`；完整下載也會包含其他設定檔。缺少 tokenizer 時會直接報錯，避免第三方套件嘗試從網路補抓。若模型已在其他位置，啟動後端前設定：

```powershell
$env:MEDTERM_WHISPER_MODEL_PATH = 'D:/Models/faster-whisper-small'
```

再匯入 MP4 / MP3 / WAV / M4A / WEBM / MKV。FFmpeg 先擷取音訊，轉錄完成、子程序釋放 GPU 後才可進行後續產題。內部強制 `local_files_only=True` 與 `HF_HUB_OFFLINE=1`。完成後的時間戳記及文字會保存在 SQLite 來源片段內。

## 五、產題與人工審核

1. 選取匯入完成的來源，可先按 **Inspect source chunks** 查看內容與來源位置。
2. 選題型、起始片段（從 1 開始）、每批題數（1–8），按 **Queue generation**。
3. 佇列顯示目前工作、片段及完成進度；前一個工作完成前不會載入下一個模型。
4. 生成內容先用 Pydantic 驗證，原文證據必須在來源片段中找到。這只能檢查格式及引文，不能保證模型對醫學概念的推論正確。
5. 展開草稿完整 JSON，確認／修改答案、繁中解釋、選項及評分規準。核對原文後勾選審核，才可 **Approve for practice**。不確定題目還需額外確認。
6. 核准後寫入原有題庫表，週次與主題自動出現在介面中。原有題目與作答紀錄保留。

模型標籤及 digest、來源片段、題型和 prompt 版本用於草稿快取。相同條件重試會重用已驗證且未捨棄的草稿，避免重複推論。失敗前已完成的草稿不會消失。JSON 解析錯誤、引用不存在、無效選項／配對／填字座標都會停止工作並顯示錯誤，不會進入可玩的題庫。

## 六、概念簡答批改

正常遊戲繼續使用原本的離線檢查。未辨識的 **Short answer / Clinical connections** 作答會提供 **Optional local AI feedback**，可選模型並排入相同佇列。批改依參考答案及 rubric 比對概念，將拼字錯誤與概念缺漏分開列出。

批改結果只是建議；須由使用者確認後才透過既有自我評估機制改變分數。也可以忽略 AI，直接自行評估。沒有 Ollama 時所有一般遊戲功能照常可用。

## 進度、取消與重試

工作狀態、進度、錯誤及草稿保存在既有 SQLite 的新增資料表。可取消等候中的工作；進行中的轉錄會終止子程序，Ollama 請求則等待目前單題請求結束或逾時，再確認資源釋放。後端中斷後，未完成工作會標示失敗，需要手動重試，不會默默重跑。

佇列最多 20 件待處理／執行中工作。檔案鎖避免同一份專案的多個後端同時執行處理階段；本程式無法控制其他應用程式使用 GPU。

## 驗證範圍

自動化測試使用模擬 Ollama 回覆驗證 JSON、來源、草稿審核、快取、FIFO、取消、CPU fallback 及離線遊戲相容性。瀏覽器驗證匯入與佇列及原有遊戲。由於本機尚未備妥 Ollama／Whisper 模型，真實推論品質、速度及 CUDA 相容性尚須安裝後用教材驗證。

參考：[Ollama API](https://docs.ollama.com/api/generate)、[停用雲端功能](https://docs.ollama.com/faq)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)。
