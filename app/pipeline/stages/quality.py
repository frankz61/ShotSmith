from app.core.config import settings


def run(cutout_path: str, items: list[dict], fidelity, storage) -> None:
    for it in items:
        raw = it["gen_params"].get("bbox")
        bbox = tuple(raw) if raw else None
        score = fidelity.score(cutout_path, str(storage.abs(it["path"])), bbox)
        it["fidelity_score"] = round(float(score), 3)
        it["qc_status"] = "passed" if score >= settings.fidelity_threshold else "needs_review"
