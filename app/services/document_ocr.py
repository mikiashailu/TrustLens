"""Extract text from ID documents (image/PDF) and compare to profile name and phone."""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Literal

from PIL import Image, ImageEnhance, ImageOps

from app.config import settings
from app.schemas.trust_api import UNCERTAIN_SCORE_DEFAULT

Status = Literal["pass", "fail", "uncertain"]

# Tesseract page segmentation modes; IDs are often sparse multi-block text.
_OCR_PSMS = (6, 11, 3)


def _configure_tesseract() -> bool:
    try:
        import pytesseract
    except ImportError:
        return False
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    return True


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


def _core_phone_digits(phone: str) -> str:
    """Strip common Ethiopia prefixes; compare last 9 digits when possible."""
    d = _digits_only(phone)
    if d.startswith("251") and len(d) > 3:
        d = d[3:]
    if d.startswith("0") and len(d) > 1:
        d = d[1:]
    if len(d) >= 9:
        return d[-9:]
    return d


def _preprocess_for_ocr(im: Image.Image) -> Image.Image:
    """Upscale small photos and boost contrast — helps low-res ID photos."""
    im = im.convert("RGB")
    w, h = im.size
    long_edge = max(w, h)
    if long_edge < 1400:
        scale = 1400 / long_edge
        nw, nh = int(w * scale), int(h * scale)
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    im = ImageOps.autocontrast(im, cutoff=2)
    im = ImageEnhance.Sharpness(im).enhance(1.15)
    return im


def _tesseract_strings(im: Image.Image) -> str:
    import pytesseract

    chunks: list[str] = []
    for psm in _OCR_PSMS:
        try:
            t = pytesseract.image_to_string(im, lang="eng", config=f"--psm {psm}")
            if t and t.strip():
                chunks.append(t)
        except Exception:
            continue
    if not chunks:
        return ""
    merged = "\n".join(chunks)
    lines = dict.fromkeys(line.strip() for line in merged.splitlines() if line.strip())
    return "\n".join(lines.keys())


def extract_document_text(path: Path) -> str:
    """OCR for images; first PDF page rendered then OCR. Empty string on failure."""
    ext = path.suffix.lower()
    if not _configure_tesseract():
        return ""

    try:
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"):
            with Image.open(path) as im:
                im = _preprocess_for_ocr(im)
                return _tesseract_strings(im).strip()

        if ext == ".pdf":
            import fitz  # PyMuPDF

            doc = fitz.open(path)
            if doc.page_count == 0:
                return ""
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=200)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            im = _preprocess_for_ocr(im)
            return _tesseract_strings(im).strip()
    except Exception:
        return ""

    return ""


