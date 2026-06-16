#!/usr/bin/env python3
import json, ssl, os, threading, datetime as dt, urllib.request
from flask import Flask, jsonify

ODOO_URL = "https://weneedweed.odoo.com"
DB, UID, PASSWORD = "weneedweed", 13, "!Gotierdu31500"
PORT = int(os.environ.get("PORT", 5001))
_ctx = ssl._create_unverified_context()

OH_A, OH_B = 0.25, 0.15
A_K1, A_K2 = 0.15, 0.80
A_P0, A_P1, A_P2 = 0.20, 0.2321, 0.30
B_KMAX, B_PMIN, B_PMAX = 1.0, 0.22254, 0.30

COST_TABLE = {
    "APS/I":("A",1.6),"BA/G":("A",0.75),"BB/H":("A",1.13),"BUB/G":("B",0.57),
    "CB/H":("A",1.0),"CH/H":("A",0.65),"CO/C":("A",2.0),"DI/H":("B",0.6),
    "DS/H":("A",0.6),"FO/I":("A",1.3),"GFO/I":("A",1.45),"GLC/G":("B",0.65),
    "GLC/I":("A",1.45),"GPF/I":("A",1.6),"GZ/I":("A",1.4),"IC/H":("A",1.0),
    "JL/H":("A",1.0),"LB/H":("A",0.7),"LB/I":("A",1.3),"LC/H":("B",0.3),
    "LP/I":("A",1.4),"LS/I":("A",1.35),"MI/H":("B",0.6),"MP/I":("B",1.6),
    "MS/I":("A",1.3),"MS/O":("A",0.4),"MU/H":("B",0.3),"OM/I":("A",1.3),
    "PE/G":("B",0.45),"PR/H":("A",0.6),"PT/H":("B",0.6),"RL/H":("B",0.5),
    "SA/I":("A",1.4),"SB/I":("A",1.4),"SBE/G":("B",0.48),"SBO/G":("B",0.57),
    "SBO/I":("A",1.45),"SC/I":("A",1.5),"SD/I":("A",1.3),"SH/G":("B",0.48),
    "SL/I":("A",1.6),"SM/H":("A",1.0),"SP/I":("A",1.3),"SQ/I":("A",1.4),
    "SR/H":("A",1.0),"TB/H":("A",0.9),"TK/I":("A",1.4),"TRIM/L":("A",0.1),
    "TRIM/T":("A",0.1),"UR/I":("A",1.4),"WX/H":("A",2.0),"CRB/G":("B",0.35),
    "DQF/I":("A",1.6),"SWZ/I":("A",1.6),"SOT/G":("B",0.48),"MKP/G":("B",0.57),
    "BRP/G":("B",0.57),"BC/I":("A",1.5),"IC/I":("A",1.2),"STP/I":("A",1.6),
    "BB/I":("B",0.9),"SS/I":("B",0.9),"SY/I":("B",0.9),"SE/I":("B",0.9),
    "MP/H":("B",0.65),"FF/H":("B",0.7),"SC/H":("B",0.3),"AG/H":("A",1.0),
    "SG/I":("A",1.5),"TA/I":("A",1.3),"WR/I":("B",1.65),"GH/I":("A",1.18),
    "RU/I":("A",1.18),"ALM/G":("A",0.48),"KK/G":("B",0.4),"DSD/I":("A",1.45),
    "GRC/G":("B",0.68),"SP/H":("B",0.8),"TD/I":("B",1.4),"SY/O":("B",0.2),
    "LA/H":("B",0.35),"BK/I":("A",1.3),
}

def _payout_A(k):
    if k<=0: return 0.0
    if k<A_K1: return A_P0+(k/A_K1)*(A_P1-A_P0)
    if k<A_K2: return A_P1+(k-A_K1)/(A_K2-A_K1)*(A_P2-A_P1)
    return A_P2

def _payout_B(k):
    if k<=0: return 0.0
    return B_PMIN+min(k,B_KMAX)*(B_PMAX-B_PMIN)

def line_commission(sku,qty,price):
    info=COST_TABLE.get(sku)
    if info is None: return 0.0,None,"missing"
    serie,cost=info
    if not qty or not price: return 0.0,serie,"ok"
    oh=OH_A if serie=="A" else OH_B
    m=price-cost*(1+oh)
    if m<=0: return 0.0,serie,"ok"
    k=m/cost
    p=_payout_A(k) if serie=="A" else _payout_B(k)
    return p*m*qty,serie,"ok"

def odoo(model,action,args,kw=None):
    payload={"jsonrpc":"2.0","method":"call","params":{"service":"object","method":"execute_kw",
        "args":[DB,UID,PASSWORD,model,action,args]+([kw] if kw else [])}}
    req=urllib.request.Request(ODOO_URL+"/jsonrpc",data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=20,context=_ctx) as r:
            return json.loads(r.read().decode()).get("result")
    except Exception as e:
        print(f"Odoo error: {e}"); return None

D={"orders":[],"products":[],"stock":[],"ts":None,"status":"loading"}

