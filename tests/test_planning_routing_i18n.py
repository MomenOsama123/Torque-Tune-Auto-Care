"""
tests/test_planning_routing_i18n.py

Task 2 regression tests: is_planning_request() must route both English
and Arabic repair-fulfillment requests to the Planning Agent, while
normal (non-planning) questions in either language keep going to the
existing Memory/RAG path.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from client import is_planning_request  # noqa: E402  (agent/client.py)


def test_english_planning_request_is_detected():
    request = "We need spare parts for this repair job, the Brake Pad is out of stock."
    assert is_planning_request(request) is True


def test_arabic_planning_request_is_detected():
    request = "محتاجين نجهز قطع غيار للفرامل، القطعة غير متوفر في المخزون."
    assert is_planning_request(request) is True


def test_normal_english_question_is_not_planning():
    request = "What's the recommended oil change interval for a sedan?"
    assert is_planning_request(request) is False


def test_normal_arabic_question_is_not_planning():
    request = "إيه أفضل نوع زيت للسيارة في الصيف؟"
    assert is_planning_request(request) is False
