import secrets
import string

import click

from shared.crypto import hash_token
from shared.db import (
    DEFAULT_ROLE,
    VALID_ROLES,
    delete_token_by_hash,
    get_token_role,
    init_db,
    list_token_records,
    save_token_hash,
)


def generate_random_token(length=32):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@click.group()
def cli():
    """API Token Management CLI."""
    init_db()


@cli.command()
@click.option(
    "--role",
    type=click.Choice(VALID_ROLES, case_sensitive=False),
    default=DEFAULT_ROLE,
    show_default=True,
    help="Application role assigned to the new token.",
)
def create(role):
    """Generate a new token and store its hash and role."""
    normalized_role = role.lower()
    token = generate_random_token()
    token_hash = hash_token(token)

    save_token_hash(token_hash, normalized_role)

    click.echo("New API Token created successfully.")
    click.echo(f"ROLE: {normalized_role}")
    click.echo(f"TOKEN: {token}")
    click.echo(
        "IMPORTANT: Save this token now. "
        "It cannot be recovered from the database."
    )


@cli.command()
@click.argument("token")
def verify(token):
    """Verify a token and display its application role."""
    token_hash = hash_token(token)
    role = get_token_role(token_hash)

    if role is None:
        click.echo("Token is INVALID.", err=True)
        raise click.exceptions.Exit(1)

    click.echo("Token is VALID.")
    click.echo(f"ROLE: {role}")


@cli.command()
@click.argument("token")
def delete(token):
    """Delete a token using the token itself."""
    token_hash = hash_token(token)
    delete_token_by_hash(token_hash)
    click.echo("Token deleted successfully.")


@cli.command(name="list")
def list_tokens():
    """List stored token hashes and their roles."""
    token_records = list_token_records()

    if not token_records:
        click.echo("No tokens found.")
        return

    click.echo("Stored API Tokens:")
    for token_hash, role in token_records:
        click.echo(f"- {token_hash} [{role}]")


if __name__ == "__main__":
    cli()
