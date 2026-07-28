"""Automated tests for the Backoffice (Task 7 critical scenarios).

Run from the backoffice/ folder, with the dependencies installed:
    python test_backoffice.py

Uses a throwaway SQLite database, so it never touches inventory.db.
The product test needs the external Product API running on :5001.
"""
import os

import sqlalchemy
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import auth
import database
import main
import models

# --- Throwaway test database (never touches inventory.db) ---
TEST_DB = "_test_backoffice.db"
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
test_engine = sqlalchemy.create_engine(
    f"sqlite:///./{TEST_DB}", connect_args={"check_same_thread": False}
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
database.Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


main.app.dependency_overrides[database.get_db] = override_get_db
client = TestClient(main.app)

# --- Seed: 2 branches, 1 admin, 1 common user (Paris) ---
db = TestSession()
paris = models.Branch(name="Paris Centre")
lyon = models.Branch(name="Lyon Part-Dieu")
db.add_all([paris, lyon])
db.commit()
PARIS_ID, LYON_ID = paris.id, lyon.id
db.add(models.User(username="admin", password_hash=auth.get_password_hash("admin123"), role="admin", branch_id=None))
db.add(models.User(username="bob", password_hash=auth.get_password_hash("bob123"), role="common", branch_id=PARIS_ID))
db.commit()
db.close()

results = []


def check(label, condition):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + label)


def login(username, password):
    """Return (token_or_None, status_code)."""
    r = client.post("/token", data={"username": username, "password": password})
    return r.json().get("access_token"), r.status_code


def h(token):
    return {"Authorization": f"Bearer {token}"}


admin_token, _ = login("admin", "admin123")
bob_token, _ = login("bob", "bob123")
check("admin login -> token", bool(admin_token))
check("common (bob) login -> token", bool(bob_token))
check("mauvais mot de passe -> 401", login("bob", "wrong")[1] == 401)
check("route protégée sans token -> 401", client.get("/users").status_code == 401)

# --- Common user stock operations ---
r = client.post("/inventories", json={"branch_id": PARIS_ID, "product_id": "HB-LAP-1001", "quantity": 10}, headers=h(bob_token))
check("common ajoute du stock dans SA boutique -> 200", r.status_code == 200 and r.json()["quantity"] == 10)
r = client.post("/inventories", json={"branch_id": PARIS_ID, "product_id": "HB-LAP-1001", "quantity": 3}, headers=h(bob_token))
check("common modifie/retire du stock (10 -> 3)", r.status_code == 200 and r.json()["quantity"] == 3)
check("quantité négative -> 400", client.post("/inventories", json={"branch_id": PARIS_ID, "product_id": "HB-LAP-1001", "quantity": -1}, headers=h(bob_token)).status_code == 400)
check("common sur une AUTRE boutique -> 403", client.post("/inventories", json={"branch_id": LYON_ID, "product_id": "HB-LAP-1001", "quantity": 5}, headers=h(bob_token)).status_code == 403)
r = client.get(f"/inventories/{PARIS_ID}", headers=h(bob_token))
check("common consulte le stock de SA boutique", r.status_code == 200 and len(r.json()) >= 1)
check("common consulte une AUTRE boutique -> 403", client.get(f"/inventories/{LYON_ID}", headers=h(bob_token)).status_code == 403)

# --- Authorization boundaries ---
check("admin gère du stock -> 403", client.post("/inventories", json={"branch_id": PARIS_ID, "product_id": "HB-LAP-1001", "quantity": 1}, headers=h(admin_token)).status_code == 403)
check("common liste les users -> 403", client.get("/users", headers=h(bob_token)).status_code == 403)

# --- Admin user management ---
r = client.post("/register", json={"username": "alice", "password": "alice123", "role": "common", "branch_id": LYON_ID}, headers=h(admin_token))
check("admin crée un employé (role=common, boutique) -> 200", r.status_code == 200 and r.json()["role"] == "common" and r.json()["branch_id"] == LYON_ID)
alice_id = r.json()["id"]
# A user created without an explicit role must default to "common", never "admin".
r = client.post("/register", json={"username": "charlie", "password": "charlie123", "branch_id": PARIS_ID}, headers=h(admin_token))
check("register sans role -> defaut 'common' (jamais admin)", r.status_code == 200 and r.json()["role"] == "common")
check("non-admin crée un user -> 403", client.post("/register", json={"username": "x", "password": "y"}, headers=h(bob_token)).status_code == 403)

# change a user's password
users = client.get("/users", headers=h(admin_token)).json()
bob_id = next(u["id"] for u in users if u["username"] == "bob")
check("admin change le mot de passe d'un user -> 200", client.put(f"/users/{bob_id}", json={"username": "bob", "password": "newpass", "role": "common", "branch_id": PARIS_ID}, headers=h(admin_token)).status_code == 200)
check("ancien mot de passe refusé après changement", login("bob", "bob123")[1] == 401)
check("nouveau mot de passe accepté", login("bob", "newpass")[1] == 200)

# soft delete
check("admin soft-delete un user -> 200", client.delete(f"/users/{alice_id}", headers=h(admin_token)).status_code == 200)
check("user supprimé ne peut plus se connecter -> 401", login("alice", "alice123")[1] == 401)

# --- Product details come from the EXTERNAL API (not local DB) ---
r = client.get("/products/HB-LAP-1001", headers=h(admin_token))
check("détails produit via l'API Produit externe (:5001)", r.status_code == 200 and "Holberton" in str(r.json()))

# cleanup
os.remove(TEST_DB)
print(f"\n==> {sum(results)}/{len(results)} tests OK")
raise SystemExit(0 if all(results) else 1)
