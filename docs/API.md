# TrustLens AI API — Frontend integration guide

**Base URL (local):** `http://127.0.0.1:8000`  
**Swagger UI:** `http://127.0.0.1:8000/docs`  
**OpenAPI JSON:** `http://127.0.0.1:8000/openapi.json`

JSON bodies use `Content-Type: application/json` unless noted.

**Recent doc updates:** **`/health`** & **`/status`** (service status, no auth); **`/stats/...`** remains **analytics** (not the same as “status”). See **“Status vs stats vs trust checks”** below.

---

## Status vs stats vs trust checks (don’t mix these up)

| Concept | What it is |
|---------|------------|
| **`GET /health`** | **Liveness** — API process responds. **No** `user_id`, **no** DB check. For simple “is the server up?” probes. |
| **`GET /status`** | **Readiness-style** — returns `app`, `version`, and whether **`database`** is `connected` or `unavailable`. **No** `user_id`. Still returns **HTTP 200** with `"status": "degraded"` if DB is down (so you always get JSON; tune to **503** in production if your orchestrator prefers it). |
| **`GET /stats/overview`** & **`GET /stats/risk`** | **Analytics / dashboard** — aggregates over users and trust scores. **Requires** `user_id` (demo auth). **Not** a health check. |
| **`RequirementCheck.status`** in **`POST /trust-result`** | Per-check outcome: **`pass`** \| **`fail`** \| **`uncertain`** for each trust criterion (document / video / audio). This is **eKYC scoring**, not server health. |

---

## Network & port (sharing with devices on your LAN)

With **Docker Compose**, the API is published on host port **8000**.

| Where you call from | Example base URL |
|---------------------|------------------|
| Same machine | `http://127.0.0.1:8000` or `http://localhost:8000` |
| Phone / another PC (same Wi‑Fi) | `http://<your-PC-LAN-IPv4>:8000` (e.g. `http://192.168.7.241:8000`) |

Allow **inbound TCP 8000** in the host firewall if other devices cannot connect. On the machine that runs Docker, opening your own LAN IP in a browser sometimes fails on Windows; test from another device.

If the **web app** is on a different origin (e.g. Vite on port 5173), you may need **CORS** enabled on the API for that origin.

---

## Authentication model (hackathon / demo)

**No JWTs or API keys.** After sign-up or sign-in, store the user’s **`id`** (UUID). On **protected** routes, pass:

| Query param | Type | Required on protected routes |
|-------------|------|------------------------------|
| `user_id` | UUID string | Yes |

**Example:** `GET /profile?user_id=550e8400-e29b-41d4-a716-446655440000`

If `user_id` is missing, invalid, or not found → **401** `{"detail": "No user found for that id."}` (or **422** for invalid UUID).

**Sign-up** and **sign-in** do **not** use `user_id`.

---

## Error responses

| Shape | When |
|--------|------|
| `{"detail": "string"}` | Typical `HTTPException` (401, 403, 404, 409, …) |
| `{"detail": [ { "loc", "msg", "type" }, ... ] }` | Validation (**422**) |

---

## Route index

| Method | Path | Auth |
|--------|------|------|
| GET | `/health` | No |
| GET | `/status` | No |
| POST | `/auth/sign-up` | No |
| POST | `/auth/sign-in` | No |
| GET | `/auth/registered-users` | `user_id` |
| GET | `/profile` | `user_id` |
| POST | `/identity` | `user_id` |
| GET | `/identity` | `user_id` |
| POST | `/trust-result` | `user_id` |
| POST | `/eligible` | `user_id` |
| POST | `/trust-card/issue` | `user_id` |
| GET | `/trust-card` | `user_id` |
| POST | `/trust-card/select` | `user_id` |
| GET | `/stats/overview` | `user_id` |
| GET | `/stats/risk` | `user_id` |

**Admin / dashboard:** Stats routes use the same **`user_id`** gate as other protected APIs. There is **no separate admin role** in the backend yet — restrict who can see dashboard data in production (e.g. role check or separate service).

---

# Endpoints

## 0. Service status (no authentication)

### `GET /health`

**Purpose:** Liveness probe — confirms the HTTP server is handling requests.

**Query params:** none  

**Response `200`:**

```json
{ "status": "healthy" }
```

Does **not** verify PostgreSQL/SQLite; use **`GET /status`** for that.

---

### `GET /status`

