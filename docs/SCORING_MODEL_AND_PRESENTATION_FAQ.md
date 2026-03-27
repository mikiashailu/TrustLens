# Trust scoring — model overview, tech stack, and presentation Q&A

Use this document for **demo pitches**, **judges’ questions**, and **onboarding**. It describes what the system actually does today (honest scope) and which tools implement it.

---

## 1. One-sentence pitch

**TrustLens** combines **document**, **video**, and **audio** evidence from an eKYC upload into a **0–100 trust score** per modality and an overall **combined score**, then maps that score to **simple eligibility rules** for loans, device financing, and credit-card messaging—using **explainable checks** (pass / fail / uncertain) rather than a single black-box model.

---

## 2. What “model” means in this project (top level)

There is **no single end-to-end trained neural network** driving the main API score today. Instead, the system uses a **multi-modal scoring pipeline**:

| Concept | Meaning |
|---------|---------|
| **Modalities** | Three channels: **document** (ID front + back), **video**, **audio**. |
| **Criteria** | Each modality is broken into **requirement checks** (e.g. file present, resolution, OCR name match, video duration). |
| **Per-criterion score** | Each check returns a numeric score in **0–1** (and a **status**: `pass`, `fail`, or `uncertain`). |
| **Modality score (section score)** | **Average** of all criterion scores in that modality, scaled to **0–100** and clamped. |
| **Combined score** | **Rounded mean** of the three modality scores (document, video, audio)—also **0–100**. |
| **Eligibility layer** | A **separate rule engine** maps `combined_score` (and modality balance metrics) to **loan tiers** and flags for **device financing** and **credit card** messaging. |

So the “model” is best described as:

> **An explainable, rule- and signal-based fusion of document OCR, image/video/audio quality heuristics, and profile matching—aggregated into a combined trust score and then thresholded for financial product eligibility.**

**Upload-time note:** When files are first accepted, `POST /identity` also stores a **placeholder** `trust_score` / `risk_level` on the row using **very simple size-based heuristics** (`identity_files.evaluate_submission`). The **authoritative** breakdown for API consumers is **`POST /trust-result`**, which runs the full pipeline in `trust_result_analysis.build_trust_result`.

---

## 3. How the combined score is computed (simple formula)

1. For each modality, collect \(n\) criteria with scores \(s_1, \ldots, s_n\) each in \([0, 1]\).
2. **Modality score** \(=\) round/clamp \(\bigl(\frac{s_1 + \cdots + s_n}{n} \times 100\bigr)\) to **0–100**.
3. **Combined score** \(=\) round/clamp \(\frac{\text{document} + \text{video} + \text{audio}}{3}\).

**Financial mapping** (`trust_engine.evaluate_financial_eligibility`): purely **threshold-based** on `combined_score` (e.g. loan band none vs 1–5000 vs 5001–10000 vs 10001–150000), plus separate thresholds for device financing and credit-card eligibility. **Modality metrics** (min, max, spread, weakest/strongest modality) explain **imbalance** (e.g. great video but weak document).

---

## 4. What each modality uses (signals)

### Document (ID front + back)
- **Files on disk**, types, sizes; **image resolution / clarity** heuristics (Pillow).
- **OCR** (Tesseract via `pytesseract`; PDF first page via **PyMuPDF**): text extraction, then **profile matching** for **name** (tokens + fuzzy string similarity), **phone** (Ethiopia-oriented digit logic), **sex** (M/F markers in OCR vs profile).
- Many checks can be **`uncertain`** (default prior **0.5**) when data is missing or OCR is weak.

### Video
- **OpenCV** (when available): **resolution**, **duration** from container metadata.
- **File size** as a rough **bitrate / richness** proxy.
- **Face match, liveness, stress**: described as **requirements for a future system**; not scored by ML in this codebase (remain **uncertain**).

### Audio
- **mutagen** (when available): **duration**, **bitrate**.
- **File size** fallback if metadata is missing.
- **Voice vs profile / spoken name**: **future ASR / classifiers**; currently **uncertain** with guidance text.

---

## 5. Technologies used (checklist for slides)

