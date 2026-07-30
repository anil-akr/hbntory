from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# Branch schemas
class BranchCreate(BaseModel):
    name: str


class BranchResponse(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


# User schemas
class UserCreate(BaseModel):
    username: str
    password: str
    # Safe default: never grant admin rights just because the field was omitted
    role: str = "common"
    branch_id: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    branch_id: Optional[int] = None
    # Only set for a deactivated account (soft delete), so the interface can
    # show "deactivated" instead of making the row disappear.
    deleted_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Inventory schemas
class InventoryCreate(BaseModel):
    branch_id: int
    product_id: str
    quantity: int = 0


class InventoryResponse(BaseModel):
    id: int
    branch_id: int
    product_id: str
    quantity: int
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str
