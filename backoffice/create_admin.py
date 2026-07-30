from database import SessionLocal
import models
import auth

db = SessionLocal()

# Check whether the admin already exists
admin = db.query(models.User).filter(models.User.username == "admin").first()

if not admin:
    new_admin = models.User(
        username="admin",
        password_hash=auth.pwd_context.hash("admin123"),
        role="admin"
    )
    db.add(new_admin)
    db.commit()
    print("Compte administrateur 'admin' (mdp: admin123) créé avec succès !")
else:
    print("Le compte admin existe déjà.")

db.close()
