# Service IA — types de questions supportés (Task 5)

Le Service IA est un backend **indépendant** qui répond aux questions du public
(langage naturel) sur les **produits** et le **stock**, en s'appuyant uniquement
sur les outils du serveur MCP. Il n'invente jamais de données.

## Communication client ↔ Service IA

- **REST** (décision `docs/communication-decisions.md`). Endpoint : `POST /ask`.
- Corps de la requête : `{"question": "..."}` → réponse : `{"answer": "..."}`.
- Chaque question est **indépendante** (pas d'historique de conversation).

## Types de questions supportés

| Type de question | Exemple | Outils utilisés |
|---|---|---|
| Détails d'un produit | « Donne-moi les détails du produit HB-LAP-1001 » | `get_product` |
| Où un produit est disponible | « Quelle boutique a du HB-LAP-1001 ? » | `stock_for_product` |
| Ce qu'une boutique a en stock | « Quels produits trouve-t-on à Lyon Part-Dieu ? » | `stock_in_branch` |
| Quelle(s) boutique(s) pour une liste d'achats | « Je veux 3 HB-LAP-1001 et 2 HB-MON-2101, quelle boutique ? » | `check_shopping_list` |
| Rechercher / lister des produits | « Quels claviers vendez-vous ? » | `list_products` |

## Hors périmètre

Si la question sort de ce périmètre, ou si les outils ne fournissent pas
l'information (produit inexistant, boutique inconnue, API produit injoignable),
l'agent répond **clairement que l'information n'est pas disponible** plutôt que
d'inventer.

## Accès au stock (stratégie)

L'IA accède au stock **via notre propre serveur MCP** (outils `stock_*`), pas par
un accès direct à la base. Frontière propre : l'agent ne parle qu'au MCP.

> ⚠️ Pour l'instant, les outils stock lisent un fichier local
> `product_mcp_server/stock_data.json` qui **remplace temporairement** la base
> d'inventaire partagée (côté Backoffice / Marie). À l'intégration, ces outils
> interrogeront la vraie base — les noms et formats de retour des outils ne
> changent pas, donc l'agent reste identique.

## Ancrage des réponses (grounding)

Le prompt système impose : n'utiliser que les données renvoyées par les outils,
ne jamais inventer (nom, prix, quantité, disponibilité), et dire clairement quand
l'information manque. Chaque appel d'outil est **affiché** dans la console du
service pour pouvoir observer/déboguer ce que fait l'agent.
