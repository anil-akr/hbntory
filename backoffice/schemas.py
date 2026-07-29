from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# Shémas branche
class BranchCreate(BaseModel):
    name: str


class BranchResponse(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


# Shémas utilisateur
class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "common"  # Safe default: never grant admin rights by omission
    branch_id: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    branch_id: Optional[int] = None
    # Rempli uniquement pour un compte désactivé (soft delete) : l'interface
    # affiche ainsi "désactivé" au lieu de faire disparaître la ligne.
    deleted_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Shémas inventaire
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
