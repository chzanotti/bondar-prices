#!/usr/bin/env python3
"""
BondAR Scraper v8 - DEFINITIVO
Baja TODOS los instrumentos del mercado argentino en USD.
Usa la misma logica del Apps Script del usuario: busca en el HTML.
"""
import json, re, sys, time
from datetime import datetime, timezone

# TODAS las paginas de IOL con bonos en USD
IOL_PAGES = [
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos-del-tesoro/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/cedears/todos",
]

def is_usd(price):
    """USD: 0.5 a 499. ARS: 1000+"""
    return 0.5 < price < 499

def parse_html(html):
    """
    Logica identica al Apps Script:
    split por <tr, buscar data-field="UltimoPrecio" y el ticker en la misma fila.
    """
    results = {}
    for row in html.split("<tr"):
        # Buscar precio
        pm = re.search(r'data-field="UltimoPrecio"[^>]*>\s*([\d,]+\.?[\d]*)', row)
        if not pm:
            continue
        raw = pm.group(1).replace(".", "").replace(",", ".")
        try:
            price = float(raw)
        except:
            try:
                price = float(pm.group(1).replace(",", "."))
            except:
                continue

        if not is_usd(price):
            continue

        # Buscar ticker
        ticker = None
        for pat in [
            r'data-field="Simbolo"[^>]*>\s*([A-Z][A-Z0-9]{1,11})\s*<',
            r'href="[^"]*cotizacion/([A-Z][A-Z0-9]{1,11})"',
            r'<strong>([A-Z][A-Z0-9]{1,11})</strong>',
            r'>([A-Z][A-Z0-9]{1,11})<',
        ]:
            m = re.search(pat, row)
            if m:
                c = m.group(1).strip()
                if 2 <= len(c) <= 12 and c not in {"TD","TR","TH","TD","DIV","IMG"}:
                    ticker = c
                    break
        if not ticker:
            continue

        # Variacion
        change = 0
        cm = re.search(r'data-field="Variacion[^"]*"[^>]*>\s*([\-\d.,]+)', row)
        if cm:
            try:
                v = float(cm.group(1).replace(",", "."))
                if -100 < v < 100:
                    change = round(v, 4)
            except:
                pass

        # Nombre
        name = ticker
        nm = re.search(r'data-field="Descripcion"[^>]*>([^<]{3,60})<', row)
        if nm:
            n = nm.group(1).strip()
            # Ignorar si parece numero
            try:
                float(n.replace(",", "."))
            except:
                name = n

        results[ticker] = {
            "price":  round(price, 4),
            "change": change,
            "name":   name,
        }

    return results

def fetch_html(url):
    """Intenta requests primero (rapido), luego Playwright (seguro)."""
    import urllib.request

    # --- Intento 1: requests simples ---
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "es-AR,es;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")
        # Verificar que realmente tiene datos de bonos
        if 'data-field="UltimoPrecio"' in html:
            print(f"    requests OK - tiene datos")
            return html
        else:
            print(f"    requests OK pero sin datos (pagina dinamica)")
    except Exception as e:
        print(f"    requests error: {e}")

    # --- Intento 2: Playwright ---
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True, args=[
                "--no-sandbox","--disable-setuid-sandbox",
                "--disable-dev-shm-usage","--disable-gpu",
            ])
            ctx = br.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="es-AR",
                viewport={"width": 1920, "height": 1080},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Scroll hasta que no aparezcan filas nuevas
            prev, stable = 0, 0
            for _ in range(120):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(350)
                n = len(page.query_selector_all("tbody tr"))
                if n == prev:
                    stable += 1
                    if stable >= 10:
                        break
                else:
                    stable = 0
                prev = n
            page.wait_for_timeout(1500)
            html = page.content()
            br.close()
            print(f"    Playwright OK - {prev} filas")
            return html
    except Exception as e:
        print(f"    Playwright error: {e}")
        return ""

def main():
    now = datetime.now(timezone.utc)
    print(f"BondAR Scraper v8 | {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Paginas: {len(IOL_PAGES)}\n")

    all_prices = {}

    for url in IOL_PAGES:
        label = url.split("/")[-2]
        print(f"[{label}] {url}")
        html = fetch_html(url)
        found = parse_html(html)
        all_prices.update(found)
        print(f"    -> {len(found)} precios USD | Total: {len(all_prices)}\n")
        time.sleep(1)

    if not all_prices:
        print("ERROR: 0 precios obtenidos")
        # Guardar igual para no romper el repo
        out = {"updated": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
               "source": "IOL", "count": 0,
               "error": "Sin precios", "prices": {}}
        with open("prices.json", "w") as f:
            json.dump(out, f, indent=2)
        sys.exit(1)

    # Agregar alias base: GD30D -> tambien accesible como GD30
    index = dict(all_prices)
    for tk, d in list(all_prices.items()):
        base = re.sub(r'[DCO]$', '', tk)
        if base != tk and base not in index:
            index[base] = d

    out = {
        "updated": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        "source":  "IOL Invertir Online",
        "count":   len(all_prices),
        "prices":  {tk: d for tk, d in sorted(index.items())},
    }

    with open("prices.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("=" * 55)
    print(f"RESULTADO: {len(all_prices)} instrumentos "
          f"({len(index)} entradas con aliases)")

    # Mostrar los bonos clave
    key_tickers = [
        "AL30D","AL30","AL35D","AL41D",
        "GD30D","GD30","GD35D","GD41D","GD46D",
        "AE38D","AO27D","AN29D","BPY26D",
        "BPD7D","BPOB8",
        "YM34O","TLCMO","PAMP1O",
    ]
    print("\nBonos clave:")
    for tk in key_tickers:
        if tk in index:
            d = index[tk]
            print(f"  {tk:10s}  ${d['price']:7.2f}  "
                  f"{d['change']:+.2f}%  {d['name'][:30]}")
        else:
            print(f"  {tk:10s}  -- NO ENCONTRADO --")