def load_data():
    global D
    try:
        today=dt.date.today()
        month_start=today.replace(day=1)
        orders=odoo("sale.order","search_read",[[["date_order",">=",month_start.isoformat()],["state","in",["sale","done"]]]],{"fields":["name","date_order","order_line"]}) or []
        print(f"Orders: {len(orders)}")
        prods={}
        order_lines=[]
        for o in orders:
            ol=o.get("order_line") or []
            lines=odoo("sale.order.line","search_read",[[["id","in",ol]]],{"fields":["product_id","product_uom_qty","price_unit"]}) or []
            for l in lines:
                pid=l.get("product_id")
                if not pid: continue
                p=(odoo("product.product","read",[[pid[0]]],{"fields":["default_code","name"]}) or [{}])[0]
                sku=p.get("default_code","?")
                name=p.get("name","")
                qty=l.get("product_uom_qty") or 0
                price=l.get("price_unit") or 0
                comm,serie,st=line_commission(sku,qty,price)
                order_lines.append({"sku":sku,"name":name,"qty":qty,"price":price,"comm":comm,"serie":serie or "A"})
                if sku not in prods:
                    prods[sku]={"name":name,"sku":sku,"serie":serie or "A","qty":0,"ca":0,"comm":0}
                prods[sku]["qty"]+=qty
                prods[sku]["ca"]+=qty*price
                prods[sku]["comm"]+=comm
        stock_items=[]
        raw=odoo("product.product","search_read",[],{"fields":["default_code","name","qty_available","virtual_available"]}) or []
        for p in raw:
            sku=p.get("default_code","")
            if sku and (p.get("qty_available") or 0)>0:
                stock_items.append({"sku":sku,"name":p.get("name",""),"serie":"B" if "TR" in sku else "A","onHand":int(p.get("qty_available") or 0),"free":int(p.get("virtual_available") or 0)})
        D={"orders":order_lines,"products":list(prods.values()),"stock":stock_items,"ts":dt.datetime.now().isoformat(),"status":"ok"}
        print(f"Done: {len(order_lines)} lines, {len(prods)} products, {len(stock_items)} stocks")
    except Exception as e:
        print(f"Load error: {e}")
        D["status"]="error"

app=Flask(__name__)

@app.route("/api/data")
def api_data():
    return jsonify(D)

@app.route("/api/reload",methods=["POST"])
def api_reload():
    threading.Thread(target=load_data,daemon=True).start()
    return jsonify({"ok":True})

