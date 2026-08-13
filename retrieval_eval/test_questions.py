"""
retrieval_eval/test_questions.py

Domain-specific test set for Torque Tune Auto Care's knowledge base
(company policy + supplier warranty terms + technical service bulletins +
diagnostic procedures). Nine questions across the three categories the
assignment asks for -- three per category, matching each retrieval
architecture's intended strength:

  - "naive"   : general/conceptual questions naive RAG should handle fine
                (no exact identifier needed, single relevant section).
  - "hybrid"  : questions naming an exact identifier (a TSB number, a WT
                code) that a small embedding can blur together with a
                lexically-similar-but-wrong chunk -- keyword matching wins.
  - "agentic" : multi-part questions that need two different sections
                (a procedure + the TSB/warranty section it points to)
                to answer completely -- needs a second retrieval hop.

`expected_keywords`: substrings that MUST all appear (case-insensitive) in
a correct final answer. This is the accuracy proxy run_eval.py checks --
crude but auditable, and good enough to compare architectures on the same
fixed test set.

Per the assignment's guardrail: this list is fixed once evaluation starts.
Do not edit questions/expected_keywords after runs begin -- add a new
question instead if a gap is found.
"""

TEST_QUESTIONS = [
    # ---------------- naive-friendly (general, single-hop) ----------------
    {
        "id": "N1",
        "category": "naive",
        "question": "What quantity counts as out of stock for a spare part?",
        "expected_keywords": ["quantity = 0", "out of stock"],
    },
    {
        "id": "N2",
        "category": "naive",
        "question": "Can a discontinued part be suggested as a valid alternative?",
        "expected_keywords": ["not discontinued"],
    },
    {
        "id": "N3",
        "category": "naive",
        "question": "Are cabin air filters returnable once the packaging is opened?",
        "expected_keywords": ["non-returnable"],
    },
    # ---------------- hybrid-friendly (exact identifiers) -----------------
    {
        "id": "H1",
        "category": "hybrid",
        "question": "What does TSB-2024-118 say?",
        "expected_keywords": ["slave cylinder"],
    },
    {
        "id": "H2",
        "category": "hybrid",
        "question": "What's the warranty window under WT-317?",
        "expected_keywords": ["90 days"],
    },
    {
        "id": "H3",
        "category": "hybrid",
        "question": "What does TSB-2022-118 say about alternators?",
        "expected_keywords": ["whine", "week 22"],
    },
    # ---------------- agentic-friendly (multi-hop) -------------------------
    {
        "id": "A1",
        "category": "agentic",
        "question": (
            "For a remanufactured Ironclad clutch kit with a soft clutch "
            "pedal, what's the likely cause and what warranty term applies "
            "to the replacement part?"
        ),
        "expected_keywords": ["slave cylinder", "12 month"],
    },
    {
        "id": "A2",
        "category": "agentic",
        "question": (
            "A customer's alternator whines at idle and it's a pre-week-22 "
            "2022 unit installed by a certified technician -- is this "
            "covered, and what's the fix?"
        ),
        "expected_keywords": ["replace", "warranty"],
    },
    {
        "id": "A3",
        "category": "agentic",
        "question": (
            "A car has a repeat brake noise complaint with the CS-3 caliper "
            "assembly and the pads are 4 months old -- what should be "
            "checked and is this covered under warranty?"
        ),
        "expected_keywords": ["slide pin", "6 months"],
    },
]
