from datetime import datetime, timezone
from typing import List
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import schemas
import auth
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="HBntory API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# AUTHENTIFICATION
# ==========================================

@app.post("/token", tags=["Authentification"])
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/register", response_model=schemas.UserResponse, tags=["Authentification"])
def register_user(
    user_in: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un administrateur peut créer des utilisateurs.",
        )
    
    existing_user = db.query(models.User).filter(models.User.username == user_in.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un utilisateur avec cet identifiant existe déjà.",
        )
    
    hashed_password = auth.get_password_hash(user_in.password)
    
    user_kwargs = {
        "username": user_in.username,
        "role": user_in.role,
        "branch_id": user_in.branch_id
    }
    if hasattr(models.User, 'password_hash'):
        user_kwargs["password_hash"] = hashed_password
    else:
        user_kwargs["hashed_password"] = hashed_password

    new_user = models.User(**user_kwargs)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# ==========================================
# BOUTIQUES (BRANCHES)
# ==========================================

@app.get("/branches", response_model=List[schemas.BranchResponse], tags=["Boutiques"])
def list_branches(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.Branch).all()


@app.post("/branches", response_model=schemas.BranchResponse, tags=["Boutiques"])
def create_branch(
    branch_in: schemas.BranchCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un administrateur peut créer une boutique.",
        )
    
    new_branch = models.Branch(name=branch_in.name)
    db.add(new_branch)
    db.commit()
    db.refresh(new_branch)
    return new_branch


# ==========================================
# INVENTAIRE / STOCKS
# ==========================================

# 1. Obtenir TOUS les stocks (pour la vue globale Admin)
@app.get("/inventories", response_model=List[schemas.InventoryResponse], tags=["Inventaire"])
def get_all_inventories(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.Inventory).all()


# 2. Obtenir le stock d'une boutique spécifique
@app.get("/inventories/{branch_id}", response_model=List[schemas.InventoryResponse], tags=["Inventaire"])
def get_inventory_by_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.Inventory).filter(models.Inventory.branch_id == branch_id).all()


# 3. Créer ou Mettre à jour la quantité d'un produit
@app.post("/inventories", response_model=schemas.InventoryResponse, tags=["Inventaire"])
def create_or_update_inventory(
    item: schemas.InventoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    branch = db.query(models.Branch).filter(models.Branch.id == item.branch_id).first()
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La boutique #{item.branch_id} n'existe pas.",
        )

    inventory_item = db.query(models.Inventory).filter(
        models.Inventory.branch_id == item.branch_id,
        models.Inventory.product_id == item.product_id
    ).first()

    if inventory_item:
        inventory_item.quantity = item.quantity
    else:
        inventory_item = models.Inventory(
            branch_id=item.branch_id,
            product_id=item.product_id,
            quantity=item.quantity
        )
        db.add(inventory_item)

    db.commit()
    db.refresh(inventory_item)
    return inventory_item


# ==========================================
# ADMINISTRATION (UTILISATEURS)
# ==========================================

@app.get("/users", response_model=List[schemas.UserResponse], tags=["Administration"])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs.",
        )
    return db.query(models.User).filter(models.User.deleted_at == None).all()


@app.delete("/users/{user_id}", tags=["Administration"])
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs.",
        )
    
    user_to_delete = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur introuvable.",
        )
    
    user_to_delete.deleted_at = datetime.now(timezone.utc)
    db.commit()
    
    return {"message": f"Utilisateur {user_to_delete.username} supprimé avec succès."}