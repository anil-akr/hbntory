import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import models
import schemas
import auth
from database import Base, engine, get_db

# URL of the external Product API (read-only). The Backoffice shows product
# details from this API, never from the local database.
PRODUCT_API_URL = os.environ.get("PRODUCT_API_URL", "http://localhost:5001")


def _fetch_product_api(path: str):
    """Call the external Product API and return its JSON, or a clear error."""
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


def _require_admin(current_user: models.User) -> None:
    """Stop the request with a 403 if the current user is not an admin.

    Used by the purely administrative routes (user management). Stock handling
    has its own, finer rules and does not go through this helper.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs.",
        )


def _reject_admin_role(requested_role: str) -> None:
    """Stop the request when it would create a second administrator.

    The system has exactly one administrator, created by the seed script. The
    interface never offers the admin role, and the API refuses it too, so the
    rule does not depend on the interface.
    """
    if requested_role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Le rôle 'admin' ne peut pas être attribué : il n'existe qu'un seul administrateur.",
        )


def _protect_admin_account(target_user: models.User) -> None:
    """Stop the request when it targets the single administrator account.

    The interface already displays the admin row as "Protégé". The API enforces
    the same rule, so the only administrator cannot be deactivated — which
    would otherwise lock user management out for good.
    """
    if target_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Le compte administrateur ne peut pas être modifié ni désactivé.",
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
    # Only an admin creates users (the first admin comes from the seed script)
    _require_admin(current_user)
    _reject_admin_role(user.role)

    existing_user = (
        db.query(models.User).filter(models.User.username == user.username).first()
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce nom d'utilisateur est déjà utilisé.",
        )

    # Create the user with the role and branch chosen by the admin
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
    # authenticate_user also rejects soft-deleted accounts.
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # The role travels in the token so the web interface knows which screen to
    # show. Authorization itself is always re-checked server-side against the
    # database: nothing is decided from the token contents.
    access_token = auth.create_access_token(
        data={"sub": user.username, "role": user.role}
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me", response_model=schemas.UserResponse, tags=["Administration"])
def read_current_user(current_user: models.User = Depends(auth.get_current_user)):
    """Return the current user (role and assigned branch).

    The interface uses it to state clearly which branch the employee works on,
    and to offer that branch only.
    """
    return current_user


# BRANCHES

@app.post("/branches", response_model=schemas.BranchResponse, tags=["Boutiques"])
def create_branch(
    branch: schemas.BranchCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Creating a branch is configuration work, so it belongs to the admin.
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un administrateur peut créer une boutique.",
        )

    existing_branch = db.query(models.Branch).filter(models.Branch.name == branch.name).first()
    if existing_branch:
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


# STOCK

@app.get("/inventories", response_model=List[schemas.InventoryResponse], tags=["Stock"])
def list_inventories(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Overview of the stock.

    The admin sees every branch (supervising without touching it); an employee
    only receives the stock of their own branch, as on every other route.
    """
    query = db.query(models.Inventory)
    if current_user.role != "admin":
        query = query.filter(models.Inventory.branch_id == current_user.branch_id)
    return query.all()


@app.get("/inventories/{branch_id}", response_model=List[schemas.InventoryResponse], tags=["Stock"])
def get_branch_inventory(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Users only see the stock of their own branch
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
    # The admin must not manage stock
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Les administrateurs ne peuvent pas gérer le stock.",
        )

    # An employee may only manage the stock of their OWN branch
    if current_user.branch_id != inventory.branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez gérer que le stock de votre propre boutique.",
        )

    # Quantity check: stock can never go negative
    if inventory.quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La quantité en stock ne peut pas être négative.",
        )

    # The product must exist in the external catalog. The database only stores
    # an identifier and cannot tell on its own whether it points to a real
    # product, so we ask the Product API before recording any stock.
    try:
        _fetch_product_api(
            f"/api/v1/products/{urllib.parse.quote(inventory.product_id)}"
        )
    except HTTPException as error:
        if error.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce produit n'existe pas dans le catalogue.",
            )
        raise

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


# PRODUCTS (from the external API, never from the local database)

@app.get("/products", tags=["Produits (API externe)"])
def list_products_from_api(
    search: str = "",
    current_user: models.User = Depends(auth.get_current_user),
):
    """List products from the EXTERNAL Product API (name, price, and so on)."""
    path = "/api/v1/products?limit=100"
    if search:
        path += "&q=" + urllib.parse.quote(search)
    return _fetch_product_api(path)


@app.get("/products/{identifier}", tags=["Produits (API externe)"])
def get_product_from_api(
    identifier: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Details of one product from the EXTERNAL Product API (by SKU or id)."""
    return _fetch_product_api(f"/api/v1/products/{urllib.parse.quote(identifier)}")


# ADMINISTRATION

@app.get("/users", response_model=List[schemas.UserResponse], tags=["Administration"])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Only the admin may list users
    _require_admin(current_user)
    return db.query(models.User).all()


@app.delete("/users/{user_id}", tags=["Administration"])
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Only the admin may delete a user
    _require_admin(current_user)

    user_to_delete = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé.",
        )
    _protect_admin_account(user_to_delete)

    # Soft delete: the row stays, only the deletion date is set
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
    # Only the admin may modify a user
    _require_admin(current_user)

    user_to_update = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_update:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé.",
        )
    _protect_admin_account(user_to_update)
    _reject_admin_role(user_update.role)

    # Update the fields: role, branch AND password
    user_to_update.role = user_update.role
    user_to_update.branch_id = user_update.branch_id
    user_to_update.password_hash = auth.pwd_context.hash(user_update.password)

    db.commit()
    db.refresh(user_to_update)
    return user_to_update
