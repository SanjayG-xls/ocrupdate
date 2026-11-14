"""Adaptive routing (report p.3, rules R1-R4) and the session engine.

R1  placement score 0-1 -> L1, 2 -> L2, 3 -> L3.
R2  a wrong answer -> concept Fragile -> repair and ONE second-chance item.
R3  climb one rung when every item at the rung is Provisional or Repaired.
    Two unresolved errors at a rung step the learner down one rung (at L1: Safety Net
    and a teacher note). Interpretation for the cases the report leaves open (documented
    in docs/ARCHITECTURE.md): one unresolved error -> Safety Net + teacher note and the
    session ends at that rung (R3 not satisfied, so no climb); after a step-down to a rung
    whose items were already delivered, the session ends with a teacher note.
R4  after the L3 items, the bridge check (Transfer item on the unmodified extract).

Explanation support (rung) and cognitive level are independent: the rung is a property
of the schedule; the cognitive level is a property of the item.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional

from .bridge_check import build_bridge
from .concept_states import ConceptTracker, State
from .explanation_generator import Explanation
from .key_term_registry import KeyTermRegistry
from .misconception_detector import Evaluation, evaluate
from .passage_processor import Passage
from .placement import place
from .question_generator import Item, ItemBank
from .repair_engine import RepairEngine
from .scoring import ScoreLedger

log = logging.getLogger("level_bridge.router")


@dataclass
class Response:
    answer: str
    certainty: int


AnswerProvider = Callable[[Item, Dict[str, object]], Response]


@dataclass
class SessionResult:
    placement: Dict[str, object]
    events: List[Dict[str, object]]
    rung_path: List[int]
    end_reason: str
    bridge_reached: bool
    teacher_notes: List[str]
    repair_latencies_s: List[float]
    delivered_items: List[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class Session:
    """Runs one learning session over a validated item bank."""

    def __init__(self, passage: Passage, bank: ItemBank, explanations: Dict[str, Explanation],
                 tracker: ConceptTracker, ledger: ScoreLedger, repair: RepairEngine, registry: KeyTermRegistry,
                 placement_rule: Dict[int, int], step_down_n: int = 2, safety_net_enabled: bool = True) -> None:
        self.passage, self.bank, self.explanations = passage, bank, explanations
        self.tracker, self.ledger, self.repair, self.registry = tracker, ledger, repair, registry
        self.placement_rule, self.step_down_n, self.safety_net_enabled = placement_rule, step_down_n, safety_net_enabled
        self.events: List[Dict[str, object]] = []
        self.delivered: List[str] = []
        self.teacher_notes: List[str] = []
        self.repair_latencies: List[float] = []
        self.on_event: Optional[Callable[[Dict[str, object]], None]] = None   # live display (interactive mode)

    # ------------------------------------------------------------------ helpers
    def _emit(self, type_: str, **data) -> None:
        ev = {"type": type_, **data}
        self.events.append(ev)
        if self.on_event is not None:
            self.on_event(ev)
        log.info("event %s", type_, extra={"data": data})

    def _ask(self, item: Item, provider: AnswerProvider, context: Dict[str, object]) -> (Response, Evaluation):
        resp = provider(item, context)
        if resp.certainty not in (1, 2, 3):
            raise ValueError(f"certainty must be 1-3, got {resp.certainty}")
        ev = evaluate(item, resp.answer)
        self.delivered.append(item.item_id)
        return resp, ev

    def _first_event(self, cid: str, correct: bool) -> str:
        st = self.tracker.states[cid]
        if st == State.LEARNING:
            return "correct_first" if correct else "wrong_first"
        if correct:
            return ""  # consistent with an earlier result; no transition
        return "" if st == State.FRAGILE else "wrong"

    # ------------------------------------------------------------------ phases
    def run_placement(self, provider: AnswerProvider) -> int:
        responses = []
        for it in self.bank.of_kind("placement"):
            resp, ev = self._ask(it, provider, {"phase": "placement"})
            responses.append({"item_id": it.item_id, "probe": it.probe_type, "correct": ev.correct, "answer": resp.answer})
            self._emit("placement_item", item=it.item_id, probe=it.probe_type, stem=it.stem, correct=ev.correct,
                       answer=resp.answer)
        pr = place(responses, self.placement_rule)
        self.placement = pr.to_dict()
        self._emit("placement_result", score=pr.score, out_of=pr.out_of, start_rung=pr.start_rung)
        return pr.start_rung

    def _assess(self, item: Item, provider: AnswerProvider, rung: int) -> bool:
        """Deliver one assessment item (with repair + second chance if wrong). Returns True if resolved."""
        resp, ev = self._ask(item, provider, {"phase": "assessment", "rung": rung})
        entry = self.ledger.record_assessment(item.item_id, item.kind, item.cognitive_level, ev.correct, resp.certainty)
        evt = self._first_event(item.concept_id, ev.correct)
        new_state = self.tracker.apply(item.concept_id, evt, item.item_id) if evt else self.tracker.states[item.concept_id]
        if ev.correct and resp.certainty == 1:
            self.tracker.flag(item.concept_id, f"low certainty on {item.item_id}: reread {', '.join(item.source_sids)}")
        self._emit("item", item=item.item_id, rung=rung, level=item.cognitive_level, ktype=item.knowledge_type,
                   concept=item.concept_id, stem=item.stem, options=[(o.key, o.text) for o in item.options],
                   response_type=item.response_type, answer=resp.answer, certainty=resp.certainty,
                   correct=ev.correct, error_code=ev.error_code, message=ev.message, state=new_state.value,
                   credits=entry.assessment_credits, cbm=entry.cbm)
        if ev.correct:
            return True
        # R2: repair + one second chance
        t0 = time.perf_counter()
        rep = self.repair.repair(item, ev)
        sc = self.bank.second_chance_for(item.item_id)
        self.repair_latencies.append(time.perf_counter() - t0)
        self._emit("repair", item=item.item_id, error_code=ev.error_code, lines=rep.lines, source=rep.source,
                   latency_s=round(self.repair_latencies[-1], 4))
        if sc is None:
            self.tracker.flag(item.concept_id, f"no second-chance item for {item.item_id}")
            return False
        resp2, ev2 = self._ask(sc, provider, {"phase": "second_chance", "rung": rung})
        e2 = self.ledger.record_second_chance(sc.item_id, sc.cognitive_level, ev2.correct, resp2.certainty)
        state2 = self.tracker.apply(item.concept_id, "second_chance_correct" if ev2.correct else "second_chance_wrong", sc.item_id)
        self._emit("second_chance", item=sc.item_id, parent=item.item_id, stem=sc.stem,
                   options=[(o.key, o.text) for o in sc.options], response_type=sc.response_type,
                   answer=resp2.answer, certainty=resp2.certainty, correct=ev2.correct, error_code=ev2.error_code,
                   message=ev2.message, state=state2.value, recovery=e2.recovery_credits, cbm=e2.cbm)
        if not ev2.correct:
            self._safety_net(item.concept_id)
        return ev2.correct

    def _safety_net(self, cid: str) -> None:
        if not self.safety_net_enabled:
            return
        sn = self.repair.safety_net(cid)
        note = f"Teacher note: {cid} ({self.repair.km.concept(cid).label}) unresolved after repair and second chance."
        self.teacher_notes.append(note)
        self._emit("safety_net", concept=cid, word_card=sn.word_card, worked_example=sn.worked_example,
                   extensions_not_implemented=sn.extensions_not_implemented, teacher_note=note)

    def run(self, provider: AnswerProvider) -> SessionResult:
        rung = self.run_placement(provider)
        path = [rung]
        end_reason = ""
        bridge_reached = False
        visited_complete = set()
        while True:
            self._emit("explain", rung=rung, source=self.explanations[f"l{rung}"].source,
                       text=self.explanations[f"l{rung}"].text)
            pending = [it for it in self.bank.for_rung(rung) if it.item_id not in self.delivered]
            if not pending and rung in visited_complete:
                end_reason = f"returned to L{rung} after a step-down; its items were already delivered - teacher note"
                self.teacher_notes.append(f"Teacher note: learner needs support at L{rung} beyond this session.")
                self._emit("route", rule="R3", decision="end", rung=rung, reason=end_reason)
                break
            unresolved = 0
            for it in pending:
                if not self._assess(it, provider, rung):
                    unresolved += 1
            visited_complete.add(rung)
            if unresolved == 0:
                if rung < 3:
                    self._emit("route", rule="R3", decision="climb", from_rung=rung, to_rung=rung + 1,
                               reason=f"all L{rung} items resolved")
                    rung += 1
                    path.append(rung)
                    continue
                self._emit("route", rule="R4", decision="bridge", rung=3, reason="L3 items resolved")
                bridge_reached = True
                break
            if unresolved >= self.step_down_n:
                if rung > 1:
                    self._emit("route", rule="R3", decision="step_down", from_rung=rung, to_rung=rung - 1,
                               reason=f"{unresolved} unresolved errors at L{rung}")
                    rung -= 1
                    path.append(rung)
                    continue
                end_reason = f"{unresolved} unresolved errors at L1 - Safety Net and teacher note"
                self._emit("route", rule="R3", decision="end", rung=1, reason=end_reason)
                break
            end_reason = f"{unresolved} unresolved error at L{rung} - cannot climb (R3); Safety Net and teacher note"
            self._emit("route", rule="R3", decision="end", rung=rung, reason=end_reason)
            break
        if bridge_reached:
            self._bridge(provider)
            end_reason = "bridge check completed"
        return SessionResult(getattr(self, "placement", {}), self.events, path, end_reason, bridge_reached,
                             self.teacher_notes, self.repair_latencies, self.delivered)

    def _bridge(self, provider: AnswerProvider) -> None:
        transfers = self.bank.of_kind("transfer")
        if not transfers:
            self._emit("bridge", available=False)
            return
        t = transfers[0]
        br = build_bridge(self.passage, t, self.registry)
        self._emit("bridge", available=True, extract_sids=br.extract_sids, extract=br.extract, verbatim=br.verbatim,
                   glosses=br.glosses, note=br.note)
        resp, ev = self._ask(t, provider, {"phase": "bridge", "rung": 3})
        entry = self.ledger.record_assessment(t.item_id, "transfer", t.cognitive_level, ev.correct, resp.certainty)
        cid = t.concept_id
        st = self.tracker.states[cid]
        if st == State.LEARNING:
            evt = "correct_first" if ev.correct else "wrong_first"
            self.tracker.flag(cid, "transfer item was the first assessment of this concept")
        elif st == State.FRAGILE:
            evt = ""
        else:
            evt = "transfer_correct" if ev.correct else "transfer_wrong"
        new = self.tracker.apply(cid, evt, t.item_id) if evt else self.tracker.states[cid]
        self._emit("item", item=t.item_id, rung=3, level=t.cognitive_level, ktype=t.knowledge_type, concept=cid,
                   stem=t.stem, options=[], response_type=t.response_type, answer=resp.answer, certainty=resp.certainty,
                   correct=ev.correct, error_code=ev.error_code, message=ev.message, state=new.value,
                   credits=entry.assessment_credits, cbm=entry.cbm, bridge=True)
        if not ev.correct:
            rep = self.repair.repair(t, ev)
            self._emit("repair", item=t.item_id, error_code=ev.error_code, lines=rep.lines, source=rep.source,
                       latency_s=round(rep.latency_s, 4))
