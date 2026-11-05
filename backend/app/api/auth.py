"""Verify tokens with Supabase Auth; never trust an unverified JWT subject."""
from uuid import UUID
import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


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
