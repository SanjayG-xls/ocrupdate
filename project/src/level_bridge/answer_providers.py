"""Answer providers: scripted (tests / reproducible demo) and interactive (live learner).

Scripted answers are written by *intent*, never by hard-coded option letter, because
option order is produced by the question generator::

    {"Q1": {"select": "correct", "certainty": 3},
     "Q2": {"value": "540 km/h", "certainty": 3},
     "P2": {"select": "error:term_confusion", "certainty": 2},
     "P3": {"select": "text:Ravi", "certainty": 1}}

``select`` forms: ``correct`` | ``error:<code>`` (first option with that error code) |
``text:<option text>`` | ``letter:<A-D>``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, Optional

from .adaptive_router import Response
from .question_generator import Item


class ScriptError(KeyError):
    """The script has no usable answer for an item that the session delivered."""


def resolve_answer(item: Item, spec: Dict[str, object]) -> str:
    if item.response_type == "numeric":
        if "value" not in spec:
            raise ScriptError(f"{item.item_id}: numeric item needs 'value'")
        return str(spec["value"])
    sel = str(spec.get("select", ""))
    if sel == "correct":
        opt = item.correct_option()
    elif sel.startswith("error:"):
        opt = next((o for o in item.options if o.error_code == sel[6:]), None)
    elif sel.startswith("text:"):
        opt = next((o for o in item.options if o.text.lower() == sel[5:].lower()), None)
    elif sel.startswith("letter:"):
        opt = next((o for o in item.options if o.key == sel[7:].upper()), None)
    else:
        raise ScriptError(f"{item.item_id}: unknown select '{sel}'")
    if opt is None:
        raise ScriptError(f"{item.item_id}: no option matches '{sel}'")
    return opt.key


def scripted_provider(script: Dict[str, Dict[str, object]]) -> Callable[[Item, Dict[str, object]], Response]:
    def provide(item: Item, context: Dict[str, object]) -> Response:
        if item.item_id not in script:
            raise ScriptError(f"script has no answer for delivered item {item.item_id}")
        spec = script[item.item_id]
        return Response(resolve_answer(item, spec), int(spec.get("certainty", 2)))
    return provide


def load_script(path: Path) -> Dict[str, Dict[str, object]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("answers", data)


def interactive_provider(input_fn: Callable[[str], str] = input,
                         print_fn: Callable[[str], None] = print) -> Callable[[Item, Dict[str, object]], Response]:
    """Ask the learner in the terminal. Placement items do not ask for certainty (fixed 2, unscored)."""

    def provide(item: Item, context: Dict[str, object]) -> Response:
        print_fn("")
        print_fn(f"[{item.item_id}] {item.stem}")
        for o in item.options:
            print_fn(f"   {o.key}) {o.text}")
        valid = {o.key for o in item.options}
        while True:
            hint = "letter" if item.options else "number with unit, e.g. 12 km/h"
            ans = input_fn(f"Your answer ({hint}): ").strip()
            if not item.options and ans:
                break
            if ans[:1].upper() in valid:
                ans = ans[:1].upper()
                break
            print_fn("   Please enter one of " + ", ".join(sorted(valid)))
        if context.get("phase") == "placement":
            return Response(ans, 2)
        while True:
            c = input_fn("How sure are you? 1 = guess, 2 = fairly sure, 3 = certain: ").strip()
            if c in ("1", "2", "3"):
                return Response(ans, int(c))
    return provide
