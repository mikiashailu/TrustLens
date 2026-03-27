# TrustLens AI — System architecture

This document describes how the **TrustLens** backend is structured, how components interact, and how it runs in Docker vs locally. For HTTP details, see **[API.md](./API.md)**.

---

## 1. High-level view

```mermaid
flowchart LR
  subgraph clients["Clients"]
    FE[Web / mobile app]
    AD[Admin dashboard]
    LB[Load balancer / probes]
  end

  subgraph runtime["TrustLens runtime"]
    API[FastAPI / Uvicorn]
    SVC[Services layer]
    OCR[Tesseract OCR]
    CV[OpenCV / mutagen]
  end

  subgraph persistence["Persistence"]
    PG[(PostgreSQL or SQLite)]
    FS[File storage uploads/]
  end

  FE -->|JSON / multipart + user_id| API
  AD -->|JSON + user_id| API
  LB -->|GET /health /status| API
  API --> SVC
  SVC --> PG
  SVC --> FS
  SVC --> OCR
  SVC --> CV
```

**API surface (conceptual):**

| Area | Routes | Auth |
|------|--------|------|
| **Liveness / readiness** | `GET /health`, `GET /status` | None |
| **Auth & profile** | `/auth/*`, `GET /profile` | `user_id` on protected routes |
| **eKYC uploads** | `POST/GET /identity` | `user_id` |
| **Trust & eligibility** | `POST /trust-result`, `POST /eligible` | `user_id` |
| **Trust Card (demo)** | `POST /trust-card/issue`, `GET /trust-card`, `POST /trust-card/select` | `user_id` |
| **Analytics** | `GET /stats/overview`, `GET /stats/risk` | `user_id` (no admin RBAC yet) |

- **Services** implement validation, trust scoring, OCR, media probes, eligibility rules, card issuance heuristics, and **aggregate stats** (stats reuse the trust pipeline).
- **Database** stores users, identity submissions, and **trust_cards** (one demo card per user when eligible).
- **File storage** holds ID front/back, video, and audio (**relative paths** in DB; not base64 in `GET /identity`).

---

## 2. Deployment topology (Docker Compose)

```mermaid
flowchart TB
  subgraph host["Host machine"]
    Browser[Browser / Postman]
    Browser -->|:8000| API_CT
  end

  subgraph compose["Docker network: app_network"]
    API_CT[container: trustlens-api]
    DB_CT[container: trustlens-db]
    API_CT -->|:5432| DB_CT
    VOL_DB[(volume: postgres_data)]
    VOL_UP[(volume: api_uploads)]
    DB_CT --- VOL_DB
    API_CT --- VOL_UP
  end
```

| Service | Image / build | Role |
|---------|----------------|------|
| **api** | `Dockerfile` (Python 3.12, Tesseract) | FastAPI app, port **8000** → host |
| **db** | `docker/db` | PostgreSQL, **no** host port by default (only reachable from `api`) |

Environment: `DATABASE_URL` points the API at `db:5432`. Uploads persist in the **`api_uploads`** named volume.

**Local (non-Docker):** `database_url` defaults to SQLite under `./data/`; uploads default to `./uploads/` (see `app/config.py`).

---

## 3. Application layering (code layout)

```mermaid
flowchart TB
  subgraph api_layer["app/api"]
    H[routes_health — /health /status]
    R1[routes_auth]
    R2[routes_profile]
    R3[routes_identity]
    R4[routes_trust]
    R5[routes_trust_card]
    R6[routes_stats]
    D[deps.py — get_current_user]
  end

  subgraph schema_layer["app/schemas"]
    P[auth_flow trust_api trust_card stats_api]
  end

  subgraph service_layer["app/services"]
    ID[identity_files]
    TR[trust_result_analysis]
    TE[trust_engine]
    DO[document_ocr]
    MP[media_probe]
    TC[trust_card_service]
    ST[stats_service]
    PW[passwords]
  end

  subgraph data_layer["app/db"]
    M[models.py — User IdentitySubmission TrustCard]
    SE[session.py]
    MG[migrate.py]
  end

  H --> SE
  R1 & R2 & R3 & R4 & R5 & R6 --> D
  R1 & R2 & R3 & R4 & R5 & R6 --> P
  R3 --> ID
  R4 --> TR
  R4 --> TE
  R5 --> TC
  R6 --> ST
  TR --> DO
  TR --> MP
  TR --> ID
  ST --> TR
  TC --> TR
  R1 --> PW
  D --> M
  R1 & R2 & R3 & R4 & R5 & R6 --> SE
  SE --> M
```