**Purpose:** App identity + **database connectivity** (`SELECT 1` on the configured DB).

**Query params:** none  

**Response `200` (typical):**

```json
{
  "status": "ok",
  "database": "connected",
  "app": "TrustLens AI API",
  "version": "0.1.0"
}
```

**Response `200` when DB unreachable:**

```json
{
  "status": "degraded",
  "database": "unavailable",
  "app": "TrustLens AI API",
  "version": "0.1.0"
}
```

| Field | Meaning |
|-------|--------|
| `status` | **`ok`** if DB ping succeeded, else **`degraded`** |
| `database` | **`connected`** \| **`unavailable`** |
| `app` | From server config |
| `version` | API bundle version string (matches `app/main.py` / health router) |

---

## 1. `POST /auth/sign-up`

Register a new user.

**Query params:** none  

**Request body (JSON):**

| Field | Type | Constraints |
|-------|------|-------------|
| `full_name` | string | 1–255 chars |
| `phone` | string | 5–32 chars, **unique** |
| `sex` | string | 1–32 chars (e.g. `Male`, `Female`, `F`, `M`) — **not** `gender` |
| `date_of_birth` | string (ISO **date**) | e.g. `"1999-07-24"` — compared to ID via OCR in `/trust-result` |
| `nationality` | string | 1–128 chars (e.g. `Ethiopian`, `United States`) — compared to ID via OCR |
| `occupation` | string | 1–255 chars |
| `business_type` | string | 1–255 chars |
| `monthly_income` | number | ≥ 0, ≤ 1_000_000_000 |
| `password` | string | 6–128 chars |

**Response `201` — `UserProfileResponse`:**

| Field | Type |
|-------|------|
| `id` | UUID |
| `full_name` | string |
| `phone` | string |
| `sex` | string |
| `date_of_birth` | string (date) \| **null** (legacy users before this field existed) |
| `nationality` | string \| **null** (legacy) |
| `occupation` | string |
| `business_type` | string |
| `monthly_income` | number |

**Errors:** **409** `Phone already registered.` · **422** validation.

---

## 2. `POST /auth/sign-in`

**Query params:** none  

**Body (JSON):** `phone`, `password` (same constraints as schema).

**Response `200`:** `UserProfileResponse`  

**Errors:** **401** `Invalid phone or password.`

---

## 3. `GET /auth/registered-users`

Paginated users (safe profile fields). **Protected.**

**Query params:** `user_id` (**required**), `limit` (default 20, 1–200), `offset` (default 0).

**Response `200` — `RegisteredUsersResponse`:** `total`, `limit`, `offset`, `users` (`UserProfileResponse[]`).

---

## 4. `GET /profile`

**Query params:** `user_id` (**required**).

**Response `200`:** `UserProfileResponse`

---

## 5. `POST /identity`

New identity submission: **ID front**, **ID back**, **video**, **audio**. **Protected.**

**Content-Type:** `multipart/form-data`  
**Query params:** `user_id` (**required**).

**Form files:**

| Field | Allowed extensions |
|-------|---------------------|
| `document_front` | `.pdf`, `.jpg`, `.jpeg`, `.png` |
| `document_back` | same |
| `video` | `.mp4`, `.webm`, `.mov`, `.mkv` |
| `sound` | `.mp3`, `.wav`, `.m4a`, `.ogg`, `.aac` |

Max **50 MiB per file**.

**Response `200` — `IdentitySubmissionMetaResponse`:** `id`, `user_id`, `created_at`, `document_front_*` / `document_back_*` / `video_*` / `sound_*` content types and sizes, `eligible`, `eligibility_reasons`, `trust_score`, `risk_level`, `trust_reasons`.

**Errors:** **400** bad type/size · **401** bad `user_id`.

**Example (fetch):**

```javascript
const form = new FormData();
form.append("document_front", frontFile);
form.append("document_back", backFile);
form.append("video", videoFile);
form.append("sound", soundFile);
await fetch(`${API}/identity?user_id=${userId}`, { method: "POST", body: form });
```

---

## 6. `GET /identity`

Latest submission: `user_id`, `submission_id`, and **relative** paths under `media` (no signed URLs in API). **Protected.**

**Query params:** `user_id` (**required**).

**`media`:** `document_front_path`, `document_back_path`, `video_path`, `sound_path` (each string \| null).

**Errors:** **404** `No identity upload yet. POST /identity first.`

