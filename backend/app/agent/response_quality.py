from __future__ import annotations

from dataclasses import dataclass
import re

from app.agent.state import CustomerAgentState, append_event


@dataclass(frozen=True)
class ResponseQualityIssue:
    code: str
    message: str


_RAW_ERROR = re.compile(r"(?:\bError\b|\b[A-Za-z]+Error\b|Traceback)", re.IGNORECASE)
_TOOL_NAME = re.compile(
    r"\b(?:get|find|list|cancel|modify|return|exchange)_[a-z0-9_]+\b"
)
_RAW_STATUS = re.compile(
    r"\b(?:pending|delivered|cancelled|canceled|shipped|processed|returned|exchanged)\b",
    re.IGNORECASE,
)
_NEXT_STEP = re.compile(
    r"(?:[？?]|您可以|您希望|请选择|请提供|请稍后|可以继续|可以转接|需要我|请确认)"
)


def inspect_customer_response(text: str) -> list[ResponseQualityIssue]:
    issues: list[ResponseQualityIssue] = []
    if _RAW_ERROR.search(text):
        issues.append(ResponseQualityIssue("raw_error", "回答暴露了原始异常信息"))
    if _TOOL_NAME.search(text):
        issues.append(ResponseQualityIssue("internal_tool_name", "回答暴露了内部工具名称"))
    if _RAW_STATUS.search(text):
        issues.append(ResponseQualityIssue("untranslated_status", "订单状态未转换为客户可读中文"))
    if text.strip() and not _NEXT_STEP.search(text):
        issues.append(ResponseQualityIssue("missing_next_step", "回答缺少明确的下一步"))
    return issues


def append_response_quality_event(
    state: CustomerAgentState,
    text: str,
    *,
    source: str,
) -> CustomerAgentState:
    issues = inspect_customer_response(text)
    policy_hits = []
    for event in reversed(state.events):
        if event.event_type == "rag.completed":
            policy_hits = event.payload.get("hits") or []
            break
        if event.event_type == "rag.degraded":
            break
    return append_event(
        state,
        "response.quality_checked",
        {
            "source": source,
            "passed": not issues,
            "issue_codes": [issue.code for issue in issues],
            "policy_evidence_available": bool(policy_hits),
            "policy_evidence_count": len(policy_hits),
        },
    )
