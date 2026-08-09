# Cataloging progress

- Source photos: images/jpg/IMG_4814.jpg ... IMG_4955.jpg (141 photos total, ~5-6 cards each)
- Each photo = a staged layout of multiple cards; some carry the seller's price stickers.
- Data is appended to catalog/cards.jsonl (one JSON object per card).

## Resume pointer
- LAST PHOTO CATALOGED: IMG_4890
- NEXT PHOTO TO DO: IMG_4891
- To resume: read next images/jpg/IMG_####.jpg, append records to cards.jsonl, commit.

## Key flags found so far
- IMG_4823: TWO James Cook "Kaboom!" cards slabbed by Beckett as "COUNTERFEIT TRADING CARD"
  (auto authentic only). Likely NOT listable on major marketplaces; must disclose.
- IMG_4825: Mike Singletary "Booom!" Beckett labels "CUSTOM" card (auto authentic).
- IMG_4828: Allen Iverson Panini Signature Series card is an UNREDEEMED redemption (exp 11/27/2027).

## After identification pass, generate:
1. catalog/master_inventory.csv  (sorted most-expensive first; comps to be added)
2. catalog/needs_more_info.md     (cards flagged needs_more)
3. Replacement pro-image plan / card_dealer_pro import file