| Layer | Responsibility |
|-------|----------------|
| **Routes** | HTTP mapping, status codes, DI (`get_current_user`, `get_db`) |
| **Schemas** | Pydantic request/response models and OpenAPI |
| **Services** | Files, trust breakdown, OCR (name/phone/sex/DOB/nationality), eligibility, trust card threshold, **stats aggregations** |
| **DB** | ORM models, `init_db()` + `create_all` + `migrate` hooks |

**Entry point:** `app/main.py` — lifespan creates `data/` and upload dir, runs `init_db()`, mounts routers (**health first**, then auth → profile → identity → trust → trust_card → stats).

---

## 4. Core domain entities (data model)

```mermaid
erDiagram
  User ||--o{ IdentitySubmission : owns
  User ||--o| TrustCard : "optional 1:1"

  User {
    uuid id PK
    string full_name
    string phone UK
    string sex "column gender"
    date date_of_birth
    string nationality
    string occupation
    string business_type
    float monthly_income
    string password_hash
    datetime created_at
  }

  TrustCard {
    uuid id PK
    uuid user_id FK UK
    uuid submission_id FK
    int combined_score_at_issue
    string card_suffix
    string selected_product
    datetime created_at
    datetime updated_at
  }

  IdentitySubmission {
    uuid id PK
    uuid user_id FK
    datetime created_at
    string document_front_path
    string document_back_path
    string video_path
    string audio_path
    int document_front_size_bytes
    int document_back_size_bytes
    int video_size_bytes
    int audio_size_bytes
    bool eligible
    string eligibility_reasons
    int trust_score
    string risk_level
    string trust_reasons
  }
```

Paths under `uploads/` are **relative** strings; resolved via `settings.upload_dir` and `identity_files.absolute_under_uploads`.

---

## 5. Request flows

### 5.1 Health (no auth)

```mermaid
sequenceDiagram
  participant LB as Probe / monitor
  participant A as API
  participant DB as Database

  LB->>A: GET /health
  A-->>LB: 200 { status: healthy }

  LB->>A: GET /status
  A->>DB: SELECT 1
  A-->>LB: 200 { status, database, app, version }
```

`/health` does **not** ping the DB. `/status` does — use for readiness-style monitoring.

### 5.2 Registration / session (demo auth)

```mermaid
sequenceDiagram
  participant C as Client
  participant A as API
  participant DB as Database

  C->>A: POST /auth/sign-up or /auth/sign-in
  A->>DB: insert or lookup User
  A-->>C: UserProfileResponse including id
  Note over C: Store id; send as user_id query param on protected routes
```

**Auth model:** `user_id` query parameter (`get_current_user`). **Hackathon-style**, not production OAuth2/JWT.

### 5.3 Identity upload → trust → eligibility → card → stats

```mermaid
sequenceDiagram
  participant C as Client
  participant A as API
  participant FS as Upload FS
  participant DB as Database
  participant T as trust_result_analysis

  C->>A: POST /identity?user_id=… multipart
  A->>FS: validate_and_save front/back/video/sound
  A->>DB: IdentitySubmission row
  A-->>C: IdentitySubmissionMetaResponse

  C->>A: POST /trust-result?user_id=…
  A->>DB: latest IdentitySubmission
  A->>T: build_trust_result(sub, user)
  T->>T: OCR DOB nationality name phone sex clarity OpenCV mutagen
  A-->>C: TrustResultResponse

  C->>A: POST /eligible?user_id=…
  A->>T: same + trust_engine.evaluate_financial_eligibility
  A-->>C: EligibleResponse

  opt Trust Card combined greater than 45
    C->>A: POST /trust-card/issue
    A->>DB: upsert TrustCard
  end

  opt Admin dashboard
    C->>A: GET /stats/overview
    A->>T: build_trust_result per user with submission
    A-->>C: DashboardStatsResponse
  end
```

