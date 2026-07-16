#!/usr/bin/env python3
"""
BondAR Scraper DEFINITIVO - usa BYMA Open Data API
API 100% publica, JSON REST, sin browser, sin scraping.
Funciona desde cualquier servidor incluyendo GitHub Actions.
"""
import json, re, sys, time, urllib.request, ssl
from datetime import datetime, timezone

# BYMA Open Data - API publica usada por open.bymadata.com.ar
BYMA_BASE = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free"

ENDPOINTS = [
    ("bonos_privados",    f"{BYMA_BASE}/bonds-private-placements"),
    ("bonos_publicos",    f"{BYMA_BASE}/government-securities"),
    ("letras",            f"{BYMA_BASE}/lebacs"),
    ("ons",               f"{BYMA_BASE}/obligaciones-negociables"),
    ("bonos_garantizados",f"{BYMA_BASE}/guaranteed-bonds"),
]

# Headers que usa el browser en open.bymadata.com.ar
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Origin":          "https://open.bymadata.com.ar",
    "Referer":         "https://open.bymadata.com.ar/",
    "Content-Type":    "application/json",
}

def is_usd(price):
    return 0.5 < price < 499

def fetch_byma(label, url):
    """Fetch BYMA endpoint - POST con body, igual que hace el browser"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # BYMA usa POST con body JSON
    body = json.dumps({"T2": True, "T1": True, "T0": True}).encode()
    req = urllib.request.Request(url, data=body, headers=HEADERS, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            data = json.loads(r.read().decode())
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            print(f"  [{label}] POST OK: {len(items)} items")
            return items
    except urllib.error.HTTPError as e:
        print(f"  [{label}] HTTP {e.code}: trying GET...")
    except Exception as e:
        print(f"  [{label}] POST error: {e}, trying GET...")

    # Fallback: GET sin body
    req2 = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req2, timeout=20, context=ctx) as r:
            data = json.loads(r.read().decode())
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            print(f"  [{label}] GET OK: {len(items)} items")
            return items
    except Exception as e:
        print(f"  [{label}] GET error: {e}")
        return []

def parse_byma_item(item):
    """Parsea un item de la API de BYMA"""
    try:
        # Ticker
        ticker = None
        for f in ["simbolo","symbol","ticker","Simbolo","SYMBOL"]:
            v = item.get(f)
            if v and isinstance(v, str) and 2 <= len(v.strip()) <= 12:
                ticker = v.strip().upper()
                break
        if not ticker: return None

        # Precio - BYMA usa "ultimoPrecio" o "last"
        price = 0
        for f in ["ultimoPrecio","ultimo","lastPrice","last","UltimoPrecio",
                  "precioUltimo","cierre","close","precioCierre"]:
            v = item.get(f)
            if v is not None:
                try:
                    p = float(str(v).replace(",","."))
                    if p > 0: price = p; break
                except: pass
        if not is_usd(price): return None

        # Variacion
        change = 0
        for f in ["variacion","variacionPorcentual","change","var","porcentualVariacion"]:
            v = item.get(f)
            if v is not None:
                try:
                    c = float(str(v).replace(",",".").replace("%",""))
                    if -100 < c < 100: change = round(c, 4); break
                except: pass

        # Nombre
        name = ticker
        for f in ["descripcion","nombre","description","name","Descripcion"]:
            v = item.get(f)
            if v and isinstance(v, str) and len(v) > 2:
                try: float(v.replace(",",".")); 
                except: name = v.strip()[:60]; break

        return {"ticker": ticker, "price": round(price, 4), "change": change, "name": name}
    except: return None

def fetch_iol_fallback():
    """Fallback: intenta IOL con requests simples (sin browser)"""
    results = {}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    urls = [
        "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
        "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos",
        "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos-del-tesoro/todos",
    ]

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es-AR,es;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                html = r.read().decode("utf-8", errors="replace")

            if 'data-field="UltimoPrecio"' not in html:
                print(f"  IOL {url.split('/')[-2]}: sin data-field (pagina dinamica)")
                continue

            count = 0
            for row in html.split("<tr"):
                pm = re.search(r'data-field="UltimoPrecio"[^>]*>\s*([\d,]+\.?[\d]*)', row)
                if not pm: continue
                try: price = float(pm.group(1).replace(",","."))
                except: continue
                if not is_usd(price): continue

                ticker = None
                for pat in [
                    r'data-field="Simbolo"[^>]*>\s*([A-Z][A-Z0-9]{1,11})\s*<',
                    r'href="[^"]*cotizacion/([A-Z][A-Z0-9]{1,11})"',
                ]:
                    m = re.search(pat, row)
                    if m:
                        c = m.group(1).strip()
                        if 2 <= len(c) <= 12: ticker = c; break
                if not ticker: continue

                change = 0
                cm = re.search(r'data-field="Variacion[^"]*"[^>]*>\s*([\-\d.,]+)', row)
                if cm:
                    try:
                        v = float(cm.group(1).replace(",","."))
                        if -100 < v < 100: change = round(v, 4)
                    except: pass

                results[ticker] = {"price": round(price,4), "change": change, "name": ticker}
                count += 1
            print(f"  IOL {url.split('/')[-2]}: {count} precios USD")
        except Exception as e:
            print(f"  IOL error: {e}")

    return results

def fetch_playwright_fallback():
    """Ultimo recurso: Playwright con scroll completo"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {}

    results = {}
    urls = [
        "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
        "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos",
        "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos-del-tesoro/todos",
    ]

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage","--disable-gpu"
        ])
        ctx = br.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/124.0.0.0",
            locale="es-AR", viewport={"width":1920,"height":1080}
        )

        for url in urls:
            page = ctx.new_page()
            print(f"  Playwright: {url.split('/')[-2]}...")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                for sel in ["table tbody tr:nth-child(5)","tbody tr:nth-child(5)"]:
                    try: page.wait_for_selector(sel, timeout=15000); break
                    except: pass
                prev, stable = 0, 0
                for _ in range(150):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(300)
                    n = len(page.query_selector_all("tbody tr"))
                    if n == prev: stable += 1
                    else: stable = 0
                    if stable >= 10: break
                    prev = n
                page.wait_for_timeout(2000)
                html = page.content()
                count = 0
                for row in html.split("<tr"):
                    pm = re.search(r'data-field="UltimoPrecio"[^>]*>\s*([\d,]+\.?[\d]*)', row)
                    if not pm: continue
                    try: price = float(pm.group(1).replace(",","."))
                    except: continue
                    if not is_usd(price): continue
                    ticker = None
                    for pat in [r'data-field="Simbolo"[^>]*>\s*([A-Z][A-Z0-9]{1,11})\s*<',
                                 r'href="[^"]*cotizacion/([A-Z][A-Z0-9]{1,11})"']:
                        m = re.search(pat, row)
                        if m:
                            c = m.group(1).strip()
                            if 2 <= len(c) <= 12: ticker = c; break
                    if not ticker: continue
                    change = 0
                    cm = re.search(r'data-field="Variacion[^"]*"[^>]*>\s*([\-\d.,]+)', row)
                    if cm:
                        try:
                            v = float(cm.group(1).replace(",","."))
                            if -100 < v < 100: change = round(v,4)
                        except: pass
                    results[ticker] = {"price":round(price,4),"change":change,"name":ticker}
                    count += 1
                print(f"    {count} precios USD encontrados ({prev} filas)")
            except Exception as e:
                print(f"    Error: {e}")
            finally:
                page.close()
        br.close()
    return results