| Area | Technology |
|------|------------|
| API | **FastAPI**, **Uvicorn** |
| Validation / OpenAPI | **Pydantic** v2 |
| Config | **pydantic-settings** |
| Database ORM | **SQLAlchemy** |
| DB drivers | **PostgreSQL** + **psycopg** (Docker); **SQLite** optional locally |
| Passwords | **passlib**, **bcrypt** |
| Images | **Pillow** |
| OCR | **Tesseract** (system) + **pytesseract** |
| PDF → image | **PyMuPDF** (`fitz`) |
| Video metadata | **OpenCV** (headless wheel) |
| Audio metadata | **mutagen** |
| String similarity (names) | **difflib** (stdlib) |
| Deployment | **Docker**, **Docker Compose** |

---

## 6. Presentation Q&A (suggested answers)

### “Is this AI / machine learning?”
**Answer:** Parts are **classical AI** (OCR is a mature ML stack in Tesseract). The **fusion and eligibility** layers are **transparent rules and averages**, not a trained deep model. The API is designed so you can **swap in** real face, liveness, or ASR models later while keeping the same response shape.

### “How accurate is the score?”
**Answer:** Today it’s a **prototype trust signal**, not a calibrated credit risk model. Accuracy depends on **scan quality**, **language** on the ID, and **upload format**. We expose **per-check status and detail** so users and auditors see *why* something passed or failed—not only a single number.

### “Why do so many checks say ‘uncertain’?”
**Answer:** **Uncertain** means “we didn’t run a strong enough signal to assert pass or fail.” We use a **neutral prior score (0.5)** so the pipeline stays stable until optional models (face, liveness, ASR) are connected. The **detail** field explains what to improve (resolution, lighting, length of recording, etc.).

### “Is this fair / biased?”
**Answer:** Any automated system can carry **bias** (OCR quality varies by script and scan quality; thresholds affect outcomes). This MVP **documents** checks and uses **explainable** outputs. Production would need **policy review**, **fairness testing**, and **human override** workflows—we don’t claim regulatory compliance here.

### “What about privacy and security?”
**Answer:** Uploads are **stored on the server filesystem**; metadata is in the **database**. The demo uses a **`user_id` query parameter**, which is **not** production-grade auth. A real deployment needs **encryption at rest**, **TLS**, **strong authentication**, **retention policies**, and **consent** aligned with local law (e.g. data protection rules).

### “Can someone game the score?”
**Answer:** **Heuristic** scores can be gamed with **better uploads** (which is partly desirable—clearer ID, longer video). **Malicious** gaming (deepfakes, replay) is why **liveness** and **face match** are called out as **future** hardening—not implemented as robust models in this repo.

### “What’s the difference between `trust_score` on upload and `/trust-result`?”
**Answer:** **`POST /identity`** sets a **quick placeholder** on the submission row from **file presence and sizes**. **`POST /trust-result`** recomputes a **full multi-criteria breakdown** from the stored files and profile—that’s what you should show in the UI for “why this score.”

### “How do loan tiers work?”
**Answer:** They’re **deterministic bands** on **combined_score** (see `trust_engine.py`): e.g. very low scores → no loan; higher bands map to increasing **principal ranges**; separate thresholds enable **device financing** and **credit card** messaging. **Not** an interest-rate or affordability engine—those would need income verification and regulation.

### “Does it support Ethiopian IDs only?”
**Answer:** **Phone logic** is oriented to **Ethiopian-style** mobile patterns where applicable. **OCR** uses **English** (`eng`) by default; **Amharic** or other scripts would need **extra language packs** or different engines. **Name matching** works best when the **profile name** aligns with the **Latin line** on the ID.

### “What would you add next for a real product?”
**Answer:** **Face embedding** match (video vs ID photo), **active liveness** (challenge-response), **ASR** for spoken name, **anti-fraud** (document authenticity), **backend auth** (JWT/OAuth), **audit logs**, and **model monitoring** with labeled data.

---

## 7. Related documents

- **[API.md](./API.md)** — Endpoints for integration.  
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — Components, Docker, and data flow.
