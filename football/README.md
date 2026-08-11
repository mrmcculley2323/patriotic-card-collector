# Football Cards — subset of the Sport Card Entire Lot

**230 football cards** filtered from the full 726-card lot. Est. total: **~$5,636**
(top card: 1976 Topps Walter Payton rookie SGC 8 ~$1,500).

## Files
| File | What it is |
|---|---|
| `inventory.html` | Searchable/sortable dashboard, football only (open in browser) |
| `football_inventory.csv` | All 230 football cards, ranked most-expensive first |
| `football_card_dealer_pro_import.csv` | Same, mapped to Card Dealer Pro columns (Sport=Football) |
| `football_cardladder_fill.csv` | Fill `CARDLADDER_LAST_SOLD` + `SALE_DATE` from Card Ladder; send back to ingest |

## How this was split
Included every card whose team is an NFL club or a college-football program
(Oilers, Florida State, Penn State, South Carolina, Texas A&M, Indiana).
Ambiguous teams were disambiguated by player:
- **Cardinals** → football only for Fitzgerald, Kyler Murray, Trey McBride, Anquan Boldin
  (Pujols / Goldschmidt etc. stay in baseball).
- **Giants** → football only for Nabers, Jaxson Dart, Abdul Carter, Cam Skattebo, Micah McFadden
  (Willie Mays / Bryce Eldridge stay in baseball).

## Heads-up
6 of these are the Beckett-labeled **custom / counterfeit** autos (James Cook Kaboom ×2,
Manziel ×2, Singletary, Gilbert Brown) — disclose or hold; most marketplaces ban them.

Source of truth remains `../catalog/cards.jsonl`; regenerate with the scripts in `../catalog/`.
