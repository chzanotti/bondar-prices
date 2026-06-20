#!/usr/bin/env python3
"""
BondAR Price Scraper v3
Estrategia: fetch individual por ticker + fallback lista completa con scroll largo
"""
import json, re, sys, time
from datetime import datetime, timezone

# ── Tickers a buscar ──────────────────────────────────────────────────────────
# Agregá acá cualquier ticker nuevo que necesites
TICKERS_USD = [
    # Soberanos Ley Local (USD CCL)
    "AL29D","AL30D","AL35D","AL38D","AL41D","AL46D",
    # Soberanos Ley NY (USD)
    "GD29D","GD30D","GD35D","GD38D","GD41D","GD46D",
    # AE / AO / AN series
    "AE38D","AO27D","AO28D","AN29D",
    # Bopreales
    "BPY26D","BPD7D","BPOB8","BPOC7",
    # ONs más comunes en USD (terminan en O)
    "YM34O","TLCMO","PAMP1O","CA30D","IRCFO","MRCAO",
    "GNCXO","YMCXO","TLC5O","TLC4O","MGC2O",
]

def get_pw_browser():
    """Retorna browser Playwright configurado"""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    br = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox","--disable-setuid-sandbox",
              "--disable-dev-shm-usage","--disable-gpu"]
    )
    ctx = br.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="es-AR",
        timezone_id="America/Argentina/Buenos_Aires",
        viewport={"width": 1920, "height": 1080},
    )
    return pw, br, ctx

