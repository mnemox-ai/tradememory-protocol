"""Rules learned from a trader's own history, enforced by the broker brake.

A rule starts as a suggestion drawn from descriptive statistics of closed
trades (`tradememory sync ...`). It does nothing until the owner approves it
(`tradememory rules approve`). An approved rule only ever tightens what the
brake allows: it can hold an order for the owner's approval or refuse it,
never let through something the policy refused.
"""
