#!/usr/bin/env python3
"""
BondAR Price Scraper v5
Descarga TODOS los instrumentos USD de IOL (no hardcodea tickers).
Funciona con cualquier bono que el usuario cargue en el dashboard.
"""
import json, re, sys, time
from datetime import datetime, timezone

IOL_URLS = [
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos",
]

def is_usd(price):
    """Precio USD: entre 0.5 y 499. ARS: 1000+"""
    return 0.5 < price < 499

def scrape_full_page(ctx, url):
    """Descarga lista completa de IOL con scroll hasta el final"""
    page = ctx.new_page()
    api_rows = []

    def on_resp(resp):
        try:
            if resp.status != 200: return
            if "json" not in resp.headers.get("content-type", ""): return
            skip = ["google","analytics","cdn","font","hotjar","clarity","facebook","segment","intercom","drift"]
            if any(s in resp.url for s in skip): return
            body = resp.json()
            rows = None
            if isinstance(body, list) and len(body) > 2:
                rows = body
            elif isinstance(body, dict):
                for k in ["data","items","titulos","result","cotizaciones","quotes","instrumentos"]:
                    if isinstance(body.get(k), list) and len(body[k]) > 2:
                        rows = body[k]; break
            if rows:
                print(f"    [API] {len(rows)} filas de {resp.url[-60:]}")
                api_rows.extend(rows)
        except: pass

    page.on("response", on_resp)
    print(f"\n  Cargando: {url[-50:]}")
    
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"  Error cargando pagina: {e}")
        page.close()
        return []

    # Esperar que aparezca contenido
    for sel in ["table tbody tr:nth-child(5)", "tbody tr:nth-child(5)", "tr:nth-child(5)"]:
        try:
            page.wait_for_selector(sel, timeout=15000)
            print(f"  Contenido detectado")
            break
        except: pass

    # Scroll hasta el fondo - esperar que no aparezcan filas nuevas
    print("  Scrolleando hasta el final...")
    prev_count = 0
    stable = 0
    for i in range(100):  # max 100 intentos
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)
        count = len(page.query_selector_all("tbody tr"))
        if count != prev_count:
            print(f"    {count} filas...", end="\r")
            stable = 0
        else:
            stable += 1
            if stable >= 8:  # 8 veces sin cambios = cargado completo
                break
        prev_count = count

    page.wait_for_timeout(2000)
    print(f"  Total filas HTML: {prev_count} | API rows: {len(api_rows)}")

    results = []

    # Parse API rows (mas confiable)
    if api_rows:
        for item in api_rows:
            r = parse_api(item)
            if r: results.append(r)
        print(f"  Parsed {len(results)} instrumentos USD desde API")

    # Fallback: parse tabla HTML
    if len(results) < 5:
        print("  Usando fallback HTML...")
        rows = page.query_selector_all("table tbody tr, tbody tr")
        for row in rows:
            try:
                cells = [c.inner_text().strip() for c in row.query_selector_all("td")]
                r = parse_html(cells)
                if r: results.append(r)
            except: pass
        print(f"  Parsed {len(results)} instrumentos USD desde HTML")

    page.close()
    return results

def parse_api(item):
    try:
        ticker = None
        for f in ["simbolo","ticker","symbol","Simbolo","especie","codigo"]:
            v = item.get(f)
            if v and isinstance(v, str) and 2 <= len(v.strip()) <= 12:
                ticker = v.strip().upper(); break
        if not ticker: return None

        price = 0
        for f in ["ultimoPrecio","ultimo","Ultimo","UltimoPrecio","lastPrice",
                  "precioUltimo","Last","close","precioCierre","precioPromedio"]:
            v = item.get(f)
            if v is not None:
                try:
                    p = float(str(v).replace(",",".").replace("$",""))
                    if p > 0: price = p; break
                except: pass
        if not is_usd(price): return None

        change = 0
        for f in ["variacion","variacionPorcentual","change","Variacion"]:
            v = item.get(f)
            if v is not None:
                try: change = round(float(str(v).replace(",",".").replace("%","")), 4); break
                except: pass

        name = ""
        for f in ["descripcion","nombre","name","Descripcion","denominacion"]:
            v = item.get(f)
            if v and isinstance(v, str) and len(v) > 1: name = v.strip()[:60]; break

        vol = 0
        for f in ["volumenNominal","volumen","volume"]:
            v = item.get(f)
            if v:
                try: vol = int(float(str(v).replace(",",""))); break
                except: pass

        return {"ticker": ticker, "price": round(price, 4), "change": change, "name": name or ticker, "volume": vol}
    except: return None

def parse_html(cells):
    try:
        if len(cells) < 3: return None
        ticker = cells[0].strip().upper()
        if not ticker or len(ticker) < 2 or len(ticker) > 12: return None
        if ticker in ["SIMBOLO","TICKER","ESPECIE","INSTRUMENTO"]: return None
        name = cells[1].strip()[:60] if len(cells) > 1 else ticker
        price = 0
        for ci in range(2, min(len(cells), 8)):
            try:
                v = float(cells[ci].replace(".","").replace(",",".").replace("$","").strip())
                if is_usd(v): price = v; break
            except: pass
        if not price: return None
        change = 0
        for ci in range(3, min(len(cells), 8)):
            try:
                v = float(cells[ci].replace(",",".").replace("%","").strip())
                if -100 < v < 200: change = round(v, 4); break
            except: pass
        return {"ticker": ticker, "price": round(price, 4), "change": change, "name": name, "volume": 0}
    except: return None

def main():
    now = datetime.now(timezone.utc)
    print(f"BondAR Scraper v5 - {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("Estrategia: descarga lista COMPLETA de IOL (todos los USD)")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: pip install playwright && playwright install chromium")
        sys.exit(1)

    all_items = []

    with sync_playwright() as pw:
        br = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox",
                  "--disable-dev-shm-usage","--disable-gpu","--single-process"]
        )
        ctx = br.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
            viewport={"width": 1920, "height": 1080},
        )

        for url in IOL_URLS:
            items = scrape_full_page(ctx, url)
            all_items.extend(items)

        br.close()

    # Build index - deduplicate, prefer D suffix (USD CCL)
    index = {}
    for item in all_items:
        tk = item["ticker"]
        base = re.sub(r'[DCO]$', '', tk)
        if tk not in index:
            index[tk] = item
        # Also store base alias (GD30D -> also accessible as GD30)
        if base != tk and base not in index:
            index[base] = item
        # Prefer D over C over base
        if base in index:
            existing = index[base]["ticker"]
            score = lambda t: 3 if t.endswith('D') else (2 if t.endswith('C') else 1)
            if score(tk) > score(existing):
                index[base] = item

    out = {
        "updated": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        "source": "IOL Invertir Online",
        "count": len([k for k in index if not re.search(r'[DCO]$', re.sub(r'[DCO]$','',k)) or True]),
        "prices": {tk: {"price": d["price"], "change": d["change"], "name": d["name"]}
                   for tk, d in sorted(index.items())}
    }

    with open("prices.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    usd_count = len([k for k in index if not k.endswith('_base')])
    print(f"\n{'='*50}")
    print(f"RESULTADO: {usd_count} instrumentos USD guardados en prices.json")
    print(f"Incluye aliases (GD30D tambien accesible como GD30)")
    print("\nMuestra de precios:")
    for tk, d in list(out["prices"].items())[:30]:
        print(f"  {tk:12s} ${d['price']:.2f}  {d['change']:+.2f}%  {d['name'][:30]}")

    if usd_count == 0:
        print("ERROR: 0 precios!"); sys.exit(1)

if __name__ == "__main__":
    main()
