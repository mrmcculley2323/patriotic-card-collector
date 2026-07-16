# Deploy to Render (free)

Everything is pre-configured — `render.yaml` tells Render exactly how to run
the site. You just need two free accounts and about 5 minutes.

## One-time setup

### Step 1 — GitHub (free account, holds the code)
1. Create an account at https://github.com/signup (skip if you have one).
2. Tell Claude you're signed in — Claude can push the prepared repo for you
   once you're authenticated, or:
   - Create a new **private** repository named `patriotic-card-collector`
   - Follow GitHub's "push an existing repository" instructions from the
     `patriotic-card-collector` folder (the git repo is already committed).

### Step 2 — Render (free account, runs the site)
1. Create an account at https://render.com (sign up **with GitHub** — easiest).
2. Click **New → Blueprint**, pick your `patriotic-card-collector` repo.
3. Render reads `render.yaml` and sets everything up. When prompted for
   environment values, set:
   - `ADMIN_KEY` — any secret password (protects your orders page)
   - `SITE_URL` — your Render URL, e.g. `https://patriotic-card-collector.onrender.com`
     (you can add this after the first deploy shows you the URL)
4. Deploy. Your site is live at `https://<name>.onrender.com`.

### Step 3 — API keys (whenever you get them)
Add these in Render → your service → **Environment** (same names as
config.json): `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `STRIPE_SECRET_KEY`,
`STRIPE_WEBHOOK_SECRET`, `SHIPPO_API_KEY`. Each one flips that feature from
demo to live. Point the Stripe webhook at
`https://<your-site>/api/stripe-webhook`.

## Free-tier fine print

- **Cold starts:** the free instance sleeps after ~15 minutes idle; the first
  visitor after that waits ~30–60 seconds while it wakes. Fine for starting
  out; $7/month removes it later if the shop takes off.
- **Order history resets on redeploys** (free tier has no permanent disk).
  This does NOT lose real orders: every paid order lives permanently in your
  Stripe dashboard and every label in your Shippo dashboard — print labels
  from the site dashboard soon after orders come in, or check Stripe/Shippo.
- **Ship-from address:** when you add the Shippo key, also add env vars
  `SHIP_FROM_NAME`, `SHIP_FROM_STREET1`, `SHIP_FROM_CITY`, `SHIP_FROM_STATE`,
  `SHIP_FROM_ZIP`, `SHIP_FROM_PHONE` in Render so labels carry your real
  return address.

## Updating the live site

After any change Claude makes locally:
```
git add -A
git commit -m "update"
git push
```
Render redeploys automatically on every push.
