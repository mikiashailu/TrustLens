# TrustLens AI API — Frontend integration guide

Base URL (local): `http://127.0.0.1:8000`  
Interactive docs: `http://127.0.0.1:8000/docs` (Swagger UI)

All JSON bodies use `Content-Type: application/json` unless noted.

---

## Authentication model (hackathon / demo)

**There are no JWTs or API keys.** After sign-up or sign-in, the API returns the user’s **`id`** (UUID). For every **protected** route, send that UUID as a **query parameter**:

| Query param | Type | Required on protected routes |
|-------------|------|------------------------------|
| `user_id`   | UUID string | Yes |

Example:

`GET /profile?user_id=550e8400-e29b-41d4-a716-446655440000`

If `user_id` is missing, invalid, or not found → **401** with `{"detail": "No user found for that id."}` (or FastAPI validation error for bad UUID shape).

**Sign-up** and **sign-in** do **not** require `user_id`.

---

## Error responses

| Shape | When |
|--------|------|
| `{"detail": "string message"}` | Most `HTTPException`s (401, 404, 409, etc.) |
| `{"detail": [ { "loc", "msg", "type" }, ... ] }` | Request validation (422) |

---

# Endpoints

## 1. `POST /auth/sign-up`

Register a new user.

**Query params:** none  

**Request body (JSON):**

| Field | Type | Constraints |
|-------|------|-------------|
| `full_name` | string | 1–255 chars |
| `phone` | string | 5–32 chars, must be **unique** |
| `sex` | string | 1–32 chars (e.g. `Male`, `Female`, `F`, `M`) |
| `occupation` | string | 1–255 chars |
| `business_type` | string | 1–255 chars |
| `monthly_income` | number | ≥ 0, ≤ 1_000_000_000 |
| `password` | string | 6–128 chars |

**Response `201` — `UserProfileResponse` (JSON):**

| Field | Type |
|-------|------|
| `id` | UUID |
| `full_name` | string |
| `phone` | string |
| `sex` | string |
| `occupation` | string |
| `business_type` | string |
| `monthly_income` | number |

**Errors:**

| Status | `detail` (typical) |
|--------|---------------------|
| 409 | `Phone already registered.` |
| 422 | Validation errors |

Store `id` as the current user’s ID; use it as `user_id` on protected calls.

---

## 2. `POST /auth/sign-in`

**Query params:** none  

**Request body (JSON):**

| Field | Type | Constraints |
|-------|------|-------------|
| `phone` | string | 5–32 chars |
| `password` | string | 1–128 chars |

**Response `200` — same as `UserProfileResponse` (see sign-up).

**Errors:**

| Status | `detail` |
|--------|----------|
| 401 | `Invalid phone or password.` |

---

## 3. `GET /auth/registered-users`

Paginated list of users (public profile fields only). **Protected.**

**Query params:**

| Param | Type | Default | Constraints |
|-------|------|---------|-------------|
| `user_id` | UUID | — | **Required** (caller must be a valid user) |
| `limit` | int | 20 | 1–200 |
| `offset` | int | 0 | ≥ 0 |

**Response `200` — `RegisteredUsersResponse`:**

| Field | Type |
|-------|------|
| `total` | int |
| `limit` | int |
| `offset` | int |
| `users` | `UserProfileResponse[]` |

---

## 4. `GET /profile`

Returns the profile for the user identified by `user_id`. **Protected.**

**Query params:**

| Param | Type | Required |
|-------|------|----------|
| `user_id` | UUID | Yes |

**Response `200` — `UserProfileResponse`**

**Errors:** 401 if user not found for `user_id`.

---

## 5. `POST /identity`

Upload **front ID**, **back ID**, **video**, and **audio** for a **new** identity submission. **Protected.**

**Content-Type:** `multipart/form-data`  

**Query params:**

| Param | Type | Required |
|-------|------|----------|
| `user_id` | UUID | Yes |

**Form fields (files):**

| Field name | Type | Allowed extensions |
|------------|------|---------------------|
| `document_front` | file | `.pdf`, `.jpg`, `.jpeg`, `.png` |
| `document_back` | file | same as front |
| `video` | file | `.mp4`, `.webm`, `.mov`, `.mkv` |
| `sound` | file | `.mp3`, `.wav`, `.m4a`, `.ogg`, `.aac` |

Max **50 MiB per file** (server-side).

**Response `200` — `IdentitySubmissionMetaResponse`:**

| Field | Type | Notes |
|-------|------|--------|
| `id` | UUID | Submission ID |
| `user_id` | UUID | Owner |
| `created_at` | string (ISO 8601 datetime) | |
| `document_front_content_type` | string \| null | |
| `document_back_content_type` | string \| null | |
| `video_content_type` | string \| null | |
| `sound_content_type` | string \| null | |
| `document_front_size_bytes` | int \| null | |
| `document_back_size_bytes` | int \| null | |
| `video_size_bytes` | int \| null | |
| `sound_size_bytes` | int \| null | |
| `eligible` | boolean | Quick gate from upload rules |
| `eligibility_reasons` | string[] | |
| `trust_score` | int \| null | |
| `risk_level` | string \| null | |
| `trust_reasons` | string[] | |