**Latest submission:** `GET /identity`, `POST /trust-result`, `POST /eligible`, and trust-card **issue** logic all anchor on the **most recent** `IdentitySubmission` by `created_at` for that user.

**Stats:** `stats_service` calls **`build_trust_result`** once per user who has at least one submission — correct but **O(users)**; fine for demos, cache or batch for scale.

---

## 6. Trust pipeline (logical)

```mermaid
flowchart TB
  subgraph inputs["Inputs"]
    U[User profile name phone sex DOB nationality]
    F[ID front/back on disk]
    V[Video file]
    AU[Audio file]
  end

  subgraph document_mod["Document modality"]
    OCR[document_ocr Tesseract PyMuPDF]
    H1[Clarity heuristics per side]
    OCR --> H1
  end

  subgraph video_mod["Video modality"]
    CV[media_probe OpenCV]
    H2[Resolution duration size]
    CV --> H2
  end

  subgraph audio_mod["Audio modality"]
    MU[media_probe mutagen]
    H3[Duration bitrate size]
    MU --> H3
  end

  F --> document_mod
  V --> video_mod
  AU --> audio_mod
  U --> document_mod

  subgraph combine["Aggregation"]
    M[section_score per modality 0 to 100]
    C[combined_score mean of three]
  end

  document_mod --> M
  video_mod --> M
  audio_mod --> M
  M --> C
  C --> EL[trust_engine loan device card tiers]
  C --> TC[trust_card_service threshold 45]
```

Many checks remain **heuristic** or **uncertain** (default priors) until stronger ML (face, liveness, ASR) is added.

---

## 7. Trust Card & analytics (cross-cutting)

| Component | Role |
|-----------|------|
| **`trust_card_service`** | Reads live **`combined_score`** via **`build_trust_result`**; issues **`TrustCard`** row if score **> 45**; mock display suffix; product selection persisted. |
| **`stats_service`** | Counts users/submissions; recomputes trust per user for **prime** count, **global** average, **modality pass rates**, **risk tiers**, and **suspicious pattern** heuristics. |
| **`trust_engine`** | Maps **`combined_score`** to loan tiers and device/card **eligibility flags** (unchanged contract for `/eligible`). |

---

## 8. External dependencies (runtime)

| Dependency | Used for |
|------------|----------|
| **PostgreSQL** (Compose) / **SQLite** (default local) | Users, submissions, trust_cards |
| **Filesystem** | Uploaded binaries |
| **Tesseract** | OCR — name, phone, sex, **DOB**, **nationality** on ID |
| **PyMuPDF** | PDF first page → image → OCR |
| **OpenCV (headless)** | Video metadata |
| **mutagen** | Audio metadata |
| **passlib + bcrypt** | Password hashing |

---

## 9. Security & operations notes (honest scope)

- **Transport:** Use HTTPS in production in front of Uvicorn.
- **Authentication:** Raw **`user_id`** query string is **not** production-grade; add JWT/OAuth and **roles** (e.g. restrict **`/stats/*`** to admins).
- **`/stats/*`:** Same gate as **`/profile`** today — any valid user can call analytics; fix before real multi-tenant use.
- **Secrets:** Use proper secret management for DB URLs and keys in production.
- **File access:** No public CDN for uploads; add signed URLs or a gated download API if the UI must show media.
- **Trust Card:** Demo only — not PCI, not a real PAN.

---

## 10. Related docs

- **[API.md](./API.md)** — All routes, bodies, `user_id`, health vs stats vs trust **`status`** fields.
- **[SCORING_MODEL_AND_PRESENTATION_FAQ.md](./SCORING_MODEL_AND_PRESENTATION_FAQ.md)** — How scores are computed and presentation Q&A.
