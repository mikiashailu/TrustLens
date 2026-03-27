# TrustLens AI Backend (MVP)

- **`POST /identity`** — upload document, video, sound (`X-User-Id`)
- **`GET /identity`** — **latest** submission for that user: `user_id`, `submission_id`, **`media`** with **relative paths** only (no base64)
- **`POST /trust-result`** — **`X-User-Id` only** (no body); uses your **latest** submission; per-modality criteria; document modality uses **Tesseract OCR** to compare **profile full name** and **phone** to text read from the ID (images + first PDF page)
- **`POST /eligible`** — **`X-User-Id` only** (no body); same latest submission as trust-result; **Birr loan tiers** from `combined_score` (see below)

## Loan tiers (`combined_score` 0–100)

| Score   | Result |
|--------|--------|
| ≤ 25   | Not eligible for loan |
| 26–50  | Eligible for **5000** birr loan |
| 51–69  | Eligible for **10000** birr loan |
| 70–100 | Eligible for **150000** birr loan |

Uncertain checks in trust-result use a **default 0.5** score (prior) so `section_score` is never inflated by `null` criteria.

## Quick start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Docs: http://127.0.0.1:8000/docs

### Document OCR (name / phone checks)

Install **[Tesseract](https://github.com/tesseract-ocr/tesseract)** and ensure `tesseract` is on your `PATH`. Docker image installs `tesseract-ocr` automatically.

On **Windows**, if Tesseract is not on PATH, set in `.env`:

`TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe`

Matching uses your profile **`full_name`** (Latin tokens + **fuzzy** match on OCR) and **`phone`** (Ethiopia **`09xxxxxxxx` / `2519…`** only). Long digit runs from **Reg. No. / dates** no longer count as a “wrong phone”. Non-Latin IDs may stay **uncertain** until you add another language pack or engine.

Video/audio trust uses **OpenCV** (resolution, duration) and **mutagen** (audio length, bitrate) when those packages are installed (`requirements.txt`).

## Auth

Header **`X-User-Id`** (user UUID) on protected routes. Sign-up / sign-in unchanged.

## GET /identity example

```json
{
  "user_id": "…",
  "submission_id": "…",
  "media": {
    "document_path": "user-uuid/submission-uuid/document.jpg",
    "video_path": "…",
    "sound_path": "…"
  }
}
```

Paths are relative to the server upload directory (`uploads/`). Resolve files locally on the server or expose a separate media route if needed.

## Docker

```bash
docker compose up --build
```
