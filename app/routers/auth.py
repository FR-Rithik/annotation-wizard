import re
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import get_current_client, hash_key, require_admin, get_demo_key
from app.database import get_db
from app.models import AccessRequest, ApiClient

router = APIRouter()

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccessRequestCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., max_length=255)
    organization: str | None = Field(default=None, max_length=100)
    intended_use: str = Field(..., min_length=5, max_length=1000)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        clean = value.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format")
        return clean




@router.get("/me")
def get_me(client: ApiClient = Depends(get_current_client)):
    return {
        "id": client.id,
        "name": client.name,
        "is_active": client.is_active,
        "created_at": client.created_at,
    }


@router.post("/keys", status_code=201)
def create_key(
    name: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    raw_key = secrets.token_hex(32)
    client = ApiClient(name=name, key_hash=hash_key(raw_key))
    db.add(client)
    db.commit()
    db.refresh(client)
    return {
        "id": client.id,
        "name": client.name,
        "key": raw_key,
        "note": "Store this key safely. It will not be shown again.",
    }


@router.get("/keys")
def list_keys(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    clients = db.query(ApiClient).order_by(ApiClient.id).all()
    return [
        {
            "id": client.id,
            "name": client.name,
            "is_active": client.is_active,
            "created_at": client.created_at,
        }
        for client in clients
    ]


@router.delete("/keys/{client_id}", status_code=200)
def revoke_key(
    client_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    client = db.query(ApiClient).filter(ApiClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.is_active = False
    db.commit()
    return {"detail": f"Key for '{client.name}' has been revoked"}


@router.post("/access-requests", status_code=201)
def submit_access_request(
    payload: AccessRequestCreate,
    db: Session = Depends(get_db),
):
    request_entry = AccessRequest(
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        organization=payload.organization.strip() if payload.organization else None,
        intended_use=payload.intended_use.strip(),
    )
    db.add(request_entry)
    db.commit()
    db.refresh(request_entry)
    return {
        "status": "success",
        "detail": "Access request submitted successfully. The team will review your request.",
        "id": request_entry.id,
    }

@router.post("/demo-api-key", status_code = 201)
def use_demo_key(
):    
    demo_key = get_demo_key()
    return {
        "demo_key": demo_key,
    }

@router.get("/access-requests", status_code=200)
def list_access_requests(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    requests = db.query(AccessRequest).order_by(AccessRequest.id.desc()).all()
    return [
        {
            "id": req.id,
            "name": req.name,
            "email": req.email,
            "organization": req.organization,
            "intended_use": req.intended_use,
            "created_at": req.created_at,
        }
        for req in requests
    ]

