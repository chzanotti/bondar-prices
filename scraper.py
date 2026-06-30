#!/usr/bin/env python3
"""
BondAR Price Scraper v7
Misma lógica que el Apps Script de Google Sheets:
  - pide el HTML de la página de cotizaciones de IOL
  - separa por filas <tr ...> ... </tr>
  - dentro de cada fila busca los data-field conocidos (Simbolo, UltimoPrecio, Variacion, etc.)
Sin navegador, sin Playwright. Mucho más liviano y estable para correr en GitHub Actions.
"""
import json, re, sys
from datetime import datetime, timezone
import urllib.request

IOL_URLS = [
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos",
    "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos-del-tesoro/todos",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

# data-field values que puede usar IOL para cada dato (probamos varios, igual que el Apps Script)
FIELD_TICKER = ["Simbolo", "simbolo"]
FIELD_PRICE  = ["UltimoPrecio", "Ultimo", "ultimoPrecio"]
FIELD_CHANGE = ["Variacion", "VariacionPorcentual", "variacion"]
FIELD_NAME   = ["Descripcion", "descripcion", "Nombre"]


def fetch_html(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def get_field(row_html, field_names):
    """Busca data-field="X">VALOR dentro de una fila, probando varios nombres posibles."""
    for fname in field_names:
        m = re.search(
            r'data-field=["\']' + re.escape(fname) + r'["\'][^>]*>\s*([^<]+)',
            row_html, re.IGNORECASE
        )
        if m:
            return m.group(1).strip()
    return None


def is_usd_price(price):
    return 0.5 < price < 499


def parse_row(row_html):
    raw_ticker = get_field(row_html, FIELD_TICKER)
    if not raw_ticker:
        return None
    ticker = raw_ticker.strip().upper()
    if not (2 <= len(ticker) <= 12):
        return None

    raw_price = get_field(row_html, FIELD_PRICE)
    if not raw_price:
        return None
    try:
        price = float(raw_price.replace(".", "").replace(",", ".").replace("$", "").strip())
    except ValueError:
        return None
    if not is_usd_price(price):
        return None

    change = 0.0
    raw_change = get_field(row_html, FIELD_CHANGE)
    if raw_change:
        try:
            change = round(float(raw_change.replace(",", ".").replace("%", "").strip()), 4)
        except ValueError:
            change = 0.0

    name = ticker
    raw_name = get_field(row_html, FIELD_NAME)
    if raw_name and len(raw_name) > 2:
        cleaned = raw_name.replace(",", ".").replace(" ", "")
        try:
            float(cleaned)  # es un numero, no un nombre -> descartar
        except ValueError:
            name = raw_name.strip()[:60]

    return {"ticker": ticker, "price": round(price, 4), "change": change, "name": name}


def scrape_page(url):
    print(f"\n  Descargando: {url}")
    try:
        html = fetch_html(url)
    except Exception as e:
        print(f"  Error al descargar: {e}")
        return []

    rows = html.split("<tr")
    results = []
    for row in rows:
        r = parse_row(row)
        if r:
            results.append(r)

    print(f"  {len(results)} instrumentos USD encontrados")
    return results


def main():
    now = datetime.now(timezone.utc)
    print(f"BondAR Scraper v7 (requests + regex) | {now.strftime('%Y-%m-%d %H:%M UTC')}")

    all_items = []
    for url in IOL_URLS:
        all_items.extend(scrape_page(url))

    if not all_items:
        print("ERROR: 0 instrumentos obtenidos. No se sobrescribe prices.json.")
        sys.exit(1)

    # Indice: deduplicar, preferir tickers en D (dolar MEP/cable) > C > base
    index = {}

    def usd_score(tk):
        if tk.endswith("D"):
            return 3
        if tk.endswith("C"):
            return 2
        if tk.endswith("O"):
            return 2
        return 1

    for item in all_items:
        tk = item["ticker"]
        if tk not in index or usd_score(tk) >= usd_score(index[tk]["ticker"]):
            index[tk] = item
        base = re.sub(r"[DCO]$", "", tk)
        if base != tk:
            if base not in index or usd_score(tk) > usd_score(index[base]["ticker"]):
                index[base] = dict(item, ticker=tk)

    out = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "IOL Invertir Online",
        "count": len(all_items),
        "prices": {tk: {"price": d["price"], "change": d["change"], "name": d["name"]}
                   for tk, d in sorted(index.items())},
    }

    with open("prices.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 55}")
    print(f"RESULTADO: {len(all_items)} instrumentos | prices.json: {len(index)} entradas")
    show = ["AL30D", "AL30", "GD30D", "GD30", "GD35D", "GD35", "AE38D", "AO27D"]
    for tk in show:
        if tk in index:
            d = index[tk]
            print(f"  {tk:10s}  ${d['price']:.2f}  {d['change']:+.2f}%  {d['name'][:30]}")
        else:
            print(f"  {tk:10s}  -- no encontrado --")


if __name__ == "__main__":
    main()
