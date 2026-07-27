import sqlite3

# Connexion à la base de données
conn = sqlite3.connect('inventory.db')
cursor = conn.cursor()

print(" Début du remplissage de la base de données...")

# 1. Insertion des boutiques
branches = ['Paris Centre', 'Lyon Part-Dieu', 'Marseille Prado']

for name in branches:
    cursor.execute("""
        INSERT INTO branches (name) 
        VALUES (?)
        ON CONFLICT(name) DO NOTHING;
    """, (name,))

# 2. Insertion d'un employé rattaché à Paris Centre
cursor.execute("SELECT id FROM branches WHERE name = 'Paris Centre'")
paris_id = cursor.fetchone()[0]

cursor.execute("""
    INSERT INTO users (username, password_hash, role, branch_id)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(username) DO NOTHING;
""", ('employe_paris', 'hash_factice_123', 'common', paris_id))

# 3. Liste des SKU demandés par ton binôme
skus = [
    'HB-LAP-1001',
    'HB-MON-2101',
    'HB-DCK-3001',
    'HB-CAM-5101',
    'HB-SSD-7101',
    'HB-PWR-8101'
]

# 4. Insertion du stock (15 unités par produit et par boutique)
cursor.execute("SELECT id FROM branches")
branch_ids = [b[0] for b in cursor.fetchall()]

for b_id in branch_ids:
    for sku in skus:
        cursor.execute("""
            INSERT INTO inventories (branch_id, product_id, quantity)
            VALUES (?, ?, ?);
        """, (b_id, sku, 15))

# Sauvegarde des changements
conn.commit()
conn.close()

print("Base de données remplie avec succès !")