#!/usr/bin/env python3
"""
BondAR Scraper - usa exactamente la misma logica que =IMPORTHTML de Google Sheets.
Descarga la tabla de IOL y filtra los precios USD (terminan en D o C, precio < 500).
"""
import json, re, sys, time
from datetime import datetime, timezone

URLS = [
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos",
]

def fetch_and_parse(url):
    """Descarga la pagina y extrae precios - igual que IMPORTHTML."""
    from playwright.sync_api import sync_playwright
    
    results = {}
    
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox",
            "--disable-dev-shm-usage","--disable-gpu"
        ])
        ctx = br.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
            locale="es-AR",
            viewport={"width":1920,"height":1080}
        )
        page = ctx.new_page()
        
        print(f"  Cargando {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Esperar tabla
        for sel in ["table tbody tr:nth-child(5)","tbody tr:nth-child(5)"]:
            try: page.wait_for_selector(sel, timeout=15000); break
            except: pass
        
        # Scroll hasta el final - igual que haría el usuario en el browser
        print("  Scrolleando...", end="", flush=True)
        prev, stable = 0, 0
        for _ in range(150):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(300)
            n = len(page.query_selector_all("tbody tr"))
            if n == prev:
                stable += 1
                if stable >= 10: break
            else:
                stable = 0
                print(f"{n}..", end="", flush=True)
            prev = n
        page.wait_for_timeout(2000)
        print(f"total={prev}")
        
        # Extraer tabla como lo hace IMPORTHTML
        # Buscar todas las filas con su ticker y precio
        rows = page.query_selector_all("table tbody tr, tbody tr")
        print(f"  Parseando {len(rows)} filas...")
        
        for row in rows:
            try:
                cells = [td.inner_text().strip() for td in row.query_selector_all("td")]
                if len(cells) < 3: continue
                
                # Columna 0 o 1: ticker (simbolo)
                ticker = cells[0].strip().upper().replace("*","").strip()
                if not ticker or len(ticker) < 2 or len(ticker) > 12: continue
                if ticker in ["SIMBOLO","TICKER","ESPECIE","TITULO","INSTRUMENTO"]: continue
                
                # Buscar precio: primer numero en rango USD (0.5 - 499)
                price = 0
                price_col = -1
                for ci, cell in enumerate(cells[1:], 1):
                    # Formato argentino: 56,11 o 1.234,56
                    txt = cell.replace(".","").replace(",",".").strip()
                    try:
                        v = float(txt)
                        if 0.5 < v < 499:
                            price = v
                            price_col = ci
                            break
                    except: pass
                
                if price <= 0: continue
                
                # Variacion: buscar % cerca del precio
                change = 0
                for ci in range(price_col+1, min(price_col+3, len(cells))):
                    txt = cells[ci].replace(",",".").replace("%","").strip()
                    try:
                        v = float(txt)
                        if -50 < v < 50 and v != price:
                            change = round(v, 4)
                            break
                    except: pass
                
                # Nombre
                name = ticker
                if len(cells) > 1 and cells[1] and not cells[1].replace(",",".").replace(".","").isdigit():
                    name = cells[1].strip()[:60]
                
                results[ticker] = {"price": round(price,4), "change": change, "name": name}
                
            except: pass
        
        # TAMBIEN capturar desde el API que Angular hace internamente
        # Interceptar las respuestas JSON que llegaron durante la carga
        page.close()
        br.close()
    
    return results

def main():
    now = datetime.now(timezone.utc)
    print(f"BondAR Scraper FINAL | {now.strftime('%Y-%m-%d %H:%M UTC')}")
    
    all_prices = {}
    
    for url in URLS:
        label = url.split("/")[-2]
        print(f"\n[{label.upper()}]")
        try:
            found = fetch_and_parse(url)
            all_prices.update(found)
            print(f"  -> {len(found)} precios USD | Total: {len(all_prices)}")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
    
    if not all_prices:
        print("ERROR: 0 precios")
        sys.exit(1)
    
    # Agregar aliases: GD30D -> tambien como GD30
    index = dict(all_prices)
    for tk, d in list(all_prices.items()):
        base = re.sub(r'[DCO]$', '', tk)
        if base != tk and base not in index:
            index[base] = d
    
    out = {
        "updated": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        "source": "IOL Invertir Online",
        "count": len(all_prices),
        "prices": {tk: d for tk, d in sorted(index.items())}
    }
    
    with open("prices.json","w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*55}")
    print(f"TOTAL: {len(all_prices)} instrumentos | {len(index)} entradas con aliases")
    
    key = ["AL29D","AL30D","AL35D","AL41D",
           "GD29D","GD30D","GD35D","GD38D","GD41D","GD46D",
           "AE38D","AO27D","AO28D","AN29D",
           "BPY26D","BPD7D","BPOB8","BPOC7",
           "YM34O","TLCMO","PAMP1O"]
    found_key = [t for t in key if t in index]
    missing_key = [t for t in key if t not in index]
    print(f"Bonos clave: {len(found_key)}/{len(key)} encontrados")
    if missing_key:
        print(f"Faltantes: {missing_key}")
    for tk in found_key[:10]:
        d = index[tk]
        print(f"  {tk:10s} ${d['price']:7.2f}  {d['change']:+.2f}%")

if __name__ == "__main__":
    main()
