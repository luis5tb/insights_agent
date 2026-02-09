"""FastAPI dependencies for authentication."""

import logging
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from insights_agent.auth.jwt import JWTValidationError, JWTValidator, get_jwt_validator
from insights_agent.auth.models import AuthenticatedUser

logger = logging.getLogger(__name__)

# HTTP Bearer authentication scheme
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    jwt_validator: Annotated[JWTValidator, Depends(get_jwt_validator)],
) -> AuthenticatedUser:
    """Extract and validate the current user from the request.

    This dependency extracts the Bearer token from the Authorization header,
    validates it using the JWT validator, and returns the authenticated user.

    Args:
        request: FastAPI request object
        credentials: HTTP Authorization credentials
        jwt_validator: JWT validator instance

    Returns:
        AuthenticatedUser with validated claims

    Raises:
        HTTPException: If authentication fails
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = await jwt_validator.validate_token(credentials.credentials)
        # Store the raw access token for forwarding to downstream services
        user.access_token = credentials.credentials
        # Store user in request state for access in other parts of the app
        request.state.user = user
        return user
    except JWTValidationError as e:
        logger.warning("JWT validation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def require_scope(
    required_scope: str,
) -> Callable[..., Coroutine[Any, Any, AuthenticatedUser]]:
    """Create a dependency that requires a specific scope.

    Args:
        required_scope: The scope that must be present in the token

    Returns:
        FastAPI dependency function
    """

    async def scope_checker(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        """Check if user has the required scope.

        Args:
            user: Authenticated user

        Returns:
            User if scope check passes

        Raises:
            HTTPException: If scope is not present
        """
        if required_scope not in user.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {required_scope}",
            )
        return user

    return scope_checker


# Type alias for common dependency pattern
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
