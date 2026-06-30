#!/usr/bin/env python3
"""
BondAR Price Scraper v6
- Descarga lista completa de IOL (bonos + ONs + bonos del tesoro)
- Corrige bug de change/name
- Agrega GD series y ONs que faltaban
"""
import json, re, sys, time
from datetime import datetime, timezone

IOL_URLS = [
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos-del-tesoro/todos",
]

def is_usd_price(price):
    return 0.5 < float(price) < 499

def parse_api_item(item):
    """Parsea un item del API de IOL con campos correctos"""
    try:
        # TICKER
        ticker = None
        for f in ["simbolo","ticker","symbol","Simbolo","especie"]:
            v = item.get(f)
            if v and isinstance(v, str) and 2 <= len(v.strip()) <= 12:
                ticker = v.strip().upper()
                break
        if not ticker:
            return None

        # PRECIO - solo campos de precio real
        price = 0
        for f in ["ultimoPrecio","ultimo","Ultimo","UltimoPrecio",
                  "lastPrice","precioUltimo","precioCierre","Last","close"]:
            v = item.get(f)
            if v is not None:
                try:
                    p = float(str(v).replace(",",".").replace("$",""))
                    if p > 0:
                        price = p
                        break
                except: pass
        if not is_usd_price(price):
            return None

        # VARIACION - solo campos de variacion/cambio porcentual
        change = 0
        for f in ["variacion","variacionPorcentual","variacionDiaria",
                  "cambioPorcentual","change","pct","variacionEnPorcentaje"]:
            v = item.get(f)
            if v is not None and v != price:  # evitar confundir con precio
                try:
                    c = float(str(v).replace(",",".").replace("%",""))
                    if -100 < c < 100:  # variacion razonable entre -100% y +100%
                        change = round(c, 4)
                        break
                except: pass

        # NOMBRE - solo strings que no parezcan numeros
        name = ticker
        for f in ["descripcion","nombre","name","Descripcion","denominacion","description"]:
            v = item.get(f)
            if v and isinstance(v, str) and len(v) > 2:
                # Ignorar si parece un numero (ej: "84,13")
                cleaned = v.replace(",",".").replace(" ","")
                try:
                    float(cleaned)
                    continue  # Es un numero, saltear
                except: pass
                name = v.strip()[:60]
                break

        return {
            "ticker": ticker,
            "price": round(price, 4),
            "change": change,
            "name": name
        }
    except:
        return None

def parse_html_row(cells):
    """Parsea fila de tabla HTML de IOL"""
    try:
        if len(cells) < 3:
            return None
        ticker = cells[0].strip().upper()
        if not ticker or len(ticker) < 2 or len(ticker) > 12:
            return None
        if ticker in ["SIMBOLO","TICKER","ESPECIE","INSTRUMENTO","TITULO"]:
            return None

        name = cells[1].strip()[:60] if len(cells) > 1 else ticker
        # Evitar nombre numerico
        try:
            float(name.replace(",","."))
            name = ticker
        except: pass

        # Precio: buscar primer numero en rango USD
        price = 0
        price_col = -1
        for ci in range(2, min(len(cells), 8)):
            txt = cells[ci].replace(".","").replace(",",".").replace("$","").strip()
            try:
                v = float(txt)
                if is_usd_price(v):
                    price = v
                    price_col = ci
                    break
            except: pass
        if not price:
            return None

        # Variacion: buscar numero con % o en rango -100/+100 DESPUES del precio
        change = 0
        for ci in range(price_col + 1, min(len(cells), price_col + 4)):
            txt = cells[ci].replace(",",".").replace("%","").strip()
            try:
                v = float(txt)
                if -100 < v < 100 and v != price:
                    change = round(v, 4)
                    break
            except: pass

        return {
            "ticker": ticker,
            "price": round(price, 4),
            "change": change,
            "name": name
        }
    except:
        return None

