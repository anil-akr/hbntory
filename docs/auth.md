# Authentification & Autorisation (Backoffice)

Ce document explique **comment le Backoffice protège l'accès** : comment un
utilisateur prouve son identité (authentification) et ce qu'il a le droit de faire
une fois connecté (autorisation). Tout le code concerné vit dans
[`backoffice/auth.py`](../backoffice/auth.py) et [`backoffice/main.py`](../backoffice/main.py).

## 1. Stockage des mots de passe : bcrypt (jamais en clair)

On ne stocke **jamais** le mot de passe en clair. À la création d'un utilisateur,
le mot de passe est transformé en **empreinte (hash) bcrypt** :

```python
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
password_hash = pwd_context.hash(user.password)   # -> "$2b$12$...."
```

Seule cette empreinte est enregistrée dans la base (colonne `password_hash`).

**Pourquoi bcrypt et pas un simple SHA256 ?**

| | Clair | SHA256 « nu » | bcrypt |
|---|---|---|---|
| Lisible si la base fuite | ❌ oui | non (mais…) | non |
| Résiste aux tables précalculées (rainbow tables) | ❌ | ❌ (pas de sel) | ✅ **sel intégré** |
| Lent volontairement (freine le brute-force) | ❌ | ❌ (très rapide) | ✅ **facteur de coût** |

- **Sel (salt) intégré :** bcrypt ajoute une valeur aléatoire à chaque hash. Deux
  utilisateurs avec le même mot de passe ont donc deux empreintes différentes, ce
  qui casse les attaques par dictionnaire précalculé.
- **Lenteur volontaire :** bcrypt est conçu pour être *coûteux* à calculer. Un
  SHA256 se calcule des millions de fois par seconde (idéal pour un attaquant qui
  teste des mots de passe) ; bcrypt, non.

**Vérification** au moment du login : on re-hash le mot de passe fourni et on
compare, sans jamais déchiffrer (un hash est à sens unique) :

```python
pwd_context.verify(mot_de_passe_saisi, user.password_hash)  # -> True / False
```

## 2. Authentification : login → jeton JWT

Le flux (endpoint `POST /token`) :

1. L'utilisateur envoie `username` + `password`.
2. On récupère l'utilisateur, on vérifie le mot de passe avec `pwd_context.verify`.
3. Si l'utilisateur a été **désactivé** (`deleted_at` non nul), l'accès est refusé.
4. Sinon, on émet un **jeton JWT** signé, valable 30 minutes :

```python
create_access_token(data={"sub": user.username})  # HS256, exp = +30 min
```

Le client renvoie ensuite ce jeton dans l'en-tête `Authorization: Bearer <jeton>`
à chaque requête protégée.

**Pourquoi un jeton JWT plutôt qu'une session serveur ?**

- **Sans état (stateless) :** le serveur n'a pas à garder en mémoire la liste des
  sessions actives. Le jeton contient lui-même l'identité (`sub`) et la date
  d'expiration (`exp`), et il est **signé** avec `SECRET_KEY` : impossible de le
  falsifier sans la clé.
- **Simple à répartir :** n'importe quelle instance de l'API peut vérifier un jeton
  avec la clé, sans base de sessions partagée.
- **Adapté à notre archi :** le front public et le Backoffice sont des clients HTTP
  séparés ; un jeton porté dans un en-tête est plus simple qu'un cookie de session.

La contrepartie (voir *Limitations* du README) : un jeton reste valide jusqu'à son
expiration, on ne peut pas le révoquer instantanément.

## 3. Vérification du jeton à chaque requête

Chaque endpoint protégé dépend de `get_current_user`, qui :

1. décode et vérifie la signature + l'expiration du jeton (`jwt.decode`) ;
2. recharge l'utilisateur depuis la base à partir du `sub` ;
3. rejette (401) si le jeton est invalide/expiré ou l'utilisateur introuvable.

```python
def get_current_user(token=Depends(oauth2_scheme), db=Depends(get_db)):
    payload = verify_token(token)          # None si invalide/expiré
    ...
    return user                            # injecté dans l'endpoint
```

## 4. Autorisation : deux rôles + cloisonnement par boutique

Une fois authentifié, ce que l'utilisateur peut faire dépend de son **rôle**
(`admin` ou `common`) et de sa **boutique** (`branch_id`).

| Action | `admin` | `common` (employé) |
|---|:---:|:---:|
| Se connecter | ✅ | ✅ |
| Créer / modifier / supprimer des utilisateurs | ✅ | ❌ 403 |
| Voir le stock de **sa** boutique | — (voit tout) | ✅ |
| Voir le stock d'une **autre** boutique | ✅ | ❌ 403 |
| Gérer (ajouter/retirer) du stock | ❌ 403 | ✅ **sa boutique uniquement** |
| Consulter le catalogue produit (API externe) | ✅ | ✅ |

Points clés de la logique (dans `main.py`) :

- **Séparation des pouvoirs :** l'admin gère les *utilisateurs* mais **ne gère pas le
  stock** ; l'employé gère le *stock* mais **pas les utilisateurs**.
- **Cloisonnement par boutique :** un employé ne peut lire/modifier que le stock de
  `current_user.branch_id`. Toute action sur une autre boutique renvoie **403**.
- **Garde-fou métier :** une quantité négative est refusée (**400**).

Exemple (empêcher un employé d'agir sur une autre boutique) :

```python
if current_user.branch_id != inventory.branch_id:
    raise HTTPException(status_code=403, detail="... votre propre boutique.")
```

## 5. Désactivation d'un compte (soft delete)

Supprimer un utilisateur ne l'efface pas : on renseigne `deleted_at` (soft delete),
ce qui préserve l'historique. Un compte désactivé est **refusé au login** (voir
étape 3 du flux `POST /token`).

## 6. Récapitulatif des fichiers

| Fichier | Rôle |
|---|---|
| `auth.py` | hash/vérif bcrypt, création/vérif du JWT, `get_current_user` |
| `main.py` | endpoints `/token`, `/register`, et les contrôles de rôle/boutique |
| `models.py` | colonnes `password_hash`, `role`, `branch_id`, `deleted_at` |
