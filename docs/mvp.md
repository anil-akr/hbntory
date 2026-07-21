# Définition du MVP (Task 0)

Le MVP couvre **toutes les exigences obligatoires** de l'énoncé, sans fonctionnalité
superflue. L'objectif : une intégration complète de bout en bout (Backoffice + IA + Client)
plutôt que quelques briques très abouties mais non connectées.

---

## 1. À implémenter en premier (cœur du MVP — obligatoire)

**Base de données (SQLAlchemy)**
- Modèles : `User`, `Branch` (boutique), `Stock`.
- `Stock` relie une boutique + un produit (par **SKU**, cf. `architecture.md` §4) + une
  quantité. Contrainte : la quantité ne devient **jamais négative**.
- Aucun détail produit stocké localement.

**Authentification & autorisation**
- Login obligatoire pour tout le Backoffice.
- Mots de passe **hashés** (jamais en clair).
- Règles de rôle **appliquées côté backend**, pas seulement dans l'UI.

**Backoffice — Admin (un seul admin)**
- Lister les utilisateurs, créer des utilisateurs communs, les assigner à une boutique,
  soft-delete, modifier, changer le mot de passe, changer la boutique assignée.
- L'admin **ne gère pas** le stock.

**Backoffice — Utilisateur commun (rattaché à une seule boutique)**
- Ajouter / retirer / consulter le stock **de sa boutique uniquement**.
- Lister les produits actuellement en stock dans sa boutique.
- Toute opération validée côté backend (quantité valide, boutique = la sienne).

**Intégration Product API**
- Consommer l'API externe pour toute info produit (liste + détail).
- Gérer la robustesse : lenteur (`simulate_delay_ms`), indisponibilité (`force_error` /
  503), produit introuvable (404), liste vide.

**Serveur MCP**
- Outils produits : lister les produits, récupérer le détail d'un produit (bridge vers le
  Product API).
- Outils stock : lecture contrôlée du stock depuis la base.
- Exposé en Streamable HTTP (cf. `communication-decisions.md`, décision 3).

**Service IA (service indépendant)**
- Un agent qui répond en langage naturel aux questions du Client, via les outils MCP.
- Sait répondre aux types de questions de l'énoncé (stock d'un produit par boutique,
  produits d'une boutique, détails d'un produit, quelle(s) boutique(s) pour un panier).
- **N'invente pas** : si les outils ne fournissent pas l'info, il le dit clairement.

**Client Web**
- Page publique, anonyme, style chat ou barre de recherche.
- Envoie chaque question au Service IA en REST (décision 2) et affiche la réponse.

**Orchestration**
- `docker-compose` lançant nos services + le Product API fourni.

---

## 2. À reporter (après le MVP)

- Historique / journal des mouvements de stock (audit).
- Filtres, tri et pagination avancés dans l'UI du Backoffice.
- Amélioration visuelle des interfaces (le design n'est pas la priorité).
- Recherche produit avancée côté Client.
- Suite de tests d'intégration étendue.

---

## 3. Optionnel (seulement si le temps le permet)

- **Streaming** des réponses de l'IA (WebSocket ou SSE) — le MVP reste en REST.
- Optimisation fine du « quelles boutiques visiter pour un panier multi-produits ».
- Cache des données produit pour limiter les appels au Product API.
- Architecture multi-agents ou agent plus élaboré.
- Tableau de bord / statistiques de stock pour l'admin.
