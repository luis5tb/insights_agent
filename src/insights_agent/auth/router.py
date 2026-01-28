"""FastAPI router for OAuth 2.0 endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from insights_agent.auth.models import OAuthError, TokenResponse
from insights_agent.auth.oauth import OAuthClient, get_oauth_client
from insights_agent.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["OAuth 2.0"])


# In-memory state storage (should use Redis in production)
# This is a simple dict to store state -> expected_redirect_uri mappings
_pending_states: dict[str, dict[str, str | None]] = {}


@router.get("/authorize")
async def authorize(
    oauth_client: Annotated[OAuthClient, Depends(get_oauth_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    response_type: Annotated[str, Query()] = "code",
    client_id: Annotated[str | None, Query()] = None,
    redirect_uri: Annotated[str | None, Query()] = None,
    scope: Annotated[str, Query()] = "openid profile email",
    state: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Initiate OAuth 2.0 Authorization Code flow.

    This endpoint redirects the user to Red Hat SSO for authentication.
    After successful authentication, the user is redirected back to the
    callback endpoint with an authorization code.

    Args:
        response_type: Must be "code" for authorization code flow
        client_id: Optional client ID (uses configured default)
        redirect_uri: Optional redirect URI (uses configured default)
        scope: OAuth scopes to request
        state: State parameter for CSRF protection

    Returns:
        Redirect response to Red Hat SSO authorization endpoint
    """
    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 'code' response_type is supported",
        )

    # Generate state if not provided
    auth_state = state or oauth_client.generate_state()

    # Store state for validation in callback
    _pending_states[auth_state] = {
        "redirect_uri": redirect_uri or oauth_client.redirect_uri,
        "client_id": client_id or oauth_client.client_id,
    }

    # Build authorization URL and redirect
    auth_url = oauth_client.build_authorization_url(
        state=auth_state,
        scope=scope,
        redirect_uri=redirect_uri,
    )

    logger.info("Redirecting to authorization endpoint with state: %s...", auth_state[:8])
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def callback(
    request: Request,
    oauth_client: Annotated[OAuthClient, Depends(get_oauth_client)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
) -> TokenResponse:
    """Handle OAuth 2.0 authorization callback.

    This endpoint receives the authorization code from Red Hat SSO after
    successful authentication, exchanges it for tokens, and returns the
    token response.

    Args:
        request: FastAPI request object
        code: Authorization code from Red Hat SSO
        state: State parameter for CSRF validation
        error: Error code if authorization failed
        error_description: Error description if authorization failed
        oauth_client: OAuth client instance

    Returns:
        Token response with access token, refresh token, etc.

    Raises:
        HTTPException: If authorization failed or state validation fails
    """
    # Handle error response from IdP
    if error:
        logger.warning("Authorization error from IdP: %s - %s", error, error_description)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=OAuthError(
                error=error,
                error_description=error_description,
            ).model_dump(),
        )

    # Validate authorization code is present
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code",
        )

    # Validate state parameter
    if not state or state not in _pending_states:
        logger.warning("Invalid or missing state parameter")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing state parameter",
        )

    # Get stored state data and remove it (one-time use)
    state_data = _pending_states.pop(state)
    redirect_uri = state_data.get("redirect_uri")

    # Exchange code for tokens
    result = await oauth_client.exchange_code(code=code, redirect_uri=redirect_uri)

    if isinstance(result, OAuthError):
        logger.error("Token exchange failed: %s", result.error_description)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.model_dump(),
        )

    logger.info("Successfully exchanged authorization code for tokens")
    return result


@router.post("/token")
async def token(
    grant_type: Annotated[str, Form()],
    oauth_client: Annotated[OAuthClient, Depends(get_oauth_client)],
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
) -> TokenResponse:
    """OAuth 2.0 token endpoint.

    This endpoint handles token requests including:
    - authorization_code: Exchange authorization code for tokens
    - refresh_token: Refresh an expired access token

    Args:
        grant_type: The grant type (authorization_code or refresh_token)
        code: Authorization code (for authorization_code grant)
        redirect_uri: Redirect URI (for authorization_code grant)
        refresh_token: Refresh token (for refresh_token grant)
        client_id: Client ID (optional, uses configured default)
        client_secret: Client secret (optional, uses configured default)
        oauth_client: OAuth client instance

    Returns:
        Token response with access token, refresh token, etc.

    Raises:
        HTTPException: If token request fails
    """
    if grant_type == "authorization_code":
        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing authorization code",
            )

        result = await oauth_client.exchange_code(
            code=code,
            redirect_uri=redirect_uri,
        )

    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing refresh token",
            )

        result = await oauth_client.refresh_token(refresh_token)

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported grant type: {grant_type}",
        )

    if isinstance(result, OAuthError):
        logger.error("Token request failed: %s - %s", result.error, result.error_description)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.model_dump(),
        )

    return result


@router.get("/userinfo")
async def userinfo(
    request: Request,
    oauth_client: Annotated[OAuthClient, Depends(get_oauth_client)],
) -> dict[str, str]:
    """Get user information using the access token.

    This endpoint fetches user information from Red Hat SSO's userinfo endpoint.
    The access token must be provided in the Authorization header.

    Args:
        request: FastAPI request object
        oauth_client: OAuth client instance

    Returns:
        User information from the IdP

    Raises:
        HTTPException: If userinfo request fails
    """
    # Extract Bearer token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth_header.split(" ", 1)[1]
    result = await oauth_client.get_userinfo(access_token)

    if isinstance(result, OAuthError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.model_dump(),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return result
