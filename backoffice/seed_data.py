import sqlite3
from passlib.context import CryptContext
from database import engine, Base
# DO NOT REMOVE: importing models registers the tables with SQLAlchemy.
# Without it, create_all() creates nothing (linters flag it as "unused",
# but it really is needed).
import models  # noqa: F401

# 1. Create the database tables 🏗️
Base.metadata.create_all(bind=engine)

# Password hashing setup 🔐
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Connect to the SQLite database 🗄️
connection = sqlite3.connect("inventory.db")
cursor = connection.cursor()

# Reference stock, by branch then by product 📊
stock_by_branch = {
    "Paris Centre": {"HB-LAP-1001": 12, "HB-MON-2101": 8, "HB-DCK-3001": 25, "HB-CAM-5101": 4},
    "Lyon Part-Dieu": {"HB-LAP-1001": 5, "HB-SSD-7101": 40, "HB-PWR-8101": 30, "HB-DCK-3001": 10},
    "Marseille Prado": {"HB-LAP-1001": 3, "HB-MON-2101": 6, "HB-CAM-5101": 9, "HB-SSD-7101": 15}
}

# Start over from the reference stock above, so the script can be run again
# between two demos. The unique constraint on (branch, product) would reject a
# second row for the same pair anyway.
cursor.execute("DELETE FROM inventories;")

# 2. Insert the branches and their stock 🏬📦
for branch_name, products in stock_by_branch.items():
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

# 3. Get the id of Paris Centre for the employee account 👤
cursor.execute("SELECT id FROM branches WHERE name = ?", ("Paris Centre",))
paris_id = cursor.fetchone()[0]

# 4. Insert the employee, with a hashed password 🔑
cursor.execute("""
    INSERT INTO users (username, password_hash, role, branch_id)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(username) DO NOTHING;
""", ('employe_paris', pwd_context.hash('employe123'), 'common', paris_id))

# 5. Insert the administrator (no branch assigned, does not manage stock) 👑
cursor.execute("""
    INSERT INTO users (username, password_hash, role, branch_id)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(username) DO NOTHING;
""", ('admin', pwd_context.hash('admin123'), 'admin', None))

# Save the changes and close 💾
connection.commit()
connection.close()

print("Base de données et tables créées avec succès ! 🎉")