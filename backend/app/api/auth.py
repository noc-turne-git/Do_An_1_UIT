"""Verify tokens with Supabase Auth; never trust an unverified JWT subject."""
from dataclasses import dataclass
from uuid import UUID
import httpx
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ChatPrincipal:
    """An authenticated account or an unguessable, server-issued guest session."""
    user_id: UUID | None = None
    anonymous_session_id: UUID | None = None

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None


def get_current_user_id(request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> UUID:
    if credentials is None or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Bearer access token required', headers={'WWW-Authenticate': 'Bearer'})
    settings = request.app.state.settings
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(503, 'Supabase Auth is not configured')
    try:
        response = httpx.get(settings.supabase_url.rstrip('/') + '/auth/v1/user',
            headers={'apikey': settings.supabase_publishable_key.get_secret_value(),
                     'Authorization': 'Bearer ' + credentials.credentials}, timeout=5,
            follow_redirects=False)
        if response.status_code in (401, 403):
            raise HTTPException(401, 'Invalid or expired access token')
        if response.status_code != 200:
            raise HTTPException(503, 'Authentication provider unavailable')
        return UUID(response.json()['id'])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Authentication provider unavailable') from None


def get_chat_principal(request: Request,
        anonymous_session_id: str | None = Header(default=None, alias='X-Anonymous-Session-ID'),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> ChatPrincipal:
    """Accept a verified account token or a guest session capability for chat only.

    Guest session IDs are minted by ``POST /api/v1/chat/anonymous-sessions`` and
    validated against the database by the conversation repository.
    """
    if credentials is not None:
        return ChatPrincipal(user_id=get_current_user_id(request, credentials))
    if anonymous_session_id:
        try:
            return ChatPrincipal(anonymous_session_id=UUID(anonymous_session_id))
        except ValueError:
            raise HTTPException(422, 'Invalid anonymous session ID') from None

    # Keep FastAPI dependency overrides useful for the authenticated API tests.
    override = request.app.dependency_overrides.get(get_current_user_id)
    if override is not None:
        return ChatPrincipal(user_id=override())
    raise HTTPException(401, 'Bearer access token or anonymous session required',
                        headers={'WWW-Authenticate': 'Bearer'})
