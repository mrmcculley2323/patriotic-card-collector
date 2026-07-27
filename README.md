# Patriotic Card Collector — Storefront

A patriotic sports-card storefront with live eBay listings, direct Buy-It-Now
checkout (Stripe), and automatic USPS shipping labels (Shippo).

## Run it

```
python server.py
```

Then open http://localhost:8321. No installs needed — plain Python.

**With no API keys configured, everything runs in DEMO mode:** sample eBay
listings, simulated checkout (no charges), and mock shipping labels. This lets
you test the whole flow safely. Add keys one at a time to go live.

## Pages

| Page | Who it's for |
|---|---|
| `/` | Buyers — live eBay listings + Buy-It-Now direct checkout |
| `/orders.html` | You — every order with shipping address, tracking #, and a Print Label button |

## Going live — 3 integrations

Copy `config.example.json` to `config.json`, then fill in keys as you get them.
**Never share config.json or upload it anywhere public.**

### 1. Live eBay listings (free)
1. Sign up at https://developer.ebay.com (free eBay Developers Program account).
2. Create an app under "Application Keys" (Production) — copy the **App ID
   (Client ID)** and **Cert ID (Client Secret)**.
3. In config.json set `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, and
   `EBAY_SELLER_USERNAME` (your eBay seller username).

The homepage then shows your real, current eBay listings with photos and
links to each item.

### 2. Direct payments — Stripe
1. Sign up at https://stripe.com and complete seller onboarding.
2. Copy your **Secret key** (starts `sk_live_...`; use `sk_test_...` to test)
   into `STRIPE_SECRET_KEY`.
3. In the Stripe dashboard add a webhook pointing to
   `https://YOUR-DOMAIN/api/stripe-webhook` for the event
   `checkout.session.completed`, and put its signing secret in
   `STRIPE_WEBHOOK_SECRET`.

Buyers click **Buy Now** and pay on Stripe's hosted checkout page, which also
collects their shipping address. Card numbers never touch this site or server.
Stripe's standard fee is ~2.9% + 30¢ per sale.

### 3. Automatic shipping labels — Shippo
1. Sign up at https://goshippo.com (pay-as-you-go plan is fine).
2. Add a payment method (labels cost real money — roughly $4–6 for USPS
   Ground Advantage on a bubble mailer).
3. Copy your **Live API token** into `SHIPPO_API_KEY`.
4. Put your real return address in `SHIP_FROM`.

When a Stripe payment completes, the server automatically buys the cheapest
USPS label for the buyer's address and saves the label + tracking number to
the order dashboard — just open `/orders.html` and hit **Print 4×6 Label**.

## Printing 4×6 labels on a Rollo

Labels are generated at a native **4×6 in** size and the **Print 4×6 Label**
button opens a dedicated print page (`/print/<order_id>`) that forces a
`4in × 6in` page with **zero margins** and stretches the label to fill the
whole sheet, then opens the print dialog for you. That means the label maps
1:1 onto the Rollo's printable area — no manual cropping or resizing per order.

One-time computer setup so it "just works" every time:

1. **Install the Rollo driver** from https://www.rollo.com/setup and plug the
   printer in. It should appear as *Rollo Printer* (or *Rollo X10xx*).
2. **Set the media/label size to 4×6:**
   - **Windows:** Settings → Bluetooth & devices → Printers → Rollo →
     Printing preferences → set **Paper size = 4" × 6"** (or *100mm × 150mm*).
   - **macOS:** System Settings → Printers & Scanners → Rollo → the paper size
     `4 x 6` is selected automatically in the print dialog.
3. In the browser print dialog that pops up, confirm:
   - **Destination / Printer:** Rollo
   - **Paper size:** 4 × 6 in
   - **Margins:** None (or Default)
   - **Scale:** 100% / **Actual size** — *not* "Fit to page shrink"
   - **Background graphics: ON** (so the barcode/label art prints)
4. Print one label, then check **"Use these settings by default"** /
   save them as the default — after that every label prints edge-to-edge with
   one click.

> Tip: make the Rollo your **default printer** if you only use it for labels,
> so you don't have to pick it each time.

## Your inventory

Edit `inventory.json` to control what's in the Buy-It-Now section — title,
price, weight in ounces (used for label rates), sport, and badge text.

**Heads up on double-selling:** if the same card is listed on eBay *and* in
the Buy-It-Now section, it can sell in both places. Keep direct inventory
separate from your eBay listings, or end the eBay listing as soon as a card
sells here.

**eBay policy note:** it's fine to run your own site, but don't put links to
it inside your eBay listings — eBay prohibits off-platform sale links.

## Going public

The site needs to be reachable on the internet for real buyers and for
Stripe's webhook. Easiest paths: a $5/month VPS, or a tunnel like Cloudflare
Tunnel from your PC. Set `SITE_URL` in config.json to your public URL, and set
`ADMIN_KEY` so only you can open the orders dashboard.
