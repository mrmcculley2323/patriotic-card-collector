"""
Patriotic Card Collector — storefront server.

Zero-dependency Python backend (stdlib only). Serves the website and provides:
  * GET  /api/status          -> which integrations are live vs demo
  * GET  /api/listings        -> your live eBay listings (Browse API) or demo data
  * GET  /api/store           -> buy-now inventory from inventory.json
  * POST /api/checkout        -> creates a Stripe Checkout session (live mode)
  * POST /api/demo-checkout   -> simulated checkout with shipping form (demo mode)
  * POST /api/stripe-webhook  -> on paid checkout, buys a USPS label via Shippo
  * GET  /api/orders          -> order list for the seller dashboard (orders.html)
  * GET  /label/<order_id>    -> raw 4x6 mock label for demo orders
  * GET  /print/<order_id>    -> 4x6 zero-margin print page (Rollo) that
                                 auto-opens the print dialog, demo or live

Configuration comes from config.json (copy config.example.json) or environment
variables. With no keys configured, every feature runs in demo mode so the
whole flow can be tested without spending a cent.

Run:  python server.py   (serves on http://localhost:8321)
"""

import base64
import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SITE_DIR, "config.json")
INVENTORY_PATH = os.path.join(SITE_DIR, "inventory.json")
ORDERS_PATH = os.path.join(SITE_DIR, "orders.json")
# Cloud hosts (Render, etc.) set PORT; locally we default to 8321.
PORT = int(os.environ.get("PORT", "8321"))
HOST = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"

_orders_lock = threading.Lock()


# ---------------------------------------------------------------- config

def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    # Environment variables override config.json
    for key in [
        "EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET", "EBAY_SELLER_USERNAME",
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
        "SHIPPO_API_KEY", "ADMIN_KEY", "SITE_URL",
    ]:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    # SHIP_FROM_* env vars override the ship-from address (for cloud hosting)
    ship_env = {k[len("SHIP_FROM_"):].lower(): v for k, v in os.environ.items()
                if k.startswith("SHIP_FROM_")}
    if ship_env:
        cfg["SHIP_FROM"] = {**cfg.get("SHIP_FROM", {}), **ship_env}
    cfg.setdefault("SITE_URL", f"http://localhost:{PORT}")
    cfg.setdefault("SHIP_FROM", {
        "name": "Patriotic Card Collector",
        "street1": "123 Main St",
        "city": "Hometown",
        "state": "TX",
        "zip": "75001",
        "country": "US",
        "phone": "5555555555",
        "email": "mrmcculley23@gmail.com",
    })
    return cfg


CFG = load_config()


def ebay_live():
    return bool(CFG.get("EBAY_CLIENT_ID") and CFG.get("EBAY_CLIENT_SECRET")
                and CFG.get("EBAY_SELLER_USERNAME"))


def stripe_live():
    return bool(CFG.get("STRIPE_SECRET_KEY"))


def shippo_live():
    return bool(CFG.get("SHIPPO_API_KEY"))


# ---------------------------------------------------------------- helpers

def http_json(url, method="GET", headers=None, body=None, form=False):
    """Minimal JSON HTTP client on urllib."""
    headers = dict(headers or {})
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body, doseq=True).encode()
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            data = json.dumps(body).encode()
            headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        return None, f"HTTP {e.code} from {url}: {detail}"
    except Exception as e:  # network errors etc.
        return None, f"request to {url} failed: {e}"


