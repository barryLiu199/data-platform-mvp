"""Workflow State Machine — pure state transition logic.

No I/O, no HTTP, no DB. Just rules about which transitions are valid.
"""
from typing import Set

STATUS_DRAFT = "draft"
STATUS_TESTED = "tested"
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"

EDITABLE_STATUSES: Set[str] = {STATUS_DRAFT, STATUS_TESTED, STATUS_OFFLINE}
DELETABLE_STATUSES: Set[str] = {STATUS_DRAFT, STATUS_OFFLINE}

# Valid transitions: current_status -> set of allowed target statuses
_TRANSITIONS = {
    STATUS_DRAFT: {STATUS_TESTED},
    STATUS_TESTED: {STATUS_ONLINE, STATUS_DRAFT},
    STATUS_ONLINE: {STATUS_OFFLINE},
    STATUS_OFFLINE: {STATUS_TESTED, STATUS_ONLINE},
}


def can_transition(current: str, target: str) -> bool:
    """Check if a state transition is valid."""
    return target in _TRANSITIONS.get(current, set())


def validate_test(status: str) -> str | None:
    """Validate workflow can be tested. Returns error message or None."""
    if status not in {STATUS_DRAFT, STATUS_TESTED}:
        return f"状态 {status} 下不允许测试"
    return None


def validate_publish(status: str) -> str | None:
    """Validate workflow can be published. Returns error message or None."""
    if status != STATUS_TESTED:
        return f"只有 tested 状态可发布,当前 {status},请先测试"
    return None


def validate_offline(status: str) -> str | None:
    """Validate workflow can go offline. Returns error message or None."""
    if status != STATUS_ONLINE:
        return f"只有 online 状态可下线,当前 {status}"
    return None


def validate_run(status: str) -> str | None:
    """Validate workflow can be run. Returns error message or None."""
    if status not in {STATUS_ONLINE, STATUS_TESTED}:
        return f"状态 {status} 下不允许运行,需先测试/发布"
    return None


def validate_delete(status: str) -> str | None:
    """Validate workflow can be deleted. Returns error message or None."""
    if status not in DELETABLE_STATUSES:
        return f"工作流状态 {status},只有 draft/offline 状态允许删除;请先下线"
    return None


def validate_schedule_online(status: str) -> str | None:
    """Validate schedule can be turned on. Returns error message or None."""
    if status != STATUS_ONLINE:
        return "工作流需先发布上线才能开启调度"
    return None