def scrape_page(ctx, url):
    """Scrapea una pagina de IOL con scroll completo"""
    page = ctx.new_page()
    api_rows = []

    def on_resp(resp):
        try:
            if resp.status != 200: return
            if "json" not in resp.headers.get("content-type", ""): return
            skip = ["google","analytics","cdn","font","hotjar","clarity",
                    "facebook","segment","intercom","drift","twitter"]
            if any(s in resp.url for s in skip): return
            body = resp.json()
            rows = None
            if isinstance(body, list) and len(body) > 2:
                rows = body
            elif isinstance(body, dict):
                for k in ["data","items","titulos","result","cotizaciones",
                           "quotes","instrumentos","bonos","securities"]:
                    if isinstance(body.get(k), list) and len(body[k]) > 2:
                        rows = body[k]
                        break
            if rows:
                print(f"    [API] {len(rows)} filas | {resp.url[-55:]}")
                api_rows.extend(rows)
        except: pass

    page.on("response", on_resp)

    print(f"\n  Cargando: {url.split('/')[-2]}/{url.split('/')[-1]}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"  Error: {e}")
        page.close()
        return []

    # Esperar contenido inicial
    for sel in ["table tbody tr:nth-child(5)", "tbody tr:nth-child(5)"]:
        try:
            page.wait_for_selector(sel, timeout=15000)
            print(f"  Contenido detectado")
            break
        except: pass

    # Scroll agresivo hasta que no aparezcan filas nuevas
    print("  Scrolleando...", end=" ", flush=True)
    prev = 0
    stable = 0
    for i in range(150):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(400)
        n = len(page.query_selector_all("tbody tr"))
        if n != prev:
            print(f"{n}", end="...", flush=True)
            stable = 0
        else:
            stable += 1
            if stable >= 10:
                break
        prev = n
    page.wait_for_timeout(2000)
    print(f"final={prev}")

    results = []

    # Parsear desde API (mas confiable)
    if api_rows:
        for item in api_rows:
            r = parse_api_item(item)
            if r:
                results.append(r)
        print(f"  API: {len(results)} instrumentos USD")

    # Fallback HTML
    if len(results) < 5:
        print("  Usando HTML fallback...")
        rows = page.query_selector_all("table tbody tr, tbody tr")
        for row in rows:
            try:
                cells = [c.inner_text().strip()
                         for c in row.query_selector_all("td")]
                r = parse_html_row(cells)
                if r:
                    results.append(r)
            except: pass
        print(f"  HTML: {len(results)} instrumentos USD")

    page.close()
    return results

def main():
    now = datetime.now(timezone.utc)
    print(f"BondAR Scraper v6 | {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Paginas a scrapear: {len(IOL_URLS)}")

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
                  "--disable-dev-shm-usage","--disable-gpu"]
        )
        ctx = br.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
            viewport={"width": 1920, "height": 1080},
        )

        for url in IOL_URLS:
            items = scrape_page(ctx, url)
            all_items.extend(items)
            print(f"  Subtotal acumulado: {len(all_items)}")

        br.close()

    if not all_items:
        print("ERROR: 0 instrumentos obtenidos")
        sys.exit(1)

    # Construir indice: deduplicar, preferir D > C > base
    index = {}
    def usd_score(tk):
        if tk.endswith('D'): return 3
        if tk.endswith('C'): return 2
        if tk.endswith('O'): return 2
        return 1

    for item in all_items:
        tk = item["ticker"]
        # Guardar por ticker exacto
        if tk not in index or usd_score(tk) >= usd_score(index[tk]["ticker"]):
            index[tk] = item
        # Guardar alias base (AL30D -> tambien AL30)
        base = re.sub(r'[DCO]$', '', tk)
        if base != tk:
            if base not in index or usd_score(tk) > usd_score(index[base]["ticker"]):
                index[base] = item

    out = {
        "updated": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        "source": "IOL Invertir Online",
        "count": len(all_items),
        "prices": {tk: {"price": d["price"], "change": d["change"], "name": d["name"]}
                   for tk, d in sorted(index.items())}
    }

    with open("prices.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"RESULTADO: {len(all_items)} instrumentos USD")
    print(f"prices.json: {len(index)} entradas (con aliases base)")
    print(f"\nMuestra:")
    show = ["AL30D","AL30","GD30D","GD30","GD35D","GD35","AE38D",
            "AO27D","AN29D","BPD7D","BPA7D","BPB7D"]
    for tk in show:
        if tk in index:
            d = index[tk]
            print(f"  {tk:10s}  ${d['price']:.2f}  {d['change']:+.2f}%  {d['name'][:30]}")
        else:
            print(f"  {tk:10s}  -- no encontrado --")

if __name__ == "__main__":
    main()
