import hashlib
import secrets

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.logger import get_logger
from app.models import ApiClient

logger = get_logger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def get_current_client(
    api_key: str = Security(API_KEY_HEADER),
    db: Session = Depends(get_db),
) -> ApiClient:
    if not api_key:
        logger.warning("Request missing X-API-Key header")
        raise HTTPException(status_code=401, detail="X-API-Key header missing")

    key_hash = hash_key(api_key)
    client = db.query(ApiClient).filter(ApiClient.key_hash == key_hash).first()

    if not client:
        logger.warning("Request with invalid API key")
        raise HTTPException(status_code=403, detail="Invalid API key")

    if not client.is_active:
        logger.warning(f"Request with inactive API key for client: {client.name}")
        raise HTTPException(status_code=403, detail="API key is inactive")

    logger.info(f"Authenticated client: {client.name}")
    return client



def require_admin(api_key: str = Security(API_KEY_HEADER)):
    if not api_key:
        raise HTTPException(status_code=403, detail="Admin access required")

    if not secrets.compare_digest(
        api_key.encode("utf-8"),
        settings.admin_api_key.encode("utf-8"),
    ): 
        raise HTTPException(status_code=403, detail="Admin access required")

def get_demo_key(
):
    return settings.demo_api_key