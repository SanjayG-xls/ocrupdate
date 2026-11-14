"""Flag content for human comparison. Never silently change scientific text."""
import re
from ..formula_engine import FORMULAS, normalise_quantity_names
from ..quantity_parser import UNIT_ALIASES, UNITS


def inspect_text(text, words=(), threshold=70):
    warnings = [f"Low OCR confidence: {w['text']} ({w['confidence']:.0f}); compare with photo."
                for w in words if w['confidence'] < threshold]
    formulas = []
    for line in re.split(r'[\n;]|(?<=[.!?])\s+', text):
        if re.search(r'[=+×÷/*^²³−-]|\\(?:frac|sqrt)|[∫∑√]', line):
            expression = line.strip()
            if not expression:
                continue
            status = 'unsupported; manual review'
            normalized = normalise_quantity_names(expression).lower()
            for formula in FORMULAS.values():
                pattern = rf'\b{formula.output}\s*=\s*{formula.numerator}\s*([×÷/*+−-])\s*{formula.denominator}\b'
                match = re.search(pattern, normalized)
                if match:
                    status = 'matches supported ratio; verify symbols in photo' if match[1] in ('/', '÷') else f'CONFLICT: supported formula is {formula.text}'
                    if 'CONFLICT' in status:
                        warnings.append(status)
                    break
            formulas.append({'text': expression, 'status': status})
    numbers = [{'text': m[0], 'start': m.start(), 'end': m.end()} for m in re.finditer(r'(?<!\w)[+-]?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?', text)]
    units = []
    known = set(UNIT_ALIASES) | set(UNITS) | {'Ω', 'm/s²', 'm/s2'}
    for malformed in re.finditer(r'\b[A-Za-z]+/{2,}[A-Za-z0-9²³]+', text):
        warnings.append(f'Suspicious unit or fraction: {malformed[0]}; compare with photo.')
    for m in re.finditer(r'(?<!\w)(?:[A-Za-zΩ]+(?:[/^][A-Za-z0-9²³]+)*[²³]?)(?!\w)', text):
        token = m[0]
        after_number = bool(re.search(r'\d\s*$', text[:m.start()]))
        if token in known or after_number or '/' in token:
            status = 'verify unit' if token in known or token.lower() in known else 'unfamiliar or malformed unit; review (not necessarily incorrect)'
            units.append({'text': token, 'start': m.start(), 'end': m.end(), 'status': status})
    if formulas or numbers or units:
        warnings.append('Compare all formulas, numbers and units with the photo, including high-confidence words.')
    return dict(warnings=warnings, formula_candidates=formulas, numeric_candidates=numbers, unit_candidates=units, review_required=True)