def read_orders():
    if not os.path.exists(ORDERS_PATH):
        return []
    with open(ORDERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_order(order):
    with _orders_lock:
        orders = read_orders()
        orders.insert(0, order)
        with open(ORDERS_PATH, "w", encoding="utf-8") as f:
            json.dump(orders, f, indent=2)


def read_inventory():
    if not os.path.exists(INVENTORY_PATH):
        return []
    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- eBay

_ebay_token = {"value": None, "expires": 0}


def ebay_get_token():
    if _ebay_token["value"] and time.time() < _ebay_token["expires"] - 60:
        return _ebay_token["value"], None
    creds = f"{CFG['EBAY_CLIENT_ID']}:{CFG['EBAY_CLIENT_SECRET']}"
    auth = base64.b64encode(creds.encode()).decode()
    data, err = http_json(
        "https://api.ebay.com/identity/v1/oauth2/token",
        method="POST",
        headers={"Authorization": f"Basic {auth}"},
        body={"grant_type": "client_credentials",
              "scope": "https://api.ebay.com/oauth/api_scope"},
        form=True,
    )
    if err:
        return None, err
    _ebay_token["value"] = data["access_token"]
    _ebay_token["expires"] = time.time() + int(data.get("expires_in", 7200))
    return _ebay_token["value"], None


def fetch_ebay_listings():
    token, err = ebay_get_token()
    if err:
        return None, err
    seller = CFG["EBAY_SELLER_USERNAME"]
    # Browse API requires a query; "card" covers a sports card inventory.
    params = urllib.parse.urlencode({
        "q": CFG.get("EBAY_SEARCH_QUERY", "card"),
        "filter": f"sellers:{{{seller}}}",
        "limit": "50",
    })
    data, err = http_json(
        f"https://api.ebay.com/buy/browse/v1/item_summary/search?{params}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        },
    )
    if err:
        return None, err
    items = []
    for it in data.get("itemSummaries", []):
        items.append({
            "title": it.get("title"),
            "price": it.get("price", {}).get("value"),
            "currency": it.get("price", {}).get("currency", "USD"),
            "image": (it.get("image") or {}).get("imageUrl"),
            "url": it.get("itemWebUrl"),
            "condition": it.get("condition"),
            "buyingOptions": it.get("buyingOptions", []),
        })
    return items, None


DEMO_LISTINGS = [
    {"title": "2023 Topps Chrome Rookie Refractor — PSA 9", "price": "89.99", "icon": "⚾", "condition": "Graded", "tint": "#25406b"},
    {"title": "Panini Prizm On-Card Auto /99", "price": "149.99", "icon": "🏈", "condition": "Ungraded", "tint": "#5a2020"},
    {"title": "Select Silver Prizm /149", "price": "64.99", "icon": "🏀", "condition": "Near Mint", "tint": "#3d2a5e"},
    {"title": "Vintage Hall-of-Famer Lot (5 Cards)", "price": "44.99", "icon": "⚾", "condition": "Vintage", "tint": "#1f4d43"},
    {"title": "Game-Worn Multi-Color Patch Relic", "price": "199.99", "icon": "🏈", "condition": "Encased", "tint": "#6b4a1d"},
    {"title": "Prizm Rookie Base Lot (10 Cards)", "price": "29.99", "icon": "🏀", "condition": "Near Mint", "tint": "#23445e"},
    {"title": "Bowman Chrome 1st Prospect", "price": "54.99", "icon": "⚾", "condition": "Near Mint", "tint": "#4a1f33"},
    {"title": "Color Blast SSP Case-Hit Insert", "price": "119.99", "icon": "🏈", "condition": "Pack Fresh", "tint": "#2e4a2a"},
]


# ---------------------------------------------------------------- Stripe

def create_stripe_session(item):
    cents = int(round(float(item["price"]) * 100))
    site = CFG["SITE_URL"].rstrip("/")
    body = {
        "mode": "payment",
        "success_url": f"{site}/?checkout=success",
        "cancel_url": f"{site}/?checkout=cancelled",
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(cents),
        "line_items[0][price_data][product_data][name]": item["title"],
        "shipping_address_collection[allowed_countries][0]": "US",
        "metadata[item_id]": item["id"],
        "metadata[item_title]": item["title"],
        "metadata[weight_oz]": str(item.get("weight_oz", 4)),
    }
    return http_json(
        "https://api.stripe.com/v1/checkout/sessions",
        method="POST",
        headers={"Authorization": f"Bearer {CFG['STRIPE_SECRET_KEY']}"},
        body=body,
        form=True,
    )


def verify_stripe_signature(payload: bytes, sig_header: str) -> bool:
    secret = CFG.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        return False
    try:
        parts = dict(p.split("=", 1) for p in sig_header.split(","))
        signed = f"{parts['t']}.".encode() + payload
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parts["v1"])
    except Exception:
        return False


# ---------------------------------------------------------------- Shippo

