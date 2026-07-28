import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import List
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timezone

import models
import schemas
import auth
from database import Base, engine, get_db

# URL de l'API Produit externe (lecture seule). Le Backoffice affiche les infos
# produit depuis cette API, jamais depuis la base locale.
PRODUCT_API_URL = os.environ.get("PRODUCT_API_URL", "http://localhost:5001")


def _fetch_product_api(path: str):
    """Appelle l'API Produit externe et renvoie son JSON, ou une erreur claire."""
    try:
        with urllib.request.urlopen(f"{PRODUCT_API_URL}{path}", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise HTTPException(
            status_code=error.code, detail="Produit introuvable ou API Produit en erreur."
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API Produit injoignable.",
        )


Base.metadata.create_all(bind=engine)
app = FastAPI(title="API Backoffice")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Bienvenue sur l'API !"}


# AUTHENTIFICATION ET UTILISATEURS
@app.post("/register", response_model=schemas.UserResponse, tags=["Administration"])
def register_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Seul l'admin peut créer des utilisateurs (le 1er admin vient du seed)
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs.",
        )

    db_user = (
        db.query(models.User).filter(models.User.username == user.username).first()
    )
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce nom d'utilisateur est déjà utilisé.",
        )

    # Création de l'utilisateur avec son rôle et sa boutique
    new_user = models.User(
        username=user.username,
        password_hash=auth.pwd_context.hash(user.password),
        role=user.role,
        branch_id=user.branch_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@app.post("/token", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = (
        db.query(models.User)
        .filter(models.User.username == form_data.username)
        .first()
    )

    # Vérifie l'existence et le mot de passe
    if not user or not auth.pwd_context.verify(
        form_data.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Bloque l'accès si l'utilisateur a été supprimé
    if user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ce compte a été désactivé.",
        )

    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


# GESTION BOUTIQUE

@app.post("/branches", response_model=schemas.BranchResponse, tags=["Boutiques"])
def create_branch(
    branch: schemas.BranchCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    db_branch = db.query(models.Branch).filter(models.Branch.name == branch.name).first()
    if db_branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Une boutique avec ce nom existe déjà.",
        )
    new_branch = models.Branch(name=branch.name)
    db.add(new_branch)
    db.commit()
    db.refresh(new_branch)
    return new_branch


@app.get("/branches", response_model=List[schemas.BranchResponse], tags=["Boutiques"])
def list_branches(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return db.query(models.Branch).all()


# GESTION STOCK

@app.get("/inventories/{branch_id}", response_model=List[schemas.InventoryResponse], tags=["Stock"])
def get_branch_inventory(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Les utilisateurs ne voient que le stock de leur propre boutique
    if current_user.role != "admin" and current_user.branch_id != branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez consulter que le stock de votre boutique assignée.",
        )
    return db.query(models.Inventory).filter(models.Inventory.branch_id == branch_id).all()


@app.post("/inventories", response_model=schemas.InventoryResponse, tags=["Stock"])
def update_or_create_stock(
    inventory: schemas.InventoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # L'administrateur ne peut pas gérer le stock
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Les administrateurs ne peuvent pas gérer le stock.",
        )

    # L'employé ne peut gérer QUE le stock de sa propre boutique
    if current_user.branch_id != inventory.branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez gérer que le stock de votre propre boutique.",
        )

    # Vérification de la quantité (ne peut pas être négative)
    if inventory.quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La quantité en stock ne peut pas être négative.",
        )

    db_inventory = (
        db.query(models.Inventory)
        .filter(
            models.Inventory.branch_id == inventory.branch_id,
            models.Inventory.product_id == inventory.product_id,
        )
        .first()
    )

    if db_inventory:
        db_inventory.quantity = inventory.quantity
    else:
        db_inventory = models.Inventory(
            branch_id=inventory.branch_id,
            product_id=inventory.product_id,
            quantity=inventory.quantity,
        )
        db.add(db_inventory)

    db.commit()
    db.refresh(db_inventory)
    return db_inventory


# PRODUITS (depuis l'API externe, jamais la base locale)

@app.get("/products", tags=["Produits (API externe)"])
def list_products_from_api(
    search: str = "",
    current_user: models.User = Depends(auth.get_current_user),
):
    """Liste les produits depuis l'API Produit EXTERNE (nom, prix, etc.)."""
    path = "/api/v1/products?limit=100"
    if search:
        path += "&q=" + urllib.parse.quote(search)
    return _fetch_product_api(path)


@app.get("/products/{identifier}", tags=["Produits (API externe)"])
def get_product_from_api(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Détails d'un produit depuis l'API Produit EXTERNE (par SKU ou id)."""
    return _fetch_product_api(f"/api/v1/products/{urllib.parse.quote(identifier)}")


# ADMINISTRATION

@app.get("/users", response_model=List[schemas.UserResponse], tags=["Administration"])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Seul l'administrateur peut voir la liste des utilisateurs
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs.",
        )
    return db.query(models.User).all()


@app.delete("/users/{user_id}", tags=["Administration"])
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Seul l'admin peut supprimer un utilisateur
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs.",
        )

    # Recherche de l'utilisateur en base
    user_to_delete = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé.",
        )

    # Application du Soft Delete
    user_to_delete.deleted_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": f"L'utilisateur {user_to_delete.username} a été désactivé."}


@app.put("/users/{user_id}", response_model=schemas.UserResponse, tags=["Administration"])
def update_user(
    user_id: int,
    user_update: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Vérifie que c'est bien un admin
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs.",
        )

    # Cherche l'utilisateur dans la base
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé.",
        )

    # Met à jour les champs (rôle, boutique, ET mot de passe)
    db_user.role = user_update.role
    db_user.branch_id = user_update.branch_id
    db_user.password_hash = auth.pwd_context.hash(user_update.password)
    
    db.commit()
    db.refresh(db_user)
    return db_user
