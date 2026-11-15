"""Admin commands: `flask --app app users ...`."""

import click
from flask.cli import AppGroup
from sqlalchemy import select

from app.core.extensions import db
from app.users.models import PREMIUM_TIERS, Tier, User

users_cli = AppGroup("users", help="Manage user accounts.")


@users_cli.command("set-tier")
@click.argument("username")
@click.argument(
    "tier", type=click.Choice([tier.value for tier in Tier], case_sensitive=False)
)
def set_tier(username: str, tier: str) -> None:
    """Change a user's tier (Free, Premium or Admin).

    Example: flask --app app users set-tier alice premium
    """
    user = db.session.scalar(select(User).where(User.username == username))
    if user is None:
        raise click.ClickException(f"No user named '{username}'.")

    user.tier = Tier(tier)
    # tier is the source of truth; is_premium follows it.
    user.is_premium = user.tier in PREMIUM_TIERS
    db.session.commit()
    click.echo(f"{username}: tier={user.tier.value}, is_premium={user.is_premium}")