---

## 7. `POST /trust-result`

Full trust breakdown for the **latest** submission. **No body.** **Protected.**

**Query params:** `user_id` (**required**).

**Response `200` — `TrustResultResponse`:** `submission_id`, `document`, `video`, `audio`, `combined`.

Each modality is a **`ModalityTrustBreakdown`:** `modality`, `criteria[]`, `section_score` (0–100).

Each **`RequirementCheck`:** `key`, `label`, `status` (`pass` \| `fail` \| `uncertain`), `score` (0–1), `detail`.

**`combined` (`CombinedTrustBreakdown`):** `document_score`, `video_score`, `audio_score`, `combined_score` (rounded mean of the three, 0–100).

### Document modality — typical `criteria[].key` values

Use these keys for stable UI logic (exact set depends on OCR availability and file presence):

| `key` | Meaning |
|-------|--------|
| `document_front_present` | Front file on disk |
| `document_back_present` | Back file on disk |
| `id_document_front_clear` | Front resolution / clarity heuristic |
| `id_document_back_clear` | Back resolution / clarity heuristic |
| `id_name_matches_full_name` | Name on ID vs profile (OCR) |
| `id_phone_matches_phone` | Phone on ID vs profile (OCR) |
| `id_sex_matches_profile` | Sex on ID vs profile (OCR) |
| `id_dob_matches_profile` | Date of birth on ID vs profile `date_of_birth` |
| `id_nationality_matches_profile` | Nationality / citizenship text vs profile `nationality` |

If Tesseract is unavailable or there are no document paths, the OCR-based rows are usually **uncertain** with an explanatory `detail`.

**Errors:** **404** if no submission yet.

---

## 8. `POST /eligible`

Same trust pipeline as `/trust-result`, **latest** submission. Returns eligibility copy + product messaging. **No body.** **Protected.**

**Query params:** `user_id` (**required**).

**Response `200` — `EligibleResponse`:**

| Field | Type |
|-------|------|
| `submission_id` | UUID |
| `document_score`, `video_score`, `audio_score`, `combined_score` | int (0–100) |
| `loan_tier` | `none` \| `1-5000` \| `5001-10000` \| `10001-150000` |
| `loan_offer` | string |
| `eligible_for_loan` | boolean (e.g. false when combined very low) |
| `eligible_for_device_financing` | boolean |
| `device_financing_offer` | string |
| `eligible_for_credit_card` | boolean |
| `credit_card_offer` | string |
| `metrics` | `EligibilityMetrics` |

**`EligibilityMetrics`:** `modality_min_score`, `modality_max_score`, `modality_spread`, `weakest_modality`, `strongest_modality` (each modality: `document` \| `video` \| `audio`).

**Errors:** **404** if no submission yet.

---

## 9. Trust Card (demo — not a real payment card)

**Threshold:** live **`combined_score` must be greater than 45** (same computation as `/trust-result` / `/eligible`). **One card per user.** `masked_number` is **mock** (not PCI / not a real PAN).

All routes require **`user_id`** as a query parameter.

| Method | Path | Body |
|--------|------|------|
| POST | `/trust-card/issue` | none |
| GET | `/trust-card` | none |
| POST | `/trust-card/select` | JSON `{ "product": "loan" \| "device_financing" \| "invoice_financing" }` |

### `POST /trust-card/issue`

Creates a card or **updates** `submission_id` / `combined_score_at_issue` if a card already exists (**`card_suffix` unchanged**).

**Errors:** **404** no identity upload · **403** combined score ≤ 45.

### `GET /trust-card`

Returns the card only if it exists **and** live combined score is still **> 45**.

**Errors:** **404** no upload, no card, or missing issue step · **403** score ≤ 45.

### `POST /trust-card/select`

**Content-Type:** `application/json`  

**Body:** `TrustCardSelectRequest` — `{ "product": "loan" | "device_financing" | "invoice_financing" }`

**Response `200` — `TrustCardResponse`:**

| Field | Type |
|-------|------|
| `id` | UUID |
| `user_id` | UUID |
| `submission_id` | UUID \| null |
| `combined_score_at_issue` | int (0–100) |
| `masked_number` | string (e.g. `•••• •••• •••• 1234`) |
| `card_suffix` | string |
| `selected_product` | `loan` \| `device_financing` \| `invoice_financing` \| null |
| `available_products` | `TrustCardProductOption[]` |
| `created_at` | datetime (ISO 8601) |

