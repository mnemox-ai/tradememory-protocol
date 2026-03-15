"""Prospective memory: evaluate plan triggers and record outcomes.

Prospective memory is "remembering to do something in the future."
In trading, this means pre-planned actions (e.g., "if price breaks X, go long")
that get evaluated against live context and then scored after execution.
"""

from datetime import datetime, timezone


def evaluate_trigger(plan: dict, current_context: dict) -> bool:
    """Check whether a plan's trigger conditions are met by current context.

    Each condition in plan["conditions"] is a dict with:
        field: str — key to look up in current_context
        op: str — comparison operator ("gt", "lt", "gte", "lte", "eq")
        value: float|str — threshold value

    All conditions must be satisfied (AND logic).

    Args:
        plan: Dict with at least "conditions" key (list of condition dicts).
        current_context: Dict of current market/system state.

    Returns:
        True if ALL conditions are met, False otherwise.
    """
    conditions = plan.get("conditions", [])
    if not conditions:
        return False

    for cond in conditions:
        field = cond.get("field")
        op = cond.get("op")
        value = cond.get("value")

        if field is None or op is None or value is None:
            return False

        actual = current_context.get(field)
        if actual is None:
            return False

        if not _compare(actual, op, value):
            return False

    return True


def _compare(actual: float, op: str, value: float) -> bool:
    """Apply comparison operator."""
    if op == "gt":
        return actual > value
    elif op == "lt":
        return actual < value
    elif op == "gte":
        return actual >= value
    elif op == "lte":
        return actual <= value
    elif op == "eq":
        return actual == value
    else:
        raise ValueError(f"Unknown operator: {op}")


def record_outcome(plan: dict, actual_pnl: float) -> dict:
    """Write execution outcome back to a plan, returning the updated plan.

    Adds an "outcome" sub-dict with P&L, timestamp, and whether the plan
    was profitable. Does not mutate the original plan dict.

    Args:
        plan: The original plan dict.
        actual_pnl: Realized P&L from executing the plan.

    Returns:
        New dict = plan + outcome fields.
    """
    result = dict(plan)
    result["outcome"] = {
        "pnl": actual_pnl,
        "profitable": actual_pnl > 0,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    result["status"] = "completed"
    return result