def ocr_available() -> bool:
    try:
        import pytesseract
    except ImportError:
        return False
    if not _configure_tesseract():
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _normalize_name_letters(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _latin_name_like_phrases(ocr_text: str) -> list[str]:
    """Pull sequences of Latin letters (e.g. GELILA MAMO BIRESAW) from noisy OCR."""
    raw = ocr_text.upper()
    phrases = re.findall(r"[A-Z]{2,}(?:\s+[A-Z]{2,}){1,8}", raw)
    out: list[str] = []
    for p in phrases:
        cleaned = re.sub(r"\s+", " ", p.strip())
        if len(cleaned.replace(" ", "")) >= 6:
            out.append(cleaned)
    return out


def _best_name_fuzzy(profile_norm: str, ocr_blob: str) -> float:
    """Best ratio between profile name and any window of similar length in OCR."""
    ob = _normalize_name_letters(ocr_blob)
    if len(ob) < 3 or len(profile_norm) < 3:
        return 0.0
    pl = len(profile_norm)
    best = 0.0
    max_win = min(len(ob), pl + 12)
    min_win = max(4, pl - 8)
    for win in range(max_win, min_win - 1, -1):
        for i in range(0, len(ob) - win + 1):
            chunk = ob[i : i + win]
            r = difflib.SequenceMatcher(None, profile_norm, chunk).ratio()
            if r > best:
                best = r
    for phrase in _latin_name_like_phrases(ocr_blob):
        pn = _normalize_name_letters(phrase)
        r = difflib.SequenceMatcher(None, profile_norm, pn).ratio()
        if r > best:
            best = r
    return best


def match_name_on_document(ocr_text: str, full_name: str) -> tuple[Status, float, str]:
    if not ocr_text.strip():
        st: Status = "uncertain"
        return st, UNCERTAIN_SCORE_DEFAULT, "No OCR text extracted (empty document, unsupported format, or OCR unavailable)."

    profile_norm = _normalize_name_letters(full_name)
    norm_ocr = _normalize_name_letters(ocr_text)
    tokens = [t for t in re.split(r"\s+", full_name.strip().lower()) if len(t) >= 2]
    if not tokens:
        return "uncertain", UNCERTAIN_SCORE_DEFAULT, "Profile full name has no matchable tokens."

    hits = sum(1 for t in tokens if t in norm_ocr)
    ratio = hits / len(tokens)
    if ratio >= 0.85 or (len(tokens) <= 2 and hits == len(tokens)):
        return "pass", 1.0, f"OCR matched {hits}/{len(tokens)} name tokens to profile."

    fuzzy = _best_name_fuzzy(profile_norm, ocr_text)
    if fuzzy >= 0.78:
        return "pass", 1.0, f"Name matched via fuzzy OCR (similarity {fuzzy:.2f}); verify profile matches ID English line."
    if fuzzy >= 0.55:
        return "uncertain", max(UNCERTAIN_SCORE_DEFAULT, fuzzy), (
            f"Partial fuzzy name match ({fuzzy:.2f}). Re-upload a straighter, brighter photo or higher resolution if this should pass."
        )

    if hits == 0:
        preview = (ocr_text[:120] + "…") if len(ocr_text) > 120 else ocr_text
        preview = re.sub(r"\s+", " ", preview)
        return (
            "fail",
            0.0,
            f"No confident name match. OCR snippet: {preview!r} — ensure profile full name matches the English line on the ID.",
        )
    return "uncertain", max(0.35, min(0.85, ratio)), f"Partial name match ({hits}/{len(tokens)} tokens)."


def _ethiopian_mobile_digit_runs(ocr_digits: str) -> list[str]:
    """10-digit runs typical of 09xxxxxxxx (and 2519… mobile) after stripping to digits only."""
    runs: list[str] = []
    for i in range(0, len(ocr_digits) - 9):
        if ocr_digits[i : i + 2] == "09":
            runs.append(ocr_digits[i : i + 10])
    for i in range(0, len(ocr_digits) - 11):
        if ocr_digits[i : i + 4] == "2519":
            chunk = ocr_digits[i : i + 12]
            if len(chunk) == 12:
                runs.append(chunk)
    return runs


def match_phone_on_document(ocr_text: str, registered_phone: str) -> tuple[Status, float, str]:
    core = _core_phone_digits(registered_phone)
    if not core or len(core) < 7:
        return "uncertain", UNCERTAIN_SCORE_DEFAULT, "Registered phone has too few digits to compare."

    ocr_digits = _digits_only(ocr_text)
    if len(ocr_digits) < 7:
        return (
            "uncertain",
            UNCERTAIN_SCORE_DEFAULT,
            "No digit sequences in OCR. Many Ethiopian resident IDs do not print a phone number.",
        )

    if core in ocr_digits or (f"0{core}" in ocr_digits and len(core) == 9):
        return "pass", 1.0, "Registered phone (normalized) found in document OCR digits."

    for win in range(min(15, len(ocr_digits)), 6, -1):
        for i in range(len(ocr_digits) - win + 1):
            chunk = ocr_digits[i : i + win]
            c = _core_phone_digits(chunk)
            if c == core or (len(c) >= 9 and c[-9:] == core):
                return "pass", 1.0, "Phone digits matched a sequence in OCR."

    mobile_runs = _ethiopian_mobile_digit_runs(ocr_digits)
    if mobile_runs:
        for run in mobile_runs:
            rcore = _core_phone_digits(run)
            if rcore == core:
                return "pass", 1.0, "Ethiopian mobile-style number in OCR matches registered phone."
        return (
            "fail",
            0.0,
            "OCR shows an Ethiopian mobile-style number (09… / 2519…) that does not match your registered phone.",
        )

    return (
        "uncertain",
        UNCERTAIN_SCORE_DEFAULT,
        "No Ethiopian mobile number (09xxxxxxxx) detected in OCR. Resident IDs often omit phone; "
        "ID/registrar numbers were not treated as a phone mismatch.",
    )


def _normalize_profile_sex(sex: str) -> str | None:
    s = sex.strip().lower()
    if re.fullmatch(r"m|male|man|masc|masculine", s):
        return "male"
    if re.fullmatch(r"f|female|woman|fem|feminine", s):
        return "female"
    return None


def _ocr_sex_marker_signals(ocr_upper: str) -> tuple[bool, bool]:
    """Return (male_likely, female_likely) from English-oriented ID OCR."""
    male_word = bool(re.search(r"\bMALE\b", ocr_upper))
    female_word = bool(re.search(r"\bFEMALE\b", ocr_upper))
    male_field = bool(
        re.search(r"(?:SEX|GENDER)\s*[:\-]?\s*(?:MALE|M)\b", ocr_upper)
        or re.search(r"(?:SEX|GENDER)\s*[:\-]?\s*M\s*(?:\n|$|/|,)", ocr_upper)
    )
    female_field = bool(
        re.search(r"(?:SEX|GENDER)\s*[:\-]?\s*(?:FEMALE|F)\b", ocr_upper)
        or re.search(r"(?:SEX|GENDER)\s*[:\-]?\s*F\s*(?:\n|$|/|,)", ocr_upper)
    )
    male = male_word or male_field
    female = female_word or female_field
    return male, female


def match_sex_on_document(ocr_text: str, profile_sex: str) -> tuple[Status, float, str]:
    if not ocr_text.strip():
        return (
            "uncertain",
            UNCERTAIN_SCORE_DEFAULT,
            "No OCR text extracted; cannot compare sex to profile.",
        )

    profile_g = _normalize_profile_sex(profile_sex)
    if profile_g is None:
        return (
            "uncertain",
            UNCERTAIN_SCORE_DEFAULT,
            f"Profile sex {profile_sex!r} is not a standard male/female label for ID matching.",
        )

    ocr_u = ocr_text.upper()
    male_hit, female_hit = _ocr_sex_marker_signals(ocr_u)

    if male_hit and female_hit:
        return (
            "uncertain",
            UNCERTAIN_SCORE_DEFAULT,
            "OCR shows both male and female indicators; ID may be noisy or multi-line — verify manually.",
        )

    if profile_g == "male":
        if male_hit:
            return "pass", 1.0, "Document OCR indicates male, matching profile."
        if female_hit:
            return (
                "fail",
                0.0,
                "Document OCR indicates female, which does not match a male profile — check profile or re-upload a clearer ID.",
            )
        return (
            "uncertain",
            UNCERTAIN_SCORE_DEFAULT,
            "Could not find a clear male (M/MALE) sex marker in OCR; try a straighter photo or ensure the sex field is visible.",
        )

    if female_hit:
        return "pass", 1.0, "Document OCR indicates female, matching profile."
    if male_hit:
        return (
            "fail",
            0.0,
            "Document OCR indicates male, which does not match a female profile — check profile or re-upload a clearer ID.",
        )
    return (
        "uncertain",
        UNCERTAIN_SCORE_DEFAULT,
        "Could not find a clear female (F/FEMALE) sex marker in OCR; try a straighter photo or ensure the sex field is visible.",
    )