@app.route("/")
def index():
    return """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cockpit WeNeed</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0a0a;--fg:#f0f0f0;--sub:#888;--a:#4ade80;--red:#ef4444;--amb:#f59e0b;--grn:#10b981;--fi:#555}
body{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--fg);padding:16px;padding-bottom:60px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
h1{font-size:20px;font-weight:700}
.btn{background:var(--a);color:#000;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-weight:600;font-size:14px}
.tabs{display:flex;border-bottom:1px solid var(--fi);margin-bottom:16px}
.tab{padding:10px 16px;border:none;background:none;color:var(--sub);cursor:pointer;font-size:14px;border-bottom:2px solid transparent}
.tab.on{color:var(--fg);border-bottom-color:var(--a)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{padding:8px;text-align:left;color:var(--sub);border-bottom:1px solid var(--fi)}
td{padding:8px;border-bottom:1px solid #1a1a1a}
.r{text-align:right}.b{font-weight:700}
.chip{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;margin-right:3px}
.gta{background:#3b82f6;color:#fff}.tr{background:#c084fc;color:#000}
.stat{background:#1a1a1a;border-radius:6px;padding:12px;margin-right:8px}
.stat .k{font-size:11px;color:var(--sub)}.stat .v{font-size:22px;font-weight:700;margin-top:4px}
.stats{display:flex;margin-top:12px}
.search{width:100%;padding:8px;background:#1a1a1a;border:1px solid var(--fi);color:var(--fg);border-radius:6px;margin-bottom:10px}
.empty{text-align:center;padding:40px;color:var(--sub)}
.tw{overflow-x:auto}
#status{font-size:12px;color:var(--sub);margin-bottom:8px}
</style>
</head>
<body>
<div class="top">
  <h1>🚀 Cockpit WeNeed</h1>
  <button class="btn" id="reloadBtn">↻ Actualiser</button>
</div>
<div id="status">Chargement...</div>
<div class="tabs">
  <button class="tab on" id="tab-commandes">Commandes</button>
  <button class="tab" id="tab-produits">Produits</button>
  <button class="tab" id="tab-stock">Stock</button>
</div>
<div id="content"></div>

<script>
var D = {orders:[], products:[], stock:[], status:"loading"};
var tab = "commandes";
var pq = "";

function eur(v, d) {
  return (v||0).toFixed(d||0).replace(/\\B(?=(\\d{3})+(?!\\d))/g, " ");
}

function esc(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function setTab(t) {
  tab = t;
  document.querySelectorAll(".tab").forEach(function(b){ b.className = "tab"; });
  document.getElementById("tab-"+t).className = "tab on";
  render();
}

function render() {
  var el = document.getElementById("content");
  var st = document.getElementById("status");
  if (D.status === "loading") { el.innerHTML = "<div class='empty'>Chargement depuis Odoo...</div>"; return; }
  if (D.status === "error") { el.innerHTML = "<div class='empty'>Erreur de connexion Odoo</div>"; return; }
  st.textContent = D.ts ? "Mis à jour: " + D.ts.substring(11,16) : "";
  if (tab === "commandes") renderCommandes(el);
  else if (tab === "produits") renderProduits(el);
  else renderStock(el);
}

function renderCommandes(el) {
  var os = D.orders || [];
  if (!os.length) { el.innerHTML = "<div class='empty'>Aucune commande ce mois</div>"; return; }
  var totCA=0, totComm=0;
  var h = "<div class='tw'><table><thead><tr><th>SKU</th><th>Produit</th><th class='r'>Qté</th><th class='r'>PU</th><th class='r'>CA</th><th class='r'>Comm.</th></tr></thead><tbody>";
  for (var i=0; i<os.length; i++) {
    var o = os[i];
    totCA += o.qty * o.price;
    totComm += o.comm;
    h += "<tr><td><span class='chip "+(o.serie==="B"?"tr":"gta")+"'>"+esc(o.sku)+"</span></td><td>"+esc(o.name)+"</td><td class='r'>"+o.qty+"</td><td class='r'>"+eur(o.price,2)+"</td><td class='r'>"+eur(o.qty*o.price)+"</td><td class='r b' style='color:var(--a)'>"+eur(o.comm,2)+"</td></tr>";
  }
  h += "</tbody></table></div>";
  h += "<div class='stats'><div class='stat'><div class='k'>CA total</div><div class='v'>"+eur(totCA)+" €</div></div><div class='stat'><div class='k'>Commissions</div><div class='v' style='color:var(--a)'>"+eur(totComm,2)+" €</div></div></div>";
  el.innerHTML = h;
}

function renderProduits(el) {
  var ps = (D.products || []).filter(function(p){ return (p.name+p.sku).toLowerCase().indexOf(pq.toLowerCase())>=0; });
  var h = "<input class='search' id='psearch' placeholder='Rechercher...' value='"+esc(pq)+"'>";
  h += "<div class='tw'><table><thead><tr><th>Produit</th><th class='r'>Qté</th><th class='r'>CA</th><th class='r'>Comm.</th></tr></thead><tbody>";
  if (!ps.length) h += "<tr><td colspan='4'><div class='empty'>Aucun produit</div></td></tr>";
  for (var i=0; i<ps.length; i++) {
    var p = ps[i];
    h += "<tr><td class='b'>"+esc(p.name||p.sku)+" <span class='chip "+(p.serie==="B"?"tr":"gta")+"'>"+(p.serie==="B"?"TR":"GTA")+"</span><div style='color:var(--fi);font-size:11px'>"+esc(p.sku)+"</div></td><td class='r'>"+p.qty+"</td><td class='r'>"+eur(p.ca)+"</td><td class='r b' style='color:var(--a)'>"+eur(p.comm,2)+"</td></tr>";
  }
  h += "</tbody></table></div>";
  el.innerHTML = h;
  var inp = document.getElementById("psearch");
  if (inp) inp.oninput = function(){ pq = this.value; renderProduits(el); };
}

function renderStock(el) {
  var ss = D.stock || [];
  if (!ss.length) { el.innerHTML = "<div class='empty'>Pas de stock disponible</div>"; return; }
  ss = ss.slice().sort(function(a,b){ return b.free - a.free; });
  var h = "<div class='tw'><table><thead><tr><th>Produit</th><th class='r'>Physique</th><th class='r'>Dispo</th></tr></thead><tbody>";
  for (var i=0; i<ss.length; i++) {
    var s = ss[i];
    var col = s.free<=0?"var(--red)":s.free<500?"var(--amb)":"var(--grn)";
    h += "<tr><td class='b'>"+esc(s.name||s.sku)+" <span class='chip "+(s.serie==="B"?"tr":"gta")+"'>"+(s.serie==="B"?"TR":"GTA")+"</span><div style='color:var(--fi);font-size:11px'>"+esc(s.sku)+"</div></td><td class='r'>"+s.onHand+"</td><td class='r b' style='color:"+col+"'>"+s.free+"</td></tr>";
  }
  h += "</tbody></table></div>";
  el.innerHTML = h;
}

async function loadData() {
  document.getElementById("status").textContent = "Chargement...";
  try {
    var r = await fetch("/api/data");
    D = await r.json();
    render();
  } catch(e) {
    document.getElementById("status").textContent = "Erreur: " + e.message;
  }
}

document.getElementById("reloadBtn").onclick = function() {
  fetch("/api/reload", {method:"POST"}).then(function(){ setTimeout(loadData, 2000); });
};
document.getElementById("tab-commandes").onclick = function(){ setTab("commandes"); };
document.getElementById("tab-produits").onclick = function(){ setTab("produits"); };
document.getElementById("tab-stock").onclick = function(){ setTab("stock"); };

loadData();
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("Cockpit WeNeed — port", PORT)
    threading.Thread(target=load_data, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
