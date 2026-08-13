"""
context_eval/transcripts.py

Fixed long-context test suite for comparing the four context-window
management strategies (context_eval/strategies.py).

The real failure mode this is testing: Torque Tune's longest live sessions
are diagnostic/service-writer calls where a customer states one fact early
(a warranty, a recall, a prior declined service, a usage detail that
changes the right part) and then the agent spends the rest of the call
making tool_call/tool_output round trips against the inventory system
(check_stock, suggest_alternative, generate_inventory_report-style lookups)
before a final question depends on that early fact. Message schema matches
mcp-server/memory/short_term_memory.py's Message (role/content/metadata),
kept as plain dicts here since these strategies run on a raw transcript,
not the live ShortTermMemory buffer.

Per the lab's cost note: input tokens are cheap, output tokens are what
burns budget -- so bulk here comes from large, realistic tool_output JSON
blobs (thousands of tokens per transcript), not from generated text.

Keep this file fixed once evaluation starts (run_eval.py results are only
comparable against a stable test suite).
"""
from typing import Any, Dict, List

Message = Dict[str, Any]

_PARTS = [
    "BRK-1042 brake pads", "OIL-220 synthetic oil filter", "ALT-556 alternator belt",
    "SPK-119 spark plug set", "RAD-330 radiator hose", "TIRE-880 all-season tire",
    "BAT-410 12V battery", "CLU-275 clutch kit", "WIP-091 wiper blades",
    "FUS-014 fuse box", "SEN-207 O2 sensor", "PMP-063 water pump",
    "HOS-141 fuel hose", "GSK-018 head gasket", "BLB-332 headlight bulb set",
]


def _filler_tool_turns(n_pairs: int, seed: int = 0) -> List[Message]:
    """Realistic bulky check_stock / suggest_alternative round trips that
    bury whatever came before them under tool JSON, not dialogue."""
    msgs: List[Message] = []
    for i in range(n_pairs):
        part = _PARTS[(seed + i) % len(_PARTS)]
        tool = "check_stock" if i % 3 else "suggest_alternative"
        msgs.append({
            "role": "tool_call",
            "content": f'{tool}(part_name="{part}")',
            "metadata": {"tool": tool},
        })
        msgs.append({
            "role": "tool_output",
            "content": (
                f'{{"part": "{part}", "quantity_on_hand": {17 + (seed + i) % 40}, '
                f'"warehouse": "Bay {1 + i % 4}", "reorder_threshold": 10, '
                f'"last_restock": "2026-0{1 + i % 7}-1{i % 9}", '
                f'"supplier": "NorthStar Auto Supply", '
                f'"unit_cost": {9.5 + i * 0.35:.2f}, "bin_location": "R{i % 9}-S{i % 5}", '
                f'"alternatives": ["{_PARTS[(seed + i + 1) % len(_PARTS)]}", '
                f'"{_PARTS[(seed + i + 2) % len(_PARTS)]}"], '
                f'"notes": "routine lookup, no action needed"}}'
            ),
            "metadata": {"tool": tool},
        })
    return msgs


def _build(id_: str, title: str, critical_msg: str, n_pairs: int,
           final_question: str, expected_keywords: List[str], seed: int = 0) -> Dict[str, Any]:
    messages: List[Message] = [
        {"role": "user", "content": "Hi, bringing in a 2019 Ford F-150 for a brake inspection.", "metadata": None},
        {"role": "assistant", "content": "Got it, pulling up the vehicle and service record now.", "metadata": None},
        {"role": "user", "content": critical_msg, "metadata": None},
        {"role": "assistant", "content": "Understood, noted on the ticket. Let me check parts availability.", "metadata": None},
    ]
    messages += _filler_tool_turns(n_pairs, seed=seed)
    messages.append({"role": "user", "content": final_question, "metadata": None})
    return {
        "id": id_,
        "title": title,
        "messages": messages,
        "final_question": final_question,
        "expected_keywords": expected_keywords,
    }


TRANSCRIPTS: List[Dict[str, Any]] = [
    _build(
        id_="T1",
        title="Warranty claim buried under stock checks",
        critical_msg=(
            "Actually, this brake caliper was replaced two months ago and it's "
            "still under warranty -- please don't charge me for the part again."
        ),
        n_pairs=18,
        final_question="The caliper is ready to install -- do we bill the customer for the part, or is it covered?",
        expected_keywords=["warranty"],
        seed=0,
    ),
    _build(
        id_="T2",
        title="Usage detail (towing) changes the right part",
        critical_msg=(
            "Just so you know, this truck is used daily for towing a construction "
            "trailer, so please go with the heavy-duty brake pads, not the standard ones."
        ),
        n_pairs=16,
        final_question="Which brake pad option should we install for this truck?",
        expected_keywords=["heavy-duty"],
        seed=3,
    ),
    _build(
        id_="T3",
        title="Safety recall buried under diagnostic noise",
        critical_msg=(
            "One more thing -- we got a manufacturer recall notice for this VIN "
            "about the airbag sensor, so please check if that's been addressed "
            "before you touch anything else."
        ),
        n_pairs=20,
        final_question="Before we release the vehicle to the customer, is there anything outstanding we need to flag?",
        expected_keywords=["recall"],
        seed=6,
    ),
    _build(
        id_="T4",
        title="Previously declined service, must not be re-added silently",
        critical_msg=(
            "Last time I was here I declined the coolant flush because of the "
            "price -- please ask me first before doing it again."
        ),
        n_pairs=14,
        final_question="While the car is up on the lift, should we go ahead and add the coolant flush to today's service?",
        expected_keywords=["declined"],
        seed=9,
    ),
    _build(
        id_="T5",
        title="Unflagged preference (no compliance/financial keyword to key off)",
        critical_msg=(
            "Also, quick heads up before you get started. My daughter's allergic "
            "to the pine air freshener you usually use after service, so please "
            "skip that this time."
        ),
        n_pairs=17,
        final_question="Anything special we should do or avoid before handing the car back?",
        expected_keywords=["allergic"],
        seed=2,
    ),
]
