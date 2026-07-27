import sqlite3
from passlib.context import CryptContext
from database import engine, Base
import models  # Charge tous vos modèles SQLAlchemy

# 1. Création automatique des tables dans la base de données 🏗️
Base.metadata.create_all(bind=engine)

# Configuration du hachage de mot de passe 🔐
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Connexion à la base de données SQLite 🗄️
conn = sqlite3.connect("inventory.db")
cursor = conn.cursor()

# Données créées par votre binôme 📊
data = {
    "branches": {
        "Paris Centre": {"HB-LAP-1001": 12, "HB-MON-2101": 8, "HB-DCK-3001": 25, "HB-CAM-5101": 4},
        "Lyon Part-Dieu": {"HB-LAP-1001": 5, "HB-SSD-7101": 40, "HB-PWR-8101": 30, "HB-DCK-3001": 10},
        "Marseille Prado": {"HB-LAP-1001": 3, "HB-MON-2101": 6, "HB-CAM-5101": 9, "HB-SSD-7101": 15}
    }
}

# 2. Insertion des boutiques et de leur stock 🏬📦
for branch_name, products in data["branches"].items():
    cursor.execute("""
        INSERT INTO branches (name)
        VALUES (?)
        ON CONFLICT(name) DO NOTHING;
    """, (branch_name,))
    
    cursor.execute("SELECT id FROM branches WHERE name = ?", (branch_name,))
    branch_id = cursor.fetchone()[0]
    
    for product_id, quantity in products.items():
        cursor.execute("""
            INSERT INTO inventories (branch_id, product_id, quantity)
            VALUES (?, ?, ?);
        """, (branch_id, product_id, quantity))

# 3. Récupération de l'ID de Paris Centre pour l'employé 👤
cursor.execute("SELECT id FROM branches WHERE name = ?", ("Paris Centre",))
paris_id = cursor.fetchone()[0]

# 4. Insertion de l'employé avec le mot de passe haché 🔑
cursor.execute("""
    INSERT INTO users (username, password_hash, role, branch_id)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(username) DO NOTHING;
""", ('employe_paris', pwd_context.hash('employe123'), 'common', paris_id))

# Sauvegarde des changements et fermeture 💾
conn.commit()
conn.close()

print("Base de données et tables créées avec succès ! 🎉")