def buy_shippo_label(address_to, weight_oz):
    headers = {"Authorization": f"ShippoToken {CFG['SHIPPO_API_KEY']}"}
    shipment_body = {
        "address_from": CFG["SHIP_FROM"],
        "address_to": address_to,
        "parcels": [{
            "length": "6", "width": "4", "height": "1",
            "distance_unit": "in",
            "weight": str(max(weight_oz, 1)), "mass_unit": "oz",
        }],
        "async": False,
    }
    shipment, err = http_json("https://api.goshippo.com/shipments/",
                              method="POST", headers=headers, body=shipment_body)
    if err:
        return None, err
    rates = [r for r in shipment.get("rates", []) if r.get("provider") == "USPS"] \
        or shipment.get("rates", [])
    if not rates:
        return None, "no shipping rates returned"
    cheapest = min(rates, key=lambda r: float(r["amount"]))
    # PNG @ 4x6 is a native thermal-label format: it prints edge-to-edge on a
    # Rollo without the letter-size whitespace the default "PDF" type adds, and
    # an <img> lets the print page scale it to fill the media automatically.
    txn, err = http_json("https://api.goshippo.com/transactions",
                         method="POST", headers=headers,
                         body={"rate": cheapest["object_id"],
                               "label_file_type": "PNG", "async": False})
    if err:
        return None, err
    if txn.get("status") != "SUCCESS":
        msgs = "; ".join(m.get("text", "") for m in txn.get("messages", []))
        return None, f"label purchase failed: {msgs or txn.get('status')}"
    return {
        "label_url": txn.get("label_url"),
        "label_file_type": "PNG",
        "tracking_number": txn.get("tracking_number"),
        "carrier": cheapest.get("provider"),
        "service": (cheapest.get("servicelevel") or {}).get("name"),
        "label_cost": cheapest.get("amount"),
    }, None


def mock_label(order_id):
    return {
        "label_url": f"/label/{order_id}",
        "label_file_type": "HTML",
        "tracking_number": "9400 1000 0000 " + order_id[:4].upper() + " DEMO",
        "carrier": "USPS (demo)",
        "service": "Ground Advantage (demo)",
        "label_cost": "0.00",
    }


# Sizes are in inches so the label always occupies the full 4x6 media,
# independent of screen DPI or the browser's print scaling.
LABEL_CSS = """
  @page { size: 4in 6in; margin: 0; }
  html, body { margin: 0; padding: 0; }
  .lbl { width: 4in; height: 6in; box-sizing: border-box; padding: .28in;
         border: 2px solid #000; background: #fff; color: #000;
         font-family: Arial, Helvetica, sans-serif; display: flex;
         flex-direction: column; }
  .demo { background: #c00; color: #fff; text-align: center; font-weight: bold;
          padding: .06in; letter-spacing: .12em; font-size: .13in; }
  .hdr { display: flex; justify-content: space-between; border-bottom: 3px solid #000;
         padding: .1in 0; font-weight: bold; font-size: .2in; margin-top: .1in; }
  .sec { font-size: .12in; color: #333; text-transform: uppercase;
         margin-top: .16in; letter-spacing: .05em; }
  .addr { font-size: .17in; line-height: 1.3; white-space: pre-line; }
  .addr.big { font-size: .24in; font-weight: bold; }
  .bars { margin-top: auto; height: .9in;
          background: repeating-linear-gradient(90deg,#000 0 3px,#fff 3px 6px,#000 6px 8px,#fff 8px 12px); }
  .trk { text-align: center; font-size: .16in; margin-top: .1in; letter-spacing: .08em; }
"""


def demo_label_html(order):
    """Inner markup for the demo shipping label, sized to fill a 4x6 sheet."""
    s, f = order["shipping"], CFG["SHIP_FROM"]
    street2 = ("\n" + s["street2"]) if s.get("street2") else ""
    return f"""<div class="lbl">
  <div class="demo">DEMO — NOT VALID FOR SHIPPING</div>
  <div class="hdr"><span>USPS GROUND ADVANTAGE</span><span>P</span></div>
  <div class="sec">From</div>
  <div class="addr">{f['name']}
{f['street1']}
{f['city']}, {f['state']} {f['zip']}</div>
  <div class="sec">Ship To</div>
  <div class="addr big">{s['name']}
{s['street1']}{street2}
{s['city']}, {s['state']} {s['zip']}</div>
  <div class="bars"></div>
  <div class="trk">{order['label']['tracking_number']}</div>
</div>"""


# ---------------------------------------------------------------- orders

def make_order(item, shipping, label, live, payment="demo"):
    return {
        "id": uuid.uuid4().hex[:12],
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "item_id": item.get("id"),
        "item_title": item.get("title"),
        "price": item.get("price"),
        "payment": payment,
        "live": live,
        "shipping": shipping,
        "label": label,
    }


REQUIRED_SHIP_FIELDS = ["name", "street1", "city", "state", "zip"]


