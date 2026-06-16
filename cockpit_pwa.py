#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cockpit WeNeed — PWA avec notifications push.
Lancement :  python3 cockpit.py
Ouvrir     :  http://localhost:5001
"""
import json, ssl, os, threading, datetime as dt, urllib.request, re, time, base64
from flask import Flask, jsonify, request, make_response
from pywebpush import webpush, WebPushException
from py_vapid import Vapid

# ------------------------------------------------------------------ CONFIG
ODOO_URL = "https://weneedweed.odoo.com"
DB, UID, PASSWORD = "weneedweed", 13, "!Gotierdu31500"
LOGIN = "ah@weneedweed.eu"
PORT = 5001
DEMO = os.environ.get("COCKPIT_DEMO") == "1"
TABELLA_SNAPSHOT = "12/06/2026"
_ctx = ssl._create_unverified_context()
COCKPIT_DIR = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ VAPID KEYS
VAPID_FILE = os.path.join(COCKPIT_DIR, ".vapid_keys.json")
SUBS_FILE = os.path.join(COCKPIT_DIR, ".push_subs.json")
VAPID_EMAIL = "mailto:ah@weneedweed.eu"

def _load_or_create_vapid():
    if os.path.exists(VAPID_FILE):
        with open(VAPID_FILE) as f:
            return json.load(f)
    v = Vapid()
    v.generate_keys()
    raw_priv = v.private_pem()
    raw_pub = v.public_key
    # Encode public key as URL-safe base64 (applicationServerKey format)
    import cryptography.hazmat.primitives.serialization as ser
    pub_bytes = raw_pub.public_bytes(ser.Encoding.X962, ser.PublicFormat.UncompressedPoint)
    pub_b64 = base64.urlsafe_b64encode(pub_bytes).decode().rstrip("=")
    priv_pem = raw_priv.decode() if isinstance(raw_priv, bytes) else raw_priv
    keys = {"public": pub_b64, "private_pem": priv_pem}
    with open(VAPID_FILE, "w") as f:
        json.dump(keys, f)
    print("🔑 Clés VAPID générées →", VAPID_FILE)
    return keys

VAPID_KEYS = _load_or_create_vapid()

def _load_subs():
    if os.path.exists(SUBS_FILE):
        with open(SUBS_FILE) as f:
            return json.load(f)
    return []

def _save_subs(subs):
    with open(SUBS_FILE, "w") as f:
        json.dump(subs, f)

push_subs = _load_subs()

# ------------------------------------------------------------------ BAREME
OH_A, OH_B = 0.25, 0.15
A_K1, A_K2 = 0.15, 0.80
A_P0, A_P1, A_P2 = 0.20, 0.2321, 0.30
B_KMAX, B_PMIN, B_PMAX = 1.0, 0.22254, 0.30

COST_TABLE = {
    "APS/I": ("A",1.6),"BA/G": ("A",0.75),"BB/H": ("A",1.13),"BUB/G": ("B",0.57),
    "CB/H": ("A",1.0),"CH/H": ("A",0.65),"CO/C": ("A",2.0),"DI/H": ("B",0.6),
    "DS/H": ("A",0.6),"FO/I": ("A",1.3),"FO/I/S": ("A",0.3),"GFO/I": ("A",1.45),
    "GLC/G": ("B",0.65),"GLC/I": ("A",1.45),"GPF/I": ("A",1.6),"GZ/I": ("A",1.4),
    "GZ/I/S": ("A",0.35),"IC/H": ("A",1.0),"JL/H": ("A",1.0),"LB/H": ("A",0.7),
    "LB/I": ("A",1.3),"LB/I/S": ("A",0.35),"LC/H": ("B",0.3),"LP/I": ("A",1.4),
    "LS/I": ("A",1.35),"LS/I/S": ("A",0.35),"MI/H": ("B",0.6),"MP/I": ("B",1.6),
    "MP/I/S": ("A",0.35),"MS/I": ("A",1.3),"MS/I/S": ("A",0.35),"MS/O": ("A",0.4),
    "MU/H": ("B",0.3),"OM/I": ("A",1.3),"OM/I/S": ("A",0.35),"PE/G": ("B",0.45),
    "PR/H": ("A",0.6),"Pre Rolled": ("A",0.3),"PT/H": ("B",0.6),"RL/H": ("B",0.5),
    "SA/I": ("A",1.4),"SA/I/S": ("A",0.35),"SB/I": ("A",1.4),"SBE/G": ("B",0.48),
    "SBO/G": ("B",0.57),"SBO/I": ("A",1.45),"SC/I": ("A",1.5),"SC/I/S": ("A",0.35),
    "SD/I": ("A",1.3),"SD/I/S": ("A",0.35),"SH/G": ("B",0.48),"SH/G/S": ("B",0.2),
    "SL/I": ("A",1.6),"SL/I/S": ("A",0.35),"SM/H": ("A",1.0),"SP/I": ("A",1.3),
    "SP/I/S": ("A",0.35),"SQ/I": ("A",1.4),"SQ/I/S": ("A",0.3),"SR/H": ("A",1.0),
    "TB/H": ("A",0.9),"TK/I": ("A",1.4),"TK/I/S": ("A",0.35),"TRIM/L": ("A",0.1),
    "TRIM/T": ("A",0.1),"UR/I": ("A",1.4),"WX/H": ("A",2.0),"CRB/G": ("B",0.35),
    "CRB/G/S": ("B",0.15),"DQF/I": ("A",1.6),"SWZ/I": ("A",1.6),"SOT/G": ("B",0.48),
    "SOT/G/S": ("B",0.15),"MKP/G": ("B",0.57),"BRP/G": ("B",0.57),"BC/I": ("A",1.5),
    "BC/I/S": ("A",0.35),"IC/I": ("A",1.2),"STP/I": ("A",1.6),"BB/I": ("B",0.9),
    "SS/I": ("B",0.9),"SY/I": ("B",0.9),"SE/I": ("B",0.9),"MP/H": ("B",0.65),
    "FF/H": ("B",0.7),"SC/H": ("B",0.3),"AG/H": ("A",1.0),"SG/I": ("A",1.5),
    "SG/I/S": ("A",0.35),"TA/I": ("A",1.3),"TA/I/S": ("A",0.35),"WR/I": ("B",1.65),
    "GH/I": ("A",1.18),"RU/I": ("A",1.18),"ALM/G": ("A",0.48),"KK/G": ("B",0.4),
    "DSD/I": ("A",1.45),"GRC/G": ("B",0.68),"SP/H": ("B",0.8),"TD/I": ("B",1.4),
    "SY/O": ("B",0.2),"LA/H": ("B",0.35),"BK/I": ("A",1.3),"BK/I/S": ("A",0.35),
    "BR/CP/50-TR": ("A",550),"CD/TR/250": ("A",450),"CD/TR/50": ("A",110),
    "CD/S/TR/50": ("A",40),"CC/TR/250": ("A",450),"DI/H/TR/100": ("B",100),
    "GP/TR/250": ("A",450),"GP/TR/50": ("A",110),"GP/TR/S/250": ("A",200),
    "GP/TR/S/50": ("A",40),"GH/H/TR/100": ("B",80),"LF/CP/250-TR": ("A",250),
    "LF/CP/50-TR": ("A",50),"MD/H/TR/100": ("B",100),"MU/H/TR/100": ("B",80),
    "PT/H/TR/100": ("B",120),"SH/H/TR/100": ("A",150),"RL/H/TR/100": ("B",80),
    "PU/TR/250": ("A",450),"SF/TR/250": ("A",250),"SC/CS/250-TR": ("A",450),
    "BR/CP/250-TR": ("A",450),"BP/G/TR/250": ("A",250),"BP/G/TR/50": ("A",50),
    "SF/TR/50": ("A",50),"LP/TR/250": ("A",312.5),"LP/TR/50": ("A",62.5),
    "MS/TR/250": ("A",312.5),"MS/TR/50": ("A",62.5),"BR/H/TR/100": ("B",70),
    "PU/TR/50": ("A",90),"LE/G/TR/250": ("A",312.5),"LE/G/TR/50": ("A",62.5),
    "MMP/H/TR/50": ("B",50),"SPP/H/TR/50": ("B",50),"DV/JB": ("A",500),
    "DV/NA/ZK/25": ("B",150),"DV/NA/GE/25": ("B",150),"DV/NA/CK/25": ("B",150),
    "LO/TR/250": ("B",325),"LO/TR/50": ("B",65),"RO/TR/250": ("B",325),
    "RO/TR/50": ("B",65),"RC/TR/250": ("B",325),"RC/TR/50": ("B",65),
    "PS/TR/250": ("B",325),"PS/TR/50": ("B",65),"TRIM/TR/500": ("A",125),
    "FF/TR/250": ("B",312.5),"GH/TR/250": ("B",312.5),"BU/H/TR/100": ("B",70),
    "SC/TR/250": ("A",450),"SC/TR/50": ("A",90),"GH/TR/50": ("B",62.5),
    "RU/TR/250": ("B",312.5),"RU/TR/50": ("B",62.5),"WB/TR/250": ("A",450),
    "FF/TR/50": ("B",62.5),"CHP/G/TR/250": ("B",312.5),"CHP/G/TR/50": ("B",62.5),
    "SM/TR/250": ("B",450),"SM/TR/50": ("B",90),"SM/S/TR/250": ("B",200),
    "SM/S/TR/50": ("B",40),"CB/G/S/TR/250": ("B",100),"FF/H/TR/100": ("B",100),
    "TD/TR/250": ("B",312.5),"TD/TR/50": ("B",62.5),"CB/G/S/TR/50": ("B",20),
    "BK/G/S/TR/250": ("B",100),"BK/G/S/TR/50": ("B",20),"WB/TR/50": ("A",90),
    "SC/G/TR/250": ("B",312.5),"SC/G/TR/50": ("B",62.5),"SK/TR/250": ("A",450),
    "SK/TR/50": ("A",90),"CC/G/TR/250": ("B",312.5),"CC/G/TR/50": ("B",62.5),
    "SL/G/S/TR/250": ("B",100),"SL/G/S/TR/50": ("B",20),"OGI/H/TR/100": ("B",100),
    "BG/TR/250": ("A",425),"BG/TR/50": ("A",85),"PO/H/TR/100": ("B",120),
    "AC/H/TR/100": ("B",120),"AB/TR/250": ("A",325),"AB/TR/50": ("A",65),
    "BM/H/TR/100": ("B",80),"SB/H/TR/100": ("B",80),"SK/250-TR": ("A",500),
}

def _payout_A(k):
    if k <= 0: return 0.0
    if k < A_K1: return A_P0 + (k/A_K1)*(A_P1-A_P0)
    if k < A_K2: return A_P1 + (k-A_K1)/(A_K2-A_K1)*(A_P2-A_P1)
    return A_P2
def _payout_B(k):
    if k <= 0: return 0.0
    return B_PMIN + min(k, B_KMAX)*(B_PMAX-B_PMIN)

def line_commission(sku, qty, price):
    info = COST_TABLE.get(sku)
    if info is None: return 0.0, None, "missing"
    serie, cost = info
    if not qty or not price or cost is None: return 0.0, serie, "ok"
    oh = OH_A if serie == "A" else OH_B
    m = price - cost*(1+oh)
    if m <= 0: return 0.0, serie, "ok"
    k = m / cost
    p = _payout_A(k) if serie == "A" else _payout_B(k)
    return p*m*qty, serie, "ok"

# ------------------------------------------------------------------ ODOO RPC
def odoo(model, action, args, kw=None):
    payload = {"jsonrpc":"2.0","method":"call","params":{"service":"object","method":"execute_kw",
        "args":[DB,UID,PASSWORD,model,action,args] + ([kw] if kw else [])}}
    req = urllib.request.Request(ODOO_URL+"/jsonrpc", data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_ctx) as resp:
            result = json.loads(resp.read().decode())
            return result.get("result")
    except Exception as e:
        print(f"⚠️  Odoo error: {e}"); return None

def load_data():
    global D, load_ts
    load_ts = dt.datetime.now()
    try:
        today = dt.date.today()
        month_start = today.replace(day=1)
        orders = odoo("sale.order", "search_read", [
            [["date_order",">=",month_start.isoformat()],["state","in",["sale","done"]]],
        ], {"fields":["name","date_order","state","order_line"]}) or []
        print(f"📊 {len(orders)} commandes trouvées")
        D["orders"] = []
        D["products"] = {}
        D["stock"] = []
        for o in orders:
            ol = o.get("order_line") or []
            lines = odoo("sale.order.line", "search_read", [[["id","in",ol]]],
                {"fields":["product_id","product_uom_qty","price_unit"]}) or []
            for l in lines:
                pid = l.get("product_id")
                if not pid: continue
                p = odoo("product.product", "read", [[pid[0]]],
                    {"fields":["default_code","name","list_price"]}) or [{}]
                p = p[0] if p else {}
                sku = p.get("default_code","?")
                name = p.get("name","")
                qty = l.get("product_uom_qty") or 0
                price = l.get("price_unit") or 0
                comm, serie, st = line_commission(sku, qty, price)
                D["orders"].append({"sku":sku,"name":name,"qty":qty,"price":price,"comm":comm,"serie":serie,"status":st})
                if sku not in D["products"]:
                    D["products"][sku] = {"name":name,"sku":sku,"serie":serie,"qty":0,"ca":0,"comm":0,"missing":st=="missing"}
                D["products"][sku]["qty"] += qty
                D["products"][sku]["ca"] += qty*price
                D["products"][sku]["comm"] += comm
        prods = odoo("product.product", "search_read", [],
            {"fields":["default_code","name","qty_available","virtual_available"]}) or []
        for p in prods:
            sku = p.get("default_code","")
            if sku and (p.get("qty_available") or p.get("virtual_available")):
                serie = "B" if "TR" in sku else "A"
                D["stock"].append({
                    "sku":sku,"name":p.get("name",""),"serie":serie,
                    "onHand":int(p.get("qty_available") or 0),
                    "free":int(p.get("virtual_available") or 0)
                })
        print(f"✅ {len(D['orders'])} lignes, {len(D['products'])} produits uniques, {len(D['stock'])} stocks")
    except Exception as e:
        print(f"❌ Load error: {e}")

# ------------------------------------------------------------------ PUSH NOTIFICATIONS
def send_push(title, body, url="/"):
    global push_subs
    dead = []
    for i, sub in enumerate(push_subs):
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps({"title": title, "body": body, "url": url}),
                vapid_private_key=VAPID_KEYS["private_pem"],
                vapid_claims={"sub": VAPID_EMAIL}
            )
            print(f"📤 Push envoyé: {title}")
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                dead.append(i)
                print(f"🗑️ Subscription expirée, supprimée")
            else:
                print(f"⚠️ Push error: {e}")
        except Exception as e:
            print(f"⚠️ Push error: {e}")
    if dead:
        push_subs = [s for i, s in enumerate(push_subs) if i not in dead]
        _save_subs(push_subs)

# ------------------------------------------------------------------ STOCK MONITOR
prev_stock = {}
MONITOR_INTERVAL = 300  # 5 minutes

def stock_monitor():
    global prev_stock
    print("👀 Stock monitor démarré (check toutes les 5 min)")
    time.sleep(30)  # attendre le premier load
    while True:
        try:
            prods = odoo("product.product", "search_read", [],
                {"fields":["default_code","name","qty_available","virtual_available"]}) or []
            alerts = []
            for p in prods:
                sku = p.get("default_code","")
                if not sku: continue
                free = int(p.get("virtual_available") or 0)
                was_zero = prev_stock.get(sku, 0) <= 0
                now_avail = free > 0
                if was_zero and now_avail:
                    name = p.get("name", sku)
                    alerts.append(f"✅ {name} ({sku}) — {free}g dispo!")
                prev_stock[sku] = free
            if alerts and push_subs:
                for a in alerts[:5]:  # max 5 alerts à la fois
                    send_push("🚨 Stock dispo!", a, "/?tab=stock")
                    time.sleep(1)
            elif alerts:
                for a in alerts[:5]:
                    print(f"🔔 ALERT (pas d'abonné push): {a}")
        except Exception as e:
            print(f"⚠️ Monitor error: {e}")
        time.sleep(MONITOR_INTERVAL)

# ------------------------------------------------------------------ FLASK APP
app = Flask(__name__)
D = {"orders":[],"products":{},"stock":[]}
load_ts = None

@app.route("/api/data")
def api_data():
    return jsonify({"orders":D["orders"],"products":list(D["products"].values()),"stock":D["stock"],"ts":load_ts.isoformat() if load_ts else None})

@app.route("/api/reload", methods=["POST"])
def api_reload():
    threading.Thread(target=load_data, daemon=True).start()
    return jsonify({"ok":True})

@app.route("/api/vapid-key")
def api_vapid_key():
    return jsonify({"publicKey": VAPID_KEYS["public"]})

@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    global push_subs
    sub = request.json
    if sub and sub not in push_subs:
        push_subs.append(sub)
        _save_subs(push_subs)
        print(f"🔔 Nouvel abonné push! Total: {len(push_subs)}")
    return jsonify({"ok": True, "count": len(push_subs)})

@app.route("/api/test-push", methods=["POST"])
def api_test_push():
    if not push_subs:
        return jsonify({"ok": False, "error": "Aucun abonné push"})
    send_push("🧪 Test Cockpit WeNeed", "Les notifications fonctionnent! 🎉", "/")
    return jsonify({"ok": True})

@app.route("/manifest.json")
def manifest():
    m = {
        "name": "Cockpit WeNeed",
        "short_name": "Cockpit",
        "description": "Dashboard commissions & stock WeNeed",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0a0a0a",
        "theme_color": "#4ade80",
        "icons": [
            {"src": "/icon-192.svg", "sizes": "192x192", "type": "image/svg+xml"},
            {"src": "/icon-512.svg", "sizes": "512x512", "type": "image/svg+xml"}
        ]
    }
    resp = make_response(json.dumps(m))
    resp.headers["Content-Type"] = "application/manifest+json"
    return resp

@app.route("/icon-192.svg")
@app.route("/icon-512.svg")
def icon():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
    <rect width="512" height="512" rx="100" fill="#0a0a0a"/>
    <text x="256" y="300" font-size="280" text-anchor="middle" fill="#4ade80">🚀</text>
    </svg>'''
    resp = make_response(svg)
    resp.headers["Content-Type"] = "image/svg+xml"
    return resp

@app.route("/sw.js")
def service_worker():
    sw = '''
const CACHE_NAME = "cockpit-v1";

self.addEventListener("install", e => {
    self.skipWaiting();
});

self.addEventListener("activate", e => {
    e.waitUntil(clients.claim());
});

self.addEventListener("push", e => {
    let data = {title: "Cockpit WeNeed", body: "Nouvelle alerte", url: "/"};
    try { data = e.data.json(); } catch(err) {}
    e.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: "/icon-192.svg",
            badge: "/icon-192.svg",
            vibrate: [200, 100, 200],
            data: {url: data.url || "/"},
            actions: [{action: "open", title: "Ouvrir"}]
        })
    );
});

self.addEventListener("notificationclick", e => {
    e.notification.close();
    const url = e.notification.data.url || "/";
    e.waitUntil(
        clients.matchAll({type: "window"}).then(list => {
            for (const c of list) {
                if (c.url.includes(url) && "focus" in c) return c.focus();
            }
            return clients.openWindow(url);
        })
    );
});
'''
    resp = make_response(sw)
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp

@app.route("/")
def index():
    return '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Cockpit WeNeed</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#4ade80">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Cockpit WeNeed">
    <link rel="apple-touch-icon" href="/icon-192.svg">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        :root { --bg:#0a0a0a; --fg:#f0f0f0; --sub:#888; --a:#4ade80; --red:#ef4444; --amb:#f59e0b; --grn:#10b981; --fi:#666; }
        html { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--fg); }
        body { padding:12px; padding-bottom:80px; }
        .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; flex-wrap:wrap; gap:8px; }
        h1 { font-size:22px; font-weight:700; }
        .topbtns { display:flex; gap:6px; }
        .reload { background:var(--a); color:#000; border:none; padding:8px 14px; border-radius:4px; cursor:pointer; font-weight:600; font-size:13px; }
        .notifbtn { background:#1a1a1a; color:var(--fg); border:1px solid var(--fi); padding:8px 14px; border-radius:4px; cursor:pointer; font-size:13px; }
        .notifbtn.on { background:#4ade80; color:#000; border-color:#4ade80; }
        .tabs { display:flex; gap:8px; margin-bottom:16px; border-bottom:1px solid var(--fi); }
        .tab { padding:8px 16px; cursor:pointer; border:none; background:none; color:var(--sub); font-weight:500; border-bottom:2px solid transparent; }
        .tab.active { color:var(--fg); border-bottom-color:var(--a); }
        .content { margin-top:16px; }
        .empty { text-align:center; padding:40px; color:var(--sub); }
        table { width:100%; border-collapse:collapse; font-size:13px; }
        th { text-align:left; padding:8px; color:var(--sub); font-weight:600; border-bottom:1px solid var(--fi); }
        td { padding:8px; border-bottom:1px solid #1a1a1a; }
        tr:hover { background:rgba(255,255,255,.02); }
        .right { text-align:right; }
        .b { font-weight:600; }
        .chip { display:inline-block; padding:2px 8px; background:var(--fi); color:var(--bg); border-radius:3px; font-size:11px; margin-right:4px; }
        .chip.tr { background:#c084fc; }
        .chip.gta { background:#3b82f6; }
        .controls { display:flex; gap:8px; margin-bottom:12px; flex-wrap:wrap; }
        .search { flex:1; min-width:200px; padding:8px; background:#1a1a1a; border:1px solid var(--fi); color:var(--fg); border-radius:4px; }
        select { padding:8px; background:#1a1a1a; border:1px solid var(--fi); color:var(--fg); border-radius:4px; }
        .fchip { display:inline-block; padding:4px 12px; margin-right:4px; margin-bottom:4px; background:#1a1a1a; border:1px solid var(--fi); border-radius:4px; cursor:pointer; font-size:12px; }
        .fchip.on { background:var(--a); color:#000; border-color:var(--a); }
        .stat { padding:12px; background:#1a1a1a; border-radius:4px; }
        .stat.warn { background:rgba(239,68,68,.1); border:1px solid rgba(239,68,68,.2); }
        .stat .k { font-size:12px; color:var(--sub); }
        .stat .v { font-size:20px; font-weight:700; margin:4px 0; }
        .stat .s { font-size:11px; color:var(--fi); }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-bottom:12px; }
        .track { margin-top:12px; padding:8px; background:#1a1a1a; border-radius:4px; font-size:12px; color:var(--sub); }
        .note { margin:12px 0; padding:8px 12px; background:rgba(59,130,246,.08); color:#60a5fa; border:1px solid rgba(59,130,246,.2); border-radius:4px; font-size:12px; }
        .tw { overflow-x:auto; }
        .clk { cursor:pointer; }
        .detail { margin-top:12px; }
        .missing-dot { display:inline-block; width:8px; height:8px; background:var(--red); border-radius:50%; margin-left:4px; }
        .frow { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:8px; }
        .flab { font-size:12px; color:var(--sub); font-weight:600; }
        .sortbtn { padding:4px 12px; background:#1a1a1a; border:1px solid var(--fi); border-radius:4px; cursor:pointer; font-size:12px; }
        .sortsel { padding:4px 8px; }
        .sortable { cursor:pointer; user-select:none; }
        .sortable:hover { color:var(--a); }
        .toast { position:fixed; bottom:20px; left:50%; transform:translateX(-50%); background:#333; color:#fff; padding:10px 20px; border-radius:8px; font-size:13px; z-index:999; display:none; }
    </style>
</head>
<body>
<div class="top">
    <h1>🚀 Cockpit WeNeed</h1>
    <div class="topbtns">
        <button class="notifbtn" id="notifBtn" onclick="toggleNotif()">🔔 Notifs</button>
        <button class="reload" onclick="reloadData()">↻ Actualiser</button>
    </div>
</div>
<div class="tabs">
    <button class="tab active" onclick="switchTab('commandes')">Commandes</button>
    <button class="tab" onclick="switchTab('produits')">Produits</button>
    <button class="tab" onclick="switchTab('stock')">Stock</button>
</div>
<div class="content" id="content"></div>
<div class="toast" id="toast"></div>
<script>
/* ===== PWA + PUSH ===== */
let swReg=null, pushSub=null;

function toast(msg,ms){const t=document.getElementById("toast");t.textContent=msg;t.style.display="block";setTimeout(()=>t.style.display="none",ms||3000);}

function urlB64ToUint8Array(b64){const p="=".repeat((4-b64.length%4)%4);const r=atob((b64+p).replace(/-/g,"+").replace(/_/g,"/"));const a=new Uint8Array(r.length);for(let i=0;i<r.length;i++)a[i]=r.charCodeAt(i);return a;}

async function initPWA(){
    if(!("serviceWorker" in navigator)){console.log("SW not supported");return;}
    try{
        swReg=await navigator.serviceWorker.register("/sw.js");
        console.log("✅ Service Worker enregistré");
        const sub=await swReg.pushManager.getSubscription();
        if(sub){pushSub=sub;updateNotifBtn(true);console.log("✅ Push déjà abonné");}
    }catch(e){console.error("SW error:",e);}
}

async function toggleNotif(){
    if(!swReg){toast("Service Worker pas prêt");return;}
    if(pushSub){
        // Désabonner
        await pushSub.unsubscribe();
        pushSub=null;
        updateNotifBtn(false);
        toast("🔕 Notifications désactivées");
        return;
    }
    // S'abonner
    try{
        const perm=await Notification.requestPermission();
        if(perm!=="granted"){toast("❌ Permission refusée");return;}
        const r=await fetch("/api/vapid-key");
        const{publicKey}=await r.json();
        pushSub=await swReg.pushManager.subscribe({
            userVisibleOnly:true,
            applicationServerKey:urlB64ToUint8Array(publicKey)
        });
        await fetch("/api/subscribe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(pushSub.toJSON())});
        updateNotifBtn(true);
        toast("🔔 Notifications activées!");
        // Test
        setTimeout(()=>fetch("/api/test-push",{method:"POST"}),2000);
    }catch(e){console.error("Push sub error:",e);toast("❌ Erreur: "+e.message);}
}

function updateNotifBtn(on){
    const b=document.getElementById("notifBtn");
    if(on){b.className="notifbtn on";b.textContent="🔔 Notifs ON";}
    else{b.className="notifbtn";b.textContent="🔕 Notifs";}
}

// Check tab param from notification click
const urlParams=new URLSearchParams(window.location.search);
if(urlParams.get("tab"))currentTab=urlParams.get("tab");

initPWA();

/* ===== DATA ===== */
let D={}, PF={ent:"all",q:"",op:null}, SF={gta:true,tr:true,fleur:true,hash:true,sample:false,bag:false,hideZero:false,q:"",sortKey:"free",asc:false};
async function load(){
  const r=await fetch("/api/data");
  D=await r.json();
  render();
}
function reloadData(){const btn=event.target;btn.disabled=true;fetch("/api/reload",{method:"POST"}).then(()=>{setTimeout(load,1000);btn.disabled=false;});}
let currentTab="commandes";
function switchTab(t){currentTab=t;document.querySelectorAll(".tab").forEach((b,i)=>{b.className="tab"+(["commandes","produits","stock"][i]===t?" active":"");});render();}
function render(){
  const html=currentTab==="commandes"?vCommandes():currentTab==="produits"?vProduits():vStock();
  document.getElementById("content").innerHTML=html;
}
function esc(s){const d=document.createElement("div");d.textContent=s;return d.innerHTML;}
function eur(v,d){return(v||0).toFixed(d||0).replace(/\\B(?=(\\d{3})+(?!\\d))/g," ").replace(" ","\\u00A0");}
function avgPriceStr(p){if(!p.qty)return "—";return(p.ca/p.qty).toFixed(2)+" €/g";}
function vCommandes(){
  const os=(D.orders||[]);
  if(!os.length)return"<div class='empty'>Aucune commande ce mois</div>";
  let h="<div class='tw'><table><thead><tr><th>SKU</th><th>Produit</th><th class='right'>Qté</th><th class='right'>PU</th><th class='right'>CA</th><th class='right'>Commission</th></tr></thead><tbody>";
  let totCA=0,totComm=0;
  for(const o of os){h+="<tr><td><span class='chip "+(o.serie==="B"?"tr":"gta")+"'>"+esc(o.sku)+"</span></td><td>"+esc(o.name||"?")+"</td><td class='right'>"+o.qty+"</td><td class='right'>"+eur(o.price,2)+"</td><td class='right'>"+eur(o.qty*o.price)+"</td><td class='right b' style='color:var(--a)'>"+eur(o.comm,2)+"</td></tr>";totCA+=o.qty*o.price;totComm+=o.comm;}
  h+="</tbody></table></div><div class='grid' style='margin-top:12px'><div class='stat'><div class='k'>CA total</div><div class='v'>"+eur(totCA)+"</div></div><div class='stat'><div class='k'>Commission total</div><div class='v' style='color:var(--a)'>"+eur(totComm,2)+"</div></div></div>";
  return h;
}
function prodDetail(p){
  let h="<div style='color:var(--sub);font-size:11px;margin-bottom:6px'>"+esc(p.sku)+(p.plName?" · pricelist: "+esc(p.plName):"")+"</div>";
  const ton=p.ca/p.qty;
  if(p.serie==="A"){
    h+="<div style='color:var(--fi);font-size:11px;margin-bottom:6px'>Fleur — tarification €/g</div>";
    h+="<table class='detail'><thead><tr><th>Palier</th><th class='right'>Prix /g</th><th class='right'>Commission</th></tr></thead><tbody>";
    for(const t of (p.plTiers||[])){
      const col=ton?(ton>=t.ppg?"var(--grn)":"var(--amb)"):"inherit";
      h+="<tr><td>"+t.q.toLocaleString("fr-FR")+" g+</td><td class='right' style='color:"+col+"'>"+t.ppg.toFixed(2)+" €/g</td><td class='right b' style='color:var(--a)'>"+eur(t.comm,2)+"</td></tr>";
    }
    h+="</tbody></table>";
    if(ton)h+="<div class='track'>Ton prix moyen pratiqué : <span class='b'>"+ton.toFixed(2)+" €/g</span></div>";
  }else{
    const ug=p.unitG||250;
    h+="<div style='color:var(--fi);font-size:11px;margin-bottom:6px'>Unité = "+ug+" g · commission par unité</div>";
    h+="<table class='detail'><thead><tr><th>Palier</th><th class='right'>Prix /g</th><th class='right'>Prix unité</th><th class='right'>Comm. /unité</th></tr></thead><tbody>";
    for(const t of (p.plTiers||[])){
      const col=ton?(ton>=t.unit?"var(--grn)":"var(--amb)"):"inherit";
      h+="<tr><td>"+t.q.toLocaleString("fr-FR")+" g+</td><td class='right'>"+t.ppg.toFixed(2)+" €</td><td class='right' style='color:"+col+"'>"+eur(t.unit)+"</td><td class='right b' style='color:var(--a)'>"+eur(t.comm,2)+"</td></tr>";
    }
    h+="</tbody></table>";
    if(ton)h+="<div class='track'>Ton prix moyen pratiqué : <span class='b'>"+Math.round(ton).toLocaleString("fr-FR")+" €/unité</span></div>";
  }
  h+="</div>";
  return h;
}
function pfToggle(sku){PF.op=PF.op===sku?null:sku;render();}
function vProduits(){
  const list=D.products.filter(p=>(PF.ent==="all"||p.serie===PF.ent)&&((p.name||"")+" "+p.sku).toLowerCase().includes(PF.q.toLowerCase()));
  const opt=(v,c,l)=>"<option value='"+v+"'"+(c===v?" selected":"")+">"+l+"</option>";
  let h="<div class='controls'><input class='search' placeholder='Rechercher nom ou SKU…' value='"+esc(PF.q)+"' oninput='PF.q=this.value;rfp()'><select onchange='PF.ent=this.value;render()'>"+opt("all",PF.ent,"Toutes gammes")+opt("A",PF.ent,"Série A (GTA)")+opt("B",PF.ent,"Série B (TR)")+"</select></div>";
  h+="<div style='color:var(--sub);font-size:12px;margin:-3px 2px 10px'>"+list.length+" référence(s)</div>";
  h+="<div class='tw'><table><thead><tr><th>Produit</th><th class='right'>Prix moy.</th><th class='right'>Qté</th><th class='right'>CA</th><th class='right'>Comm.</th></tr></thead><tbody>";
  if(!list.length)h+="<tr><td colspan='5'><div class='empty'>Aucune référence</div></td></tr>";
  for(const p of list){
    const open=PF.op===p.sku;
    h+="<tr class='clk' onclick='pfToggle(\""+p.sku+"\")'><td class='b'>"+esc(p.name||p.sku)+" "+(p.serie==="B"?"<span class='chip tr'>TR</span>":"<span class='chip gta'>GTA</span>")+(p.missing?"<span class='missing-dot'></span>":"")+"<div style='color:var(--fi);font-size:11px;font-weight:400'>"+esc(p.sku)+"</div></td><td style='text-align:right'>"+avgPriceStr(p)+"</td><td style='text-align:right'>"+p.qty.toLocaleString("fr-FR")+"</td><td style='text-align:right'>"+eur(p.ca)+"</td><td style='text-align:right;color:var(--a)' class='b'>"+eur(p.comm,2)+"</td></tr>";
    if(open)h+="<tr><td colspan='5' style='background:var(--bg);padding:0 10px 4px'>"+prodDetail(p)+"</td></tr>";
  }
  h+="</tbody></table></div>";
  return h;
}
function rfp(){const el=document.querySelector(".search");if(!el)return;const p=el.selectionStart;render();const n=document.querySelector(".search");if(n){n.focus();try{n.setSelectionRange(p,p);}catch(e){}}}

function sfToggle(k){SF[k]=!SF[k];render();}
function setSort(k){if(SF.sortKey===k)SF.asc=!SF.asc;else{SF.sortKey=k;SF.asc=(k==="free");}render();}
function vStock(){
  const S=D.stock||[];
  if(!S.length)return"<div class='empty'>Pas de données de stock.</div>";
  let list=S.filter(s=>((s.name||"")+" "+s.sku).toLowerCase().includes(SF.q.toLowerCase()));
  const k=SF.sortKey, dir=SF.asc?1:-1;
  list.sort((a,b)=>{let va=k==="name"?(a.name||a.sku).toLowerCase():a[k], vb=k==="name"?(b.name||b.sku).toLowerCase():b[k];return va<vb?-1*dir:va>vb?1*dir:0;});
  const chip=(k,lab)=>"<span class='fchip "+(SF[k]?"on":"off")+"' onclick='sfToggle(\""+k+"\")'>"+lab+"</span>";
  const arrow=SF.asc?"↑":"↓";
  let h="<div class='filters'><div class='frow'><input class='search' style='flex:1;min-width:140px' placeholder='Rechercher…' value='"+esc(SF.q)+"' oninput='SF.q=this.value;render()'></div><div class='frow'><span class='flab'>Gamme</span>"+chip("gta","GTA")+chip("tr","TR")+"</div></div>";
  h+="<div class='grid' style='margin-bottom:12px'><div class='stat'><div class='k'>Références</div><div class='v'>"+list.length+"</div></div></div>";
  const th=(k,lab)=>"<th class='right sortable' onclick='setSort(\""+k+"\")'>"+lab+(SF.sortKey===k?" "+arrow:"")+"</th>";
  h+="<div class='tw' style='margin-top:10px'><table><thead><tr><th class='sortable' onclick='setSort(\"name\")'>Produit"+(SF.sortKey==="name"?" "+arrow:"")+"</th>"+th("onHand","Physique")+th("free","Dispo")+"</tr></thead><tbody>";
  if(!list.length)h+="<tr><td colspan='3'><div class='empty'>Aucune référence</div></td></tr>";
  for(const s of list){
    const col=s.free<=0?"var(--red)":(s.free<500?"var(--amb)":"var(--grn)");
    const g=v=>v.toLocaleString("fr-FR");
    h+="<tr><td class='b'>"+esc(s.name||s.sku)+" "+(s.serie==="B"?"<span class='chip tr'>TR</span>":"<span class='chip gta'>GTA</span>")+"<div style='color:var(--fi);font-size:11px;font-weight:400'>"+esc(s.sku)+"</div></td><td style='text-align:right'>"+g(s.onHand)+"</td><td style='text-align:right;font-weight:800;color:"+col+"'>"+g(s.free)+"</td></tr>";
  }
  h+="</tbody></table></div>";
  return h;
}

load();
</script>
</body>
</html>'''

if __name__ == "__main__":
    print("="*50)
    print("  Cockpit WeNeed — PWA + Notifications Push")
    print("  Ouvre : http://localhost:%d" % PORT)
    if DEMO: print("  (mode DEMO)")
    print("  Pour arrêter : Ctrl+C")
    print("="*50)
    threading.Thread(target=load_data, daemon=True).start()
    threading.Thread(target=stock_monitor, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