def main():
    now = datetime.now(timezone.utc)
    print(f"BondAR Scraper DEFINITIVO | {now.strftime('%Y-%m-%d %H:%M UTC')}")

    all_prices = {}

    # METODO 1: BYMA Open API (rapido, sin browser, JSON puro)
    print("\n[1] BYMA Open Data API...")
    for label, url in ENDPOINTS:
        items = fetch_byma(label, url)
        for item in items:
            r = parse_byma_item(item)
            if r:
                all_prices[r["ticker"]] = r
        time.sleep(0.5)

    print(f"  BYMA total: {len(all_prices)} precios USD")

    # METODO 2: IOL con requests simples (si BYMA no alcanza)
    if len(all_prices) < 20:
        print("\n[2] IOL requests simples...")
        iol_simple = fetch_iol_fallback()
        all_prices.update(iol_simple)
        print(f"  Total con IOL simple: {len(all_prices)}")

    # METODO 3: IOL con Playwright (ultimo recurso)
    if len(all_prices) < 20:
        print("\n[3] IOL con Playwright (puede tardar 3-5 min)...")
        pw_prices = fetch_playwright_fallback()
        all_prices.update(pw_prices)
        print(f"  Total con Playwright: {len(all_prices)}")

    if not all_prices:
        print("ERROR CRITICO: 0 precios obtenidos")
        out = {"updated": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
               "source": "ERROR", "count": 0, "prices": {}}
        with open("prices.json","w") as f: json.dump(out,f)
        sys.exit(1)

    # Agregar aliases: GD30D -> tambien GD30
    index = dict(all_prices)
    for tk, d in list(all_prices.items()):
        base = re.sub(r'[DCO]$', '', tk)
        if base != tk and base not in index:
            index[base] = d

    out = {
        "updated": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        "source": "BYMA/IOL",
        "count": len(all_prices),
        "prices": {tk: {"price":d["price"],"change":d["change"],"name":d["name"]}
                   for tk, d in sorted(index.items())}
    }
    with open("prices.json","w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"TOTAL: {len(all_prices)} instrumentos | {len(index)} entradas con aliases")

    key = ["AL30D","AL30","GD29D","GD29","GD30D","GD30","GD35D","GD41D",
           "AO27D","AO28D","AN29D","BPD7D","BPA7D","BPOB8",
           "YM34O","TLCMO","PAMP1O","IRCPO","NDT25"]
    print("\nBonos del portfolio:")
    for tk in key:
        if tk in index:
            d = index[tk]
            print(f"  OK  {tk:10s} ${d['price']:7.2f}  {d['change']:+.2f}%")
        else:
            print(f"  --  {tk:10s} no encontrado")

if __name__ == "__main__":
    main()