def fetch_single_ticker(page, ticker):
    """Fetch precio de un ticker individual desde IOL"""
    url = f"https://iol.invertironline.com/titulo/cotizacion/{ticker}"
    
    api_price = None
    
    def on_resp(resp):
        nonlocal api_price
        try:
            if resp.status != 200: return
            ct = resp.headers.get("content-type","")
            if "json" not in ct: return
            if any(s in resp.url for s in ["google","analytics","cdn","font","hotjar"]): return
            body = resp.json()
            # Look for price in any JSON response
            def find_price(obj, depth=0):
                if depth > 5: return None
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        kl = k.lower()
                        if any(x in kl for x in ["ultimoprecio","ultimo","lastprice","preciocierre"]):
                            try:
                                p = float(str(v).replace(",","."))
                                if 0 < p < 500: return p
                            except: pass
                    for v in obj.values():
                        r = find_price(v, depth+1)
                        if r: return r
                elif isinstance(obj, list):
                    for item in obj[:5]:
                        r = find_price(item, depth+1)
                        if r: return r
                return None
            
            p = find_price(body)
            if p: api_price = p
        except: pass
    
    page.on("response", on_resp)
    
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        
        # API response found
        if api_price:
            return api_price
        
        # Parse HTML: look for price in the page
        # IOL shows price in elements with class like "precio", "ultimo-precio" etc
        for selector in [
            "[class*='precio'] strong",
            "[class*='Precio'] strong", 
            "[class*='cotiz'] .valor",
            ".precio-ultimo",
            "[data-field='ultimoPrecio']",
            "h2.precio", "h3.precio",
            ".ul-precio", ".ultimo-precio",
        ]:
            try:
                el = page.query_selector(selector)
                if el:
                    txt = el.inner_text().strip().replace(",",".").replace("$","").replace(" ","")
                    p = float(txt)
                    if 0 < p < 500:
                        return p
            except: pass
        
        # Last resort: find price-like numbers in page text
        content = page.content()
        # Look for JSON with price data in page source
        patterns = [
            r'"ultimoPrecio"\s*:\s*([0-9]+\.?[0-9]*)',
            r'"ultimo"\s*:\s*([0-9]+\.?[0-9]*)',
            r'"lastPrice"\s*:\s*([0-9]+\.?[0-9]*)',
            r'"precioUltimo"\s*:\s*([0-9]+\.?[0-9]*)',
            r'"UltimoPrecio"\s*:\s*([0-9]+\.?[0-9]*)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for m in matches:
                try:
                    p = float(m)
                    if 0 < p < 500:
                        return p
                except: pass
        
        return None
        
    except Exception as e:
        print(f"    Error fetching {ticker}: {e}")
        return None
    finally:
        page.remove_listener("response", on_resp)

def fetch_full_list(ctx):
    """Fetch lista completa con scroll agresivo"""
    results = {}
    
    urls = [
        "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
        "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos",
    ]
    
    for url in urls:
        page = ctx.new_page()
        api_rows = []
        
        def on_resp(resp):
            try:
                if resp.status != 200: return
                if "json" not in resp.headers.get("content-type",""): return
                if any(s in resp.url for s in ["google","analytics","cdn","font","hotjar","clarity"]): return
                body = resp.json()
                rows = None
                if isinstance(body, list) and len(body) > 2:
                    rows = body
                elif isinstance(body, dict):
                    for k in ["data","items","titulos","result","cotizaciones","quotes"]:
                        if isinstance(body.get(k), list) and len(body[k]) > 2:
                            rows = body[k]; break
                if rows:
                    print(f"    [API] {len(rows)} rows from {resp.url[-50:]}")
                    api_rows.extend(rows)
            except: pass
        
        page.on("response", on_resp)
        print(f"  Loading list: {url[-45:]}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for initial content
        for sel in ["table tbody tr:nth-child(10)", "tbody tr:nth-child(10)"]:
            try: page.wait_for_selector(sel, timeout=15000); break
            except: pass
        
        # AGGRESSIVE scroll - keep going until no new rows appear
        prev_rows = 0
        stable_count = 0
        for i in range(60):  # up to 60 iterations
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            
            current_rows = len(page.query_selector_all("tbody tr"))
            if current_rows == prev_rows:
                stable_count += 1
                if stable_count >= 5:  # 5 stable iterations = fully loaded
                    break
            else:
                stable_count = 0
                print(f"    Scroll {i+1}: {current_rows} rows")
            prev_rows = current_rows
        
        page.wait_for_timeout(3000)
        print(f"  Final rows: {prev_rows} | API rows: {len(api_rows)}")
        
        # Parse API data
        for item in api_rows:
            tk = (item.get("simbolo") or item.get("ticker") or item.get("symbol") or "").upper().strip()
            if not tk or len(tk) < 2 or len(tk) > 12: continue
            price = 0
            for f in ["ultimoPrecio","ultimo","Ultimo","UltimoPrecio","lastPrice","precioUltimo"]:
                v = item.get(f)
                if v:
                    try:
                        p = float(str(v).replace(",",".").replace("$",""))
                        if 0 < p < 500: price = p; break
                    except: pass
            if price <= 0: continue
            change = 0
            for f in ["variacion","variacionPorcentual","change"]:
                v = item.get(f)
                if v:
                    try: change = round(float(str(v).replace(",",".").replace("%","")),2); break
                    except: pass
            name = ""
            for f in ["descripcion","nombre","name"]:
                v = item.get(f)
                if v and isinstance(v,str) and len(v)>1: name=v.strip()[:50]; break
            results[tk] = {"price": round(price,4), "change": change, "name": name or tk}
        
        # HTML table fallback
        if len(results) < 5:
            rows = page.query_selector_all("table tbody tr, tbody tr")
            for row in rows:
                try:
                    cells = [c.inner_text().strip() for c in row.query_selector_all("td")]
                    if len(cells) < 3: continue
                    tk = cells[0].strip().upper()
                    if not tk or len(tk)<2 or len(tk)>12: continue
                    if tk in ["SIMBOLO","TICKER","ESPECIE"]: continue
                    price = 0
                    for ci in range(2, min(len(cells),8)):
                        try:
                            v = float(cells[ci].replace(".","").replace(",",".").replace("$","").strip())
                            if 0 < v < 500: price=v; break
                        except: pass
                    if price > 0:
                        results[tk] = {"price": round(price,4), "change": 0, "name": cells[1][:50] if len(cells)>1 else tk}
                except: pass
        
        page.close()
    
    return results

def main():
    now = datetime.now(timezone.utc)
    print(f"BondAR Scraper v3 - {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Tickers a buscar: {len(TICKERS_USD)}")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: Playwright not installed")
        sys.exit(1)
    
    prices = {}
    pw, br, ctx = get_pw_browser()
    
    try:
        # STRATEGY 1: Full list scraping (gets everything at once)
        print("\n[1/2] Scraping lista completa IOL...")
        list_prices = fetch_full_list(ctx)
        prices.update(list_prices)
        print(f"  Lista: {len(prices)} precios USD")
        
        # STRATEGY 2: Individual ticker fetch for any that are still missing
        missing = [t for t in TICKERS_USD if t not in prices]
        if missing:
            print(f"\n[2/2] Buscando {len(missing)} tickers individuales: {missing}")
            page = ctx.new_page()
            for ticker in missing:
                print(f"  Fetching {ticker}...", end=" ")
                price = fetch_single_ticker(page, ticker)
                if price:
                    prices[ticker] = {"price": round(price,4), "change": 0, "name": ticker}
                    print(f"${price:.2f}")
                else:
                    print("no encontrado")
                time.sleep(1)  # polite delay
            page.close()
        else:
            print("\n[2/2] Todos los tickers encontrados en lista!")
    
    finally:
        br.close()
        pw.stop()
    
    # Build output
    out = {
        "updated": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        "source": "IOL Invertir Online",
        "count": len(prices),
        "prices": {tk: d for tk, d in sorted(prices.items())}
    }
    
    with open("prices.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*50}")
    print(f"RESULTADO: {len(prices)} precios USD guardados")
    missing_final = [t for t in TICKERS_USD if t not in prices]
    if missing_final:
        print(f"No encontrados: {missing_final}")
    for tk, d in sorted(prices.items()):
        print(f"  {tk:10s}  ${d['price']:.2f}  {d['change']:+.2f}%")
    
    if len(prices) == 0:
        print("ERROR: 0 precios obtenidos!")
        sys.exit(1)

if __name__ == "__main__":
    main()
