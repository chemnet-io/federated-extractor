import click
import secrets
import string
from shared.db import save_token_hash, verify_token_hash, delete_token_by_hash, list_token_hashes
from shared.crypto import hash_token

def generate_random_token(length=32):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

@click.group()
def cli():
    """API Token Management CLI"""
    pass

@cli.command()
def create():
    """Generate a new token and store its hash"""
    token = generate_random_token()
    token_hash = hash_token(token)
    save_token_hash(token_hash)
    click.echo("New API Token created successfully.")
    click.echo(f"TOKEN: {token}")
    click.echo("IMPORTANT: Save this token now. It cannot be recovered from the database.")

@cli.command()
@click.argument("token")
def verify(token):
    """Verify if a token is valid"""
    token_hash = hash_token(token)
    if verify_token_hash(token_hash):
        click.echo("Token is VALID.")
    else:
        click.echo("Token is INVALID.", err=True)

@cli.command()
@click.argument("token")
def delete(token):
    """Delete a token using the token itself"""
    token_hash = hash_token(token)
    delete_token_by_hash(token_hash)
    click.echo("Token deleted successfully.")

@cli.command()
def list():
    """List all stored token hashes (non-reversible)"""
    hashes = list_token_hashes()
    if hashes:
        click.echo("Stored Token Hashes:")
        for h in hashes:
            click.echo(f"- {h}")
    else:
        click.echo("No tokens found.")

if __name__ == "__main__":
    cli()
