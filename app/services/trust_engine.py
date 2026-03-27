def _modality_metrics(document_score: int, video_score: int, audio_score: int) -> dict[str, str | int]:
    scores = {"document": document_score, "video": video_score, "audio": audio_score}
    weakest = min(scores, key=lambda k: scores[k])
    strongest = max(scores, key=lambda k: scores[k])
    vals = [document_score, video_score, audio_score]
    return {
        "modality_min_score": min(vals),
        "modality_max_score": max(vals),
        "modality_spread": max(vals) - min(vals),
        "weakest_modality": weakest,
        "strongest_modality": strongest,
    }


def evaluate_financial_eligibility(
    combined_score: int,
    document_score: int,
    video_score: int,
    audio_score: int,
) -> dict[str, str | bool | int]:
    """
    Loan bands by combined_score (0–100), amounts as numeric ranges only (no currency in tier id):
    - ≤25: not eligible for loan
    - 26–50: principal band 1–5000
    - 51–69: 5001–10000
    - 70–100: 10001–150000

    Device financing: combined_score ≥ 30.
    Credit card: combined_score ≥ 50.
    """
    cs = max(0, min(100, int(combined_score)))
    metrics = _modality_metrics(document_score, video_score, audio_score)

    eligible_device = cs >= 30
    eligible_cc = cs >= 50

    if cs <= 25:
        loan_tier = "none"
        loan_offer = "Not eligible for a loan."
        eligible_loan = False
    elif cs <= 50:
        loan_tier = "1-5000"
        loan_offer = "Eligible for a loan in the 1–5000 range."
        eligible_loan = True
    elif cs < 70:
        loan_tier = "5001-10000"
        loan_offer = "Eligible for a loan in the 5001–10000 range."
        eligible_loan = True
    else:
        loan_tier = "10001-150000"
        loan_offer = "Eligible for a loan in the 10001–150000 range."
        eligible_loan = True

    if eligible_device:
        d_offer = "Eligible for device financing based on your trust profile."
    else:
        d_offer = "Not eligible for device financing yet; improve document, video, and audio checks."

    if eligible_cc:
        cc_offer = "Eligible to apply for a credit card based on your trust profile."
    else:
        cc_offer = "Not eligible for a credit card yet; a higher combined trust score is required."

    out: dict[str, str | bool | int] = {
        "combined_score": cs,
        "loan_tier": loan_tier,
        "loan_offer": loan_offer,
        "eligible_for_loan": eligible_loan,
        "eligible_for_device_financing": eligible_device,
        "device_financing_offer": d_offer,
        "eligible_for_credit_card": eligible_cc,
        "credit_card_offer": cc_offer,
        **metrics,
    }
    return out
