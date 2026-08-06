from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from shared.crypto import hash_token
from shared.db import VALID_ROLES, get_token_role


@dataclass(frozen=True)
class AuthenticatedToken:
    """Authenticated application token information."""

    role: str


def authenticate_api_token(
    x_api_token: str = Header(..., alias="X-API-Token"),
) -> AuthenticatedToken:
    """Authenticate an application API token and return its role."""
    token_hash = hash_token(x_api_token)
    role = get_token_role(token_hash)

    if role is None:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing API Token",
        )

    return AuthenticatedToken(role=role)


def require_roles(*allowed_roles: str):
    """Create a FastAPI dependency that permits specific roles."""
    invalid_roles = set(allowed_roles) - set(VALID_ROLES)

    if invalid_roles:
        invalid_role_list = ", ".join(sorted(invalid_roles))
        raise ValueError(f"Unsupported authorization roles: {invalid_role_list}")

    allowed_role_set = frozenset(allowed_roles)

    def authorize(
        authenticated_token: AuthenticatedToken = Depends(
            authenticate_api_token
        ),
    ) -> AuthenticatedToken:
        if authenticated_token.role not in allowed_role_set:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions",
            )

        return authenticated_token

    return authorize