**`TrustCardProductOption`:** `key`, `label`, `description`.

**Suggested UX:** call `POST /eligible` → if `combined_score > 45`, call `POST /trust-card/issue` → let the user choose `POST /trust-card/select`.

---

## 10. `GET /stats/overview`

Dashboard KPIs for admin / ops charts: user totals, “prime” verifiers, system-wide trust average, 7-day upload volume, and modality pass-rate health. **Protected** — **`user_id`** query param required (same demo auth as `/profile`).

**Query params:** `user_id` (**required**).

**Response `200` — `DashboardStatsResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `total_users` | int | Count of rows in `users`. |
| `verified_prime_count` | int | Users with at least one submission whose **latest** **`combined_score` > 80** (high-tier heuristic). |
| `global_trust_score` | float | Mean **`combined_score`** (0–100) across those users only; **`0.0`** if no one has submitted identity yet. |
| `verification_volume_7d` | array | Exactly **7** objects (see `VerificationDayVolume` below). |
| `modality_health` | object | See `ModalityHealth` below. |

**`VerificationDayVolume` (each element of `verification_volume_7d`):**

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | ISO date **`YYYY-MM-DD`** (UTC calendar day on server). |
| `count` | int | Number of **`POST /identity`** submissions whose `created_at` falls on that day. |

The array covers **seven consecutive days** ending **today (UTC)**.

**`modality_health` (`ModalityHealth`):**

| Field | Type | Description |
|-------|------|-------------|
| `document_pass_rate_pct` | float | Mean % of document **`criteria`** with **`status === "pass"`** on each user’s **latest** submission, then averaged across users. |
| `video_pass_rate_pct` | float | Same for **video** modality. |
| `audio_pass_rate_pct` | float | Same for **audio** modality. |

**Implementation note:** The server recomputes trust via the same pipeline as **`POST /trust-result`** (`build_trust_result`) for every user who has an identity submission. Fine for demos; cache or precompute for large scale.

**Example:**

`GET /stats/overview?user_id=<uuid>`

```json
{
  "total_users": 120,
  "verified_prime_count": 15,
  "global_trust_score": 62.4,
  "verification_volume_7d": [
    { "date": "2025-03-20", "count": 3 },
    { "date": "2025-03-21", "count": 5 }
  ],
  "modality_health": {
    "document_pass_rate_pct": 58.2,
    "video_pass_rate_pct": 71.0,
    "audio_pass_rate_pct": 66.5
  }
}
```

*(Example shortened: real responses include **seven** `verification_volume_7d` entries, one per day.)*

---

## 11. `GET /stats/risk`

Risk monitoring aggregates: alert count, score-tier distribution, and heuristic “suspicious pattern” counts. **Protected** — **`user_id`** required.

**Query params:** `user_id` (**required**).

**Response `200` — `RiskStatsResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `active_alerts` | int | Users whose **latest** **`combined_score` < 40** (review-queue heuristic). |
| `risk_distribution` | `RiskBucket[]` | Fixed order: **critical**, **high**, **medium**, **low** (see tiers below). |
| `suspicious_patterns` | `SuspiciousPattern[]` | Human-readable **`pattern`** + **`count`** (see list below). |

**`RiskBucket` (each element of `risk_distribution`):**

| Field | Type | Description |
|-------|------|-------------|
| `level` | string | **`critical`** \| **`high`** \| **`medium`** \| **`low`** |
| `count` | int | Users in that tier (latest submission only). |

**Tier rules (latest `combined_score`):**

| `level` | Score range |
|---------|-------------|
| `critical` | ≤ 25 |
| `high` | 26 – 40 |
| `medium` | 41 – 65 |
| `low` | > 65 |

**`SuspiciousPattern`:**

| Field | Type |
|-------|------|
| `pattern` | string (fixed labels from backend) |
| `count` | int |

**Current `suspicious_patterns` rows (in order):**

1. **Low combined trust (latest score < 40)** — same cohort as a subset of `active_alerts` context.  
2. **Document modality: 2+ failed checks on latest verification** — two or more **`fail`** statuses in document criteria.  
3. **Multiple identity submissions within 24 hours (same user)** — any pair of uploads for one user ≤ **24 hours** apart.

Tune thresholds in **`app/services/stats_service.py`**.

