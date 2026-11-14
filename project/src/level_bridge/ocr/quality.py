"""Heuristic quality indicators, not scientific correctness probabilities."""


def image_warnings(gray):
    import cv2
    warnings = []
    if gray.mean() < 65:
        warnings.append('Low light: improve illumination and retake if necessary.')
    if cv2.Laplacian(gray, cv2.CV_64F).var() < 45:
        warnings.append('Low detail or blur: check focus and empty page regions.')
    return warnings


def candidate_score(words):
    if not words:
        return -1
    # Reward useful coverage as well as confidence, so one isolated word does not win.
    return sum(max(0, w['confidence']) * min(len(w['text']), 12) for w in words) / sum(min(len(w['text']), 12) for w in words) + min(len(words), 100) * .15
