# Sport Card Entire Lot — Master Catalog

Working files:
- `cards.jsonl` — one JSON object per card, appended as each photo is cataloged.
  Fields: photo, slot, year, brand, set, player, team, card_no, parallel,
  serial, graded (co/grade/cert), auto (bool), sticker_price, est_comp,
  comp_source, confidence, needs_more, notes.
- Master inventory (sorted, with comps) and the "needs more info" list are
  generated from cards.jsonl.

Source photos: images/jpg/*.jpg (converted from images/heic/*.HEIC)