**Example:**

`GET /stats/risk?user_id=<uuid>`

```json
{
  "active_alerts": 8,
  "risk_distribution": [
    { "level": "critical", "count": 2 },
    { "level": "high", "count": 6 },
    { "level": "medium", "count": 40 },
    { "level": "low", "count": 72 }
  ],
  "suspicious_patterns": [
    { "pattern": "Low combined trust (latest score < 40)", "count": 8 },
    { "pattern": "Document modality: 2+ failed checks on latest verification", "count": 5 },
    { "pattern": "Multiple identity submissions within 24 hours (same user)", "count": 1 }
  ]
}
```

---

# Quick integration checklist

1. `POST /auth/sign-up` (include **`sex`**, **`date_of_birth`**, **`nationality`**) or `POST /auth/sign-in` → save **`id`**.
2. Append **`?user_id=<uuid>`** to every protected URL.
3. `POST /identity` with **`document_front`**, **`document_back`**, **`video`**, **`sound`**.
4. `POST /trust-result` for criteria (including DOB / nationality checks).
5. `POST /eligible` for tiers and offers.
6. If `combined_score > 45`: `POST /trust-card/issue`, then optionally `POST /trust-card/select`.
7. Admin dashboard: `GET /stats/overview` and `GET /stats/risk` with the same `user_id` (add real RBAC in production).

---

# OpenAPI

Use **`/docs`** or **`/openapi.json`** for generated schemas and **Try it out** requests.

---

# What’s new & updated (changelog)

Use this list when syncing the frontend or reviewing integration docs.

## New

- **`GET /health`** — liveness (no DB). **`GET /status`** — `app`, `version`, `database` connectivity (`connected` / `unavailable`), `status` `ok` or `degraded`. **No** `user_id`. Implemented in **`app/api/routes_health.py`**.
- **Analytics / risk (dashboard):**
  - **`GET /stats/overview`** → **`DashboardStatsResponse`**: `total_users`, `verified_prime_count` (combined **> 80**), `global_trust_score`, `verification_volume_7d` (`VerificationDayVolume`: `date`, `count`), `modality_health` (`ModalityHealth`: pass-rate % per modality).
  - **`GET /stats/risk`** → **`RiskStatsResponse`**: `active_alerts` (combined **< 40**), `risk_distribution` (`RiskBucket`: `level`, `count`), `suspicious_patterns` (`SuspiciousPattern`: `pattern`, `count`).
  - Schemas live in **`app/schemas/stats_api.py`**; logic in **`app/services/stats_service.py`**. Both routes require **`user_id`** — **no admin RBAC** in API yet.
- **`date_of_birth`** and **`nationality`** on **`POST /auth/sign-up`** and **`UserProfileResponse`** — required at sign-up; used by OCR checks on the ID.
- **Document trust checks** (in **`POST /trust-result`**, document modality):
  - **`id_dob_matches_profile`** — profile DOB vs parsed / literal dates in OCR.
  - **`id_nationality_matches_profile`** — profile nationality vs citizenship wording in OCR.
- **Trust Card** (demo, not a real card):
  - **`POST /trust-card/issue`** — create/refresh card when live **`combined_score > 45`**.
  - **`GET /trust-card`** — read card if score still **> 45**.
  - **`POST /trust-card/select`** — body `{ "product": "loan" | "device_financing" | "invoice_financing" }`.
- **Route index** and **LAN / firewall / CORS** notes at the top of this guide.
- **Table of document `criteria[].key`** values under **`POST /trust-result`** for stable UI mapping.

## Updated / renamed

- **Gender → Sex:** API field is **`sex`** (DB column may still be `gender` internally). Request **`sex`**, not `gender`.
- **Identity uploads:** **`document_front`** and **`document_back`** (no single `document` field).
- **`GET /identity`** / paths: **`document_front_path`**, **`document_back_path`**, **`video_path`**, **`sound_path`**.
- **`POST /trust-result`** and **`POST /eligible`:** no JSON body; resolve **latest** submission via **`user_id`** only.
- **This document (`API.md`):** rewritten as a single integration guide with checklist, trust-card section, and criterion keys.

## Database / ops (for backend deploys)

- Migrations / startup fixes may add **`users.date_of_birth`**, **`users.nationality`**, and table **`trust_cards`** on existing databases — restart the API after deploy so `init_db` / migrate hooks run.
