#!/usr/bin/env python3
"""
BondAR Scraper DEFINITIVO
- Rasca bonos + ONs + bonos-del-tesoro (donde estan los GD)
- Misma logica que IMPORTHTML de Google Sheets
"""
import json, re, sys
from datetime import datetime, timezone

URLS = [
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos-del-tesoro/todos",
]

def scrape_url(page, url):
    results = {}
    print(f"  Cargando: {url.split('/')[-2]}")
    
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    
    for sel in ["table tbody tr:nth-child(5)", "tbody tr:nth-child(5)"]:
        try: page.wait_for_selector(sel, timeout=15000); break
        except: pass

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
        prev = n
    page.wait_for_timeout(2000)
    print(f"  Filas cargadas: {prev}")

    rows = page.query_selector_all("table tbody tr, tbody tr")
    for row in rows:
        try:
            cells = [td.inner_text().strip() for td in row.query_selector_all("td")]
            if len(cells) < 3: continue

            ticker = cells[0].strip().upper().replace("*","").strip()
            if not ticker or len(ticker) < 2 or len(ticker) > 12: continue
            if ticker in ["SIMBOLO","TICKER","ESPECIE","TITULO"]: continue

            # Precio USD: 0.5 a 499
            price = 0
            price_col = -1
            for ci, cell in enumerate(cells[1:], 1):
                txt = cell.replace(".","").replace(",",".").strip()
                try:
                    v = float(txt)
                    if 0.5 < v < 499:
                        price = v; price_col = ci; break
                except: pass
            if price <= 0: continue

            # Variacion
            change = 0
            for ci in range(price_col+1, min(price_col+4, len(cells))):
                txt = cells[ci].replace(",",".").replace("%","").strip()
                try:
                    v = float(txt)
                    if -50 < v < 50 and abs(v) != price:
                        change = round(v, 4); break
                except: pass

            results[ticker] = {"price": round(price,4), "change": change, "name": ticker}
        except: pass

    print(f"  Precios USD encontrados: {len(results)}")
    return results

def main():
    now = datetime.now(timezone.utc)
    print(f"BondAR Scraper | {now.strftime('%Y-%m-%d %H:%M UTC')}")

    from playwright.sync_api import sync_playwright
    all_prices = {}

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox",
            "--disable-dev-shm-usage","--disable-gpu"
        ])
        ctx = br.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
            locale="es-AR", viewport={"width":1920,"height":1080}
        )
        page = ctx.new_page()

        for url in URLS:
            found = scrape_url(page, url)
            all_prices.update(found)
            print(f"  Total acumulado: {len(all_prices)}\n")

        br.close()

    if not all_prices:
        print("ERROR: 0 precios"); sys.exit(1)

    # Aliases: GD30D -> tambien GD30
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

    print("="*50)
    print(f"TOTAL: {len(all_prices)} instrumentos ({len(index)} con aliases)")
    for tk in ["GD29D","GD30D","GD35D","GD38D","GD41D","GD46D",
               "AL30D","AE38D","BPD7D","BPOB8","YM34O","TLCMO"]:
        if tk in index:
            print(f"  OK {tk}: ${index[tk]['price']:.2f}")
        else:
            print(f"  NO {tk}: no encontrado")

if __name__ == "__main__":
    main()
