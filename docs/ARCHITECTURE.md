# TrustLens AI — System architecture

This document describes how the **TrustLens** backend is structured, how components interact, and how it runs in Docker vs locally.

---

## 1. High-level view

```mermaid
flowchart LR
  subgraph clients["Clients"]
    FE[Web / mobile app]
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

  FE -->|HTTP JSON / multipart| API
  API --> SVC
  SVC --> PG
  SVC --> FS
  SVC --> OCR
  SVC --> CV
```

- **API** exposes REST endpoints (`/auth`, `/profile`, `/identity`, `/trust-result`, `/eligible`).
- **Services** implement validation, trust scoring, OCR, and media probing.
- **Database** stores users and identity submission metadata (paths, sizes, eligibility flags).
- **File storage** holds uploaded ID images, video, and audio (not returned as base64 from `GET /identity`).

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
    R1[routes_auth]
    R2[routes_profile]
    R3[routes_identity]
    R4[routes_trust]
    D[deps.py — get_current_user]
  end

  subgraph schema_layer["app/schemas"]
    P[Pydantic models — request/response]
  end

  subgraph service_layer["app/services"]
    ID[identity_files]
    TR[trust_result_analysis]
    TE[trust_engine]
    DO[document_ocr]
    MP[media_probe]
    PW[passwords]
  end

  subgraph data_layer["app/db"]
    M[models.py — SQLAlchemy ORM]
    SE[session.py — engine, get_db]
    MG[migrate.py — lightweight schema fixes]
  end

  R1 & R2 & R3 & R4 --> D
  R1 & R2 & R3 & R4 --> P
  R3 --> ID
  R4 --> TR
  R4 --> TE
  TR --> DO
  TR --> MP
  TR --> ID
  R1 --> PW
  D --> M
  R1 & R2 & R3 & R4 --> SE
  SE --> M
```

| Layer | Responsibility |
|-------|----------------|
| **Routes** | HTTP mapping, status codes, dependency injection |
| **Schemas** | Validation and OpenAPI shapes |
| **Services** | Business rules: file validation, trust breakdown, eligibility bands, OCR |
| **DB** | Persistence, `init_db()` + `create_all` + `migrate` hooks |

**Entry point:** `app/main.py` — lifespan creates `data/` and upload dir, runs `init_db()`, mounts routers.

---

## 4. Core domain entities (data model)

```mermaid
erDiagram
  User ||--o{ IdentitySubmission : owns

  User {
    uuid id PK
    string full_name
    string phone UK
    string sex "column: gender"
    string occupation
    string business_type
    float monthly_income
    string password_hash
    datetime created_at
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

Paths under `uploads/` are **relative** strings stored in the DB; the server resolves them against `settings.upload_dir`.

---

## 5. Request flows

### 5.1 Registration / session (demo auth)

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

**Auth model:** `user_id` query parameter resolves the user (`get_current_user`). This is a **hackathon-style** pattern, not production OAuth2/JWT.

### 5.2 Identity upload → trust → eligibility

```mermaid
sequenceDiagram
  participant C as Client
  participant A as API
  participant FS as Upload filesystem
  participant DB as Database
  participant T as trust_result_analysis

  C->>A: POST /identity?user_id=… multipart files
  A->>FS: validate_and_save front/back/video/sound
  A->>DB: IdentitySubmission row + paths + eligibility heuristics
  A-->>C: IdentitySubmissionMetaResponse

  C->>A: POST /trust-result?user_id=…
  A->>DB: latest IdentitySubmission for user
  A->>T: build_trust_result(sub, user)
  T->>T: OCR, resolution heuristics, OpenCV/mutagen
  A-->>C: TrustResultResponse

  C->>A: POST /eligible?user_id=…
  A->>T: same pipeline + trust_engine.evaluate_financial_eligibility
  A-->>C: EligibleResponse + metrics
```

**Latest submission:** `GET /identity`, `POST /trust-result`, and `POST /eligible` all use the **most recent** `IdentitySubmission` by `created_at` for that `user_id`.

---

## 6. Trust pipeline (logical)

```mermaid
flowchart TB
  subgraph inputs["Inputs"]
    U[User profile — name, phone, sex]
    F[ID front/back files on disk]
    V[Video file]
    A[Audio file]
  end

  subgraph document_mod["Document modality"]
    OCR[document_ocr — Tesseract + PyMuPDF]
    H1[Clarity heuristics]
    OCR --> H1
  end

  subgraph video_mod["Video modality"]
    CV[media_probe — OpenCV]
    H2[Resolution / duration / size]
    CV --> H2
  end

  subgraph audio_mod["Audio modality"]
    MU[media_probe — mutagen]
    H3[Duration / bitrate / size]
    MU --> H3
  end

  F --> document_mod
  V --> video_mod
  A --> audio_mod
  U --> document_mod

  subgraph combine["Aggregation"]
    M[Per-modality section_score 0–100]
    C[combined_score — mean of three]
  end

  document_mod --> M
  video_mod --> M
  audio_mod --> M
  M --> C
  C --> EL[trust_engine — loan / device / card tiers]
```

Many checks are **heuristic** or **uncertain** (placeholder scores until real ML/face/liveness/ASR is added). OCR depends on **Tesseract** (bundled in Docker image; optional `TESSERACT_CMD` on Windows).

---

## 7. External dependencies (runtime)

| Dependency | Used for |
|------------|----------|
| **PostgreSQL** (Compose) / **SQLite** (default local) | Users, submissions |
| **Filesystem** | Uploaded binaries |
| **Tesseract** | `pytesseract` — ID text for name/phone/sex matching |
| **PyMuPDF** | First page of PDF IDs → raster → OCR |
| **OpenCV (headless)** | Video width/height/duration when decodable |
| **mutagen** | Audio duration/bitrate when metadata exists |
| **passlib + bcrypt** | Password hashing |

---

## 8. Security & operations notes (honest scope)

- **Transport:** Assume HTTPS in production in front of Uvicorn (reverse proxy).
- **Authentication:** Passing raw `user_id` in the query string is **not** secure for production; replace with sessions/JWT/OAuth and authorization checks.
- **Secrets:** DB credentials in Compose are for dev; use secrets management in production.
- **File access:** No public CDN URL for uploads in the current design; add signed URLs or a gated download API if the frontend must display media.

---

## 9. Related docs

- **[API.md](./API.md)** — Endpoints, bodies, and query parameters for frontend integration.
