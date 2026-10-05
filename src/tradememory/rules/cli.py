"""`tradememory rules ...`: see, approve and retire rules learned from your history."""

from __future__ import annotations

import click

RULES_OPTION = click.option(
    "--rules", "rules_file", default=None, help="Rules file (default ~/.tradememory/rules.json)."
)


def _path(rules_file: str | None):
    from pathlib import Path

    from .store import DEFAULT_RULES_PATH

    return Path(rules_file).expanduser() if rules_file else DEFAULT_RULES_PATH


@click.group()
def rules() -> None:
    """Rules suggested from your own trade history. None is enforced until you approve it."""


@rules.command("list")
@RULES_OPTION
@click.option("--all", "show_all", is_flag=True, help="Include retired rules.")
def rules_list(rules_file: str | None, show_all: bool) -> None:
    """Every proposed and active rule, with the history behind it."""
    from .store import RulesError, load_rules
    from .suggest import describe_evidence, describe_rule

    path = _path(rules_file)
    try:
        found = load_rules(path)
    except RulesError as exc:
        raise click.ClickException(f"{exc}\nThe brake refuses every order until this is fixed.") from exc
    shown = [r for r in found if show_all or r["status"] != "retired"]
    if not shown:
        click.echo(f"no rules in {path}. `tradememory sync ...` suggests one when your history calls for it.")
        return
    for r in shown:
        click.echo(f"{r['id']}  [{r['status']}]  {describe_rule(r)}")
        click.echo(f"    {describe_evidence(r)}")
        if r["status"] == "active":
            click.echo(f"    approved {r['approved_at']}")


@rules.command("approve")
@click.argument("rule_id")
@RULES_OPTION
@click.option("--max-notional", default=None, help="Your own limit instead of the suggested one (whole account currency).")
@click.option("--action", type=click.Choice(["escalate", "deny"]), default=None,
              help="escalate holds the order for your approval (default); deny refuses it.")
def rules_approve(rule_id: str, rules_file: str | None, max_notional: str | None, action: str | None) -> None:
    """Turn a proposed rule on. The running brake enforces it from its next order."""
    from .store import RulesError, approve
    from .suggest import describe_rule

    try:
        rule = approve(rule_id, path=_path(rules_file), max_notional=max_notional, action=action)
    except (KeyError, ValueError, RulesError) as exc:
        raise click.ClickException(str(exc).strip("'")) from exc
    click.echo(f"active: {rule['id']}  {describe_rule(rule)}")
    click.echo("It counts closed trades the brake knows about; run `tradememory sync alpaca --db <brake db>` "
               "after trades close so it sees them.")


@rules.command("retire")
@click.argument("rule_id")
@RULES_OPTION
def rules_retire(rule_id: str, rules_file: str | None) -> None:
    """Turn a rule off. It stays in the file as a record."""
    from .store import RulesError, retire

    try:
        rule = retire(rule_id, path=_path(rules_file))
    except (KeyError, ValueError, RulesError) as exc:
        raise click.ClickException(str(exc).strip("'")) from exc
    click.echo(f"retired: {rule['id']}")