# ---------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):

    # ---- plumbing
    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def log_message(self, fmt, *args):
        print("[web]", fmt % args)

    # ---- static files
    def serve_static(self, path):
        if path == "/":
            path = "/index.html"
        safe = os.path.normpath(path.lstrip("/"))
        if safe.startswith(("..", os.sep)) or safe in ("config.json", "orders.json", "server.py"):
            self.send_json({"error": "not found"}, 404)
            return
        full = os.path.join(SITE_DIR, safe)
        if not os.path.isfile(full):
            self.send_json({"error": "not found"}, 404)
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png", ".jpg": "image/jpeg",
            ".svg": "image/svg+xml", ".ico": "image/x-icon",
            ".css": "text/css", ".js": "text/javascript",
        }.get(os.path.splitext(full)[1], "application/octet-stream")
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- GET
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)

        if path == "/api/status":
            seller = CFG.get("EBAY_SELLER_USERNAME")
            self.send_json({
                "ebay_live": ebay_live(),
                "stripe_live": stripe_live(),
                "shippo_live": shippo_live(),
                "ebay_store_url": f"https://www.ebay.com/usr/{seller}" if seller
                                  else "https://www.ebay.com",
            })
            return

        if path == "/api/listings":
            if ebay_live():
                items, err = fetch_ebay_listings()
                if err:
                    print("[ebay]", err)
                    self.send_json({"demo": False, "error":
                                    "Could not reach eBay right now.", "items": []})
                    return
                self.send_json({"demo": False, "items": items})
            else:
                self.send_json({"demo": True, "items": DEMO_LISTINGS})
            return

        if path == "/api/store":
            self.send_json({"stripe_live": stripe_live(),
                            "items": read_inventory()})
            return

        if path == "/api/orders":
            admin = CFG.get("ADMIN_KEY")
            if admin and qs.get("key", [""])[0] != admin:
                self.send_json({"error": "unauthorized"}, 401)
                return
            self.send_json({"orders": read_orders()})
            return

        m = re.fullmatch(r"/label/([0-9a-f]{12})", path)
        if m:
            self.serve_mock_label(m.group(1))
            return

        m = re.fullmatch(r"/print/([0-9a-f]{12})", path)
        if m:
            self.serve_print_page(m.group(1))
            return

        self.serve_static(path)

    def send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_mock_label(self, order_id):
        """Raw 4x6 demo label (no toolbar) — the demo equivalent of a Shippo file."""
        order = next((o for o in read_orders() if o["id"] == order_id), None)
        if not order:
            self.send_json({"error": "not found"}, 404)
            return
        self.send_html(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Demo Shipping Label</title><style>{LABEL_CSS}
@media screen {{ body {{ background:#333; }}
  .lbl {{ margin:16px auto; box-shadow:0 0 12px rgba(0,0,0,.5); }} }}
</style></head><body>{demo_label_html(order)}</body></html>""")

    def serve_print_page(self, order_id):
        """4x6 zero-margin print page that auto-opens the print dialog.

        Works for both demo (HTML) and live (Shippo PNG/PDF) labels; the label
        is stretched to fill the entire 4x6 sheet so it maps 1:1 onto Rollo
        media regardless of the browser's default paper size or scaling.
        """
        order = next((o for o in read_orders() if o["id"] == order_id), None)
        if not order:
            self.send_json({"error": "not found"}, 404)
            return
        label = order.get("label") or {}
        url = label.get("label_url") or ""
        if url.startswith("/label/"):
            sheet = demo_label_html(order)  # demo label already fills 4x6
        elif url.lower().endswith(".pdf"):
            sheet = f'<iframe class="fill" src="{url}"></iframe>'
        elif url:
            sheet = f'<img class="fill" src="{url}" alt="Shipping label">'
        else:
            self.send_json({"error": "no label on this order"}, 404)
            return
        self.send_html(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Print 4x6 label</title><style>{LABEL_CSS}
  .fill {{ width: 4in; height: 6in; display: block; border: 0;
           object-fit: contain; }}
  @media screen {{
    body {{ background:#333; font-family:Arial,Helvetica,sans-serif; }}
    .bar {{ color:#fff; text-align:center; padding:14px; font-size:14px; }}
    .bar b {{ color:#f0c96b; }}
    .bar button {{ background:#f0c96b; border:0; color:#071527; font-weight:700;
      padding:.5rem 1.1rem; border-radius:6px; cursor:pointer; margin-left:.6rem; }}
    .lbl, .fill {{ margin:0 auto; box-shadow:0 0 12px rgba(0,0,0,.5); }}
  }}
  @media print {{ .bar {{ display:none; }} }}
</style></head><body>
<div class="bar">Set the printer to <b>Rollo</b> · paper <b>4&quot;&nbsp;×&nbsp;6&quot;</b> · scale <b>100% / Actual size</b>, margins <b>None</b>.
  <button onclick="window.print()">Print</button></div>
{sheet}
<script>window.addEventListener('load',function(){{setTimeout(function(){{window.print();}},500);}});</script>
</body></html>""")

    # ---- POST
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        raw = self.read_body()

        if path == "/api/checkout":
            self.handle_checkout(raw)
        elif path == "/api/demo-checkout":
            self.handle_demo_checkout(raw)
        elif path == "/api/stripe-webhook":
            self.handle_webhook(raw)
        else:
            self.send_json({"error": "not found"}, 404)

    def handle_checkout(self, raw):
        if not stripe_live():
            self.send_json({"demo": True,
                            "message": "Stripe not configured — use demo checkout."})
            return
        try:
            item_id = json.loads(raw)["item_id"]
        except Exception:
            self.send_json({"error": "bad request"}, 400)
            return
        item = next((i for i in read_inventory()
                     if i["id"] == item_id and not i.get("sold")), None)
        if not item:
            self.send_json({"error": "item not available"}, 404)
            return
        session, err = create_stripe_session(item)
        if err:
            print("[stripe]", err)
            self.send_json({"error": "checkout could not be created"}, 502)
            return
        self.send_json({"url": session["url"]})

    def handle_demo_checkout(self, raw):
        try:
            data = json.loads(raw)
            item_id = data["item_id"]
            shipping = data["shipping"]
        except Exception:
            self.send_json({"error": "bad request"}, 400)
            return
        missing = [k for k in REQUIRED_SHIP_FIELDS if not str(shipping.get(k, "")).strip()]
        if missing:
            self.send_json({"error": f"missing fields: {', '.join(missing)}"}, 400)
            return
        item = next((i for i in read_inventory() if i["id"] == item_id), None)
        if not item:
            self.send_json({"error": "item not found"}, 404)
            return
        order = make_order(item, shipping, None, live=False, payment="demo (no charge)")
        order["label"] = mock_label(order["id"])
        save_order(order)
        self.send_json({"ok": True, "order_id": order["id"],
                        "tracking": order["label"]["tracking_number"],
                        "label_url": order["label"]["label_url"]})

    def handle_webhook(self, raw):
        sig = self.headers.get("Stripe-Signature", "")
        if not verify_stripe_signature(raw, sig):
            self.send_json({"error": "bad signature"}, 400)
            return
        event = json.loads(raw)
        if event.get("type") != "checkout.session.completed":
            self.send_json({"received": True})
            return
        session = event["data"]["object"]
        details = session.get("shipping_details") or session.get("customer_details") or {}
        addr = details.get("address") or {}
        shipping = {
            "name": details.get("name", ""),
            "street1": addr.get("line1", ""),
            "street2": addr.get("line2") or "",
            "city": addr.get("city", ""),
            "state": addr.get("state", ""),
            "zip": addr.get("postal_code", ""),
            "country": addr.get("country", "US"),
            "email": (session.get("customer_details") or {}).get("email", ""),
        }
        meta = session.get("metadata", {})
        item = {"id": meta.get("item_id"), "title": meta.get("item_title"),
                "price": (session.get("amount_total") or 0) / 100}
        order = make_order(item, shipping, None, live=True, payment="stripe")
        if shippo_live():
            label, err = buy_shippo_label(
                {**shipping, "phone": "0000000000"},
                int(float(meta.get("weight_oz", 4))))
            if err:
                print("[shippo]", err)
                order["label"] = {"error": err}
            else:
                order["label"] = label
        else:
            order["label"] = mock_label(order["id"])
        save_order(order)
        self.send_json({"received": True})


if __name__ == "__main__":
    print(f"Patriotic Card Collector server -> http://localhost:{PORT}")
    print(f"  eBay listings : {'LIVE' if ebay_live() else 'DEMO (add eBay keys)'}")
    print(f"  Stripe payments: {'LIVE' if stripe_live() else 'DEMO (add Stripe key)'}")
    print(f"  Shippo labels : {'LIVE' if shippo_live() else 'DEMO (add Shippo key)'}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