**Errors:** 400 for bad file type / oversize; 401 for bad `user_id`.

**Frontend example (fetch):**

```javascript
const form = new FormData();
form.append("document_front", frontFile);
form.append("document_back", backFile);
form.append("video", videoFile);
form.append("sound", soundFile);

await fetch(`${API}/identity?user_id=${userId}`, {
  method: "POST",
  body: form,
});
```

---

## 6. `GET /identity`

Latest identity submission for the user: IDs + **relative** storage paths (not URLs, not base64). **Protected.**

**Query params:**

| Param | Type | Required |
|-------|------|----------|
| `user_id` | UUID | Yes |

**Response `200` — `IdentityPathsResponse`:**

| Field | Type |
|-------|------|
| `user_id` | UUID |
| `submission_id` | UUID |
| `media` | object (see below) |

**`media` object:**

| Field | Type |
|-------|------|
| `document_front_path` | string \| null |
| `document_back_path` | string \| null |
| `video_path` | string \| null |
| `sound_path` | string \| null |

Paths are relative to the server upload root; the browser cannot load them unless you expose a **download/static route** or proxy—today the app is oriented around **server-side** trust processing.

**Errors:**

| Status | `detail` |
|--------|----------|
| 404 | `No identity upload yet. POST /identity first.` |

---

## 7. `POST /trust-result`

Full **per-modality** trust breakdown for the user’s **latest** identity submission. **No JSON body.** **Protected.**

**Query params:**

| Param | Type | Required |
|-------|------|----------|
| `user_id` | UUID | Yes |

**Response `200` — `TrustResultResponse`:**

| Field | Type |
|-------|------|
| `submission_id` | UUID |
| `document` | `ModalityTrustBreakdown` |
| `video` | `ModalityTrustBreakdown` |
| `audio` | `ModalityTrustBreakdown` |
| `combined` | `CombinedTrustBreakdown` |

**`ModalityTrustBreakdown`:**

| Field | Type |
|-------|------|
| `modality` | `"document"` \| `"video"` \| `"audio"` |
| `criteria` | `RequirementCheck[]` |
| `section_score` | int (0–100) |

**`RequirementCheck`:**

| Field | Type |
|-------|------|
| `key` | string (stable id for UI logic, e.g. `id_name_matches_full_name`) |
| `label` | string (human-readable) |
| `status` | `"pass"` \| `"fail"` \| `"uncertain"` |
| `score` | float (0–1) |
| `detail` | string |

**`CombinedTrustBreakdown`:**

| Field | Type |
|-------|------|
| `document_score` | int (0–100) |
| `video_score` | int (0–100) |
| `audio_score` | int (0–100) |
| `combined_score` | int (0–100) — mean of the three modality section scores (rounded) |

**Errors:** 404 if no identity submission yet (same message as `GET /identity`).

---

## 8. `POST /eligible`

Loan / financing eligibility derived from the **same** trust pipeline as `POST /trust-result`, using the **latest** submission. **No JSON body.** **Protected.**

**Query params:**

| Param | Type | Required |
|-------|------|----------|
| `user_id` | UUID | Yes |

**Response `200` — `EligibleResponse`:**

| Field | Type | Notes |
|-------|------|--------|
| `submission_id` | UUID | Submission that was scored |
| `document_score` | int | Copy of combined breakdown |
| `video_score` | int | |
| `audio_score` | int | |
| `combined_score` | int | 0–100 |
| `loan_tier` | string | One of: `none`, `1-5000`, `5001-10000`, `10001-150000` |
| `loan_offer` | string | Human-readable line |
| `eligible_for_loan` | boolean | e.g. false when score very low |
| `eligible_for_device_financing` | boolean | |
| `device_financing_offer` | string | |
| `eligible_for_credit_card` | boolean | |
| `credit_card_offer` | string | |
| `metrics` | `EligibilityMetrics` | |

**`EligibilityMetrics`:**

| Field | Type |
|-------|------|
| `modality_min_score` | int (0–100) |
| `modality_max_score` | int (0–100) |
| `modality_spread` | int (0–100) |
| `weakest_modality` | `"document"` \| `"video"` \| `"audio"` |
| `strongest_modality` | `"document"` \| `"video"` \| `"audio"` |

**Errors:** 404 if no identity submission yet.

---

# Quick integration checklist

1. `POST /auth/sign-up` or `POST /auth/sign-in` → save `id`.
2. Append `?user_id=<that id>` to: `/profile`, `/identity` (GET/POST), `/trust-result`, `/eligible`, `/auth/registered-users`.
3. Upload identity with `multipart/form-data` and four file fields: `document_front`, `document_back`, `video`, `sound`.
4. Call `POST /trust-result` for criteria UI; `POST /eligible` for product offers / tiers.

---

# OpenAPI

The live spec is always in sync with the server:

- JSON: `GET /openapi.json`
- UI: `GET /docs`

Use **“Try it out”** in Swagger to copy exact request shapes.
