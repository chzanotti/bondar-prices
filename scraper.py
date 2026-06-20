#!/usr/bin/env python3
"""
BondAR Price Scraper v2 - GitHub Actions
Tries multiple methods to get Argentine bond USD prices.
"""
import json, sys
from datetime import datetime, timezone

def is_usd(price):
    """USD bond prices 30-300. ARS prices 10,000+"""
    return 0 < price < 500

def scrape_with_requests():
    """Try IOL/BYMA without browser"""
    import requests
    results = {}
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-AR,es;q=0.9",
    })
    
    # Try BYMA open API (sometimes allows server requests)
    try:
        s.headers.update({"Origin":"https://open.bymadata.com.ar","Referer":"https://open.bymadata.com.ar/"})
        r = s.get("https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/government-securities", timeout=15)
        print(f"  BYMA: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for it in items:
                tk = (it.get("simbolo") or it.get("ticker") or "").upper().strip()
                price = 0
                for f in ["ultimoPrecio","ultimo","lastPrice"]:
                    v = it.get(f)
                    if v:
                        try: p=float(str(v).replace(",",".")); price=p if p>0 else price; break
                        except: pass
                change = 0
                try: change = float(str(it.get("variacion","0")).replace(",","."))
                except: pass
                name = it.get("descripcion") or it.get("nombre") or tk
                if tk and is_usd(price):
                    results[tk] = {"price": round(price,4), "change": round(change,4), "name": str(name)[:50]}
    except Exception as e:
        print(f"  BYMA error: {e}")

    # Try IOL
    if len(results) < 5:
        try:
            s.headers.update({"Origin":"https://iol.invertironline.com","Referer":"https://iol.invertironline.com/"})
            for url in [
                "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
                "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos"
            ]:
                r = s.get(url, timeout=20)
                print(f"  IOL: {r.status_code} {url[-30:]}")
                if r.status_code == 200 and "json" in r.headers.get("content-type",""):
                    data = r.json()
                    items = data.get("data",[]) if isinstance(data,dict) else (data if isinstance(data,list) else [])
                    for it in items:
                        tk=(it.get("simbolo") or it.get("ticker") or "").upper().strip()
                        price=0
                        for f in ["ultimoPrecio","ultimo","lastPrice"]:
                            v=it.get(f)
                            if v:
                                try: p=float(str(v).replace(",",".")); price=p if p>0 else price; break
                                except: pass
                        change=0
                        try: change=float(str(it.get("variacion","0")).replace(",",".").replace("%",""))
                        except: pass
                        name=it.get("descripcion") or it.get("nombre") or tk
                        if tk and is_usd(price):
                            results[tk]={"price":round(price,4),"change":round(change,4),"name":str(name)[:50]}
        except Exception as e:
            print(f"  IOL requests error: {e}")
    
    return results

def scrape_with_playwright():
    """Full browser scraping - most reliable"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not available, skipping")
        return {}
    
    results = {}
    
    def parse_items(api_rows):
        out = {}
        for it in api_rows:
            tk=(it.get("simbolo") or it.get("ticker") or it.get("symbol") or "").upper().strip()
            if not tk or len(tk)<2 or len(tk)>12: continue
            price=0
            for f in ["ultimoPrecio","ultimo","Ultimo","UltimoPrecio","lastPrice","precioUltimo","Last"]:
                v=it.get(f)
                if v:
                    try: p=float(str(v).replace(",",".").replace("$","")); price=p if p>0 else price; break
                    except: pass
            if not is_usd(price): continue
            change=0
            for f in ["variacion","variacionPorcentual","change","Variacion"]:
                v=it.get(f)
                if v:
                    try: change=round(float(str(v).replace(",",".").replace("%","")),4); break
                    except: pass
            name=""
            for f in ["descripcion","nombre","name","Descripcion"]:
                v=it.get(f)
                if v and isinstance(v,str) and len(v)>1: name=v.strip()[:50]; break
            out[tk]={"price":round(price,4),"change":change,"name":name or tk}
        return out
    
    with sync_playwright() as pw:
        br = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage",
                  "--disable-gpu","--single-process"]
        )
        ctx = br.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0",
            locale="es-AR", timezone_id="America/Argentina/Buenos_Aires",
            viewport={"width":1920,"height":1080}
        )
        
        for url in [
            "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos",
            "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos"
        ]:
            page = ctx.new_page()
            api_rows = []
            
            def on_resp(resp):
                try:
                    if resp.status != 200: return
                    if "json" not in resp.headers.get("content-type",""): return
                    if any(s in resp.url for s in ["google","analytics","cdn","font","hotjar","clarity"]): return
                    body = resp.json()
                    rows = None
                    if isinstance(body,list) and len(body)>2: rows=body
                    elif isinstance(body,dict):
                        for k in ["data","items","titulos","result","cotizaciones"]:
                            if isinstance(body.get(k),list) and len(body[k])>2: rows=body[k]; break
                    if rows:
                        print(f"    API {len(rows)} rows: {resp.url[-50:]}")
                        api_rows.extend(rows)
                except: pass
            
            page.on("response", on_resp)
            print(f"  Loading: {url[-45:]}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            for sel in ["table tbody tr:nth-child(5)","tbody tr:nth-child(5)"]:
                try: page.wait_for_selector(sel, timeout=15000); break
                except: pass
            
            prev=0
            for _ in range(20):
                page.evaluate("window.scrollBy(0,600)")
                page.wait_for_timeout(500)
                n=len(page.query_selector_all("tbody tr"))
                if n==prev and _>6: break
                prev=n
            page.wait_for_timeout(2000)
            
            if api_rows:
                results.update(parse_items(api_rows))
                print(f"  API: {len(results)} USD prices so far")
            else:
                # HTML fallback
                rows=page.query_selector_all("table tbody tr,tbody tr")
                print(f"  HTML: {len(rows)} rows")
                for row in rows:
                    try:
                        cells=[c.inner_text().strip() for c in row.query_selector_all("td")]
                        if len(cells)<3: continue
                        tk=cells[0].strip().upper()
                        if not tk or len(tk)<2 or len(tk)>12: continue
                        price=0
                        for ci in range(2,min(len(cells),8)):
                            try:
                                v=float(cells[ci].replace(".","").replace(",",".").replace("$","").strip())
                                if is_usd(v): price=v; break
                            except: pass
                        if price>0:
                            results[tk]={"price":round(price,4),"change":0,"name":cells[1].strip()[:50] if len(cells)>1 else tk}
                    except: pass
            page.close()
        br.close()
    return results

def main():
    now = datetime.now(timezone.utc)
    print(f"BondAR Scraper v2 - {now.strftime('%Y-%m-%d %H:%M UTC')}")
    
    prices = {}
    
    print("\n[1] requests method...")
    try:
        prices = scrape_with_requests()
        print(f"  -> {len(prices)} prices")
    except Exception as e:
        print(f"  -> Failed: {e}")
    
    if len(prices) < 5:
        print("\n[2] Playwright method...")
        try:
            pw_prices = scrape_with_playwright()
            prices.update(pw_prices)
            print(f"  -> {len(prices)} prices total")
        except Exception as e:
            print(f"  -> Failed: {e}")
    
    out = {
        "updated": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        "source": "IOL Invertir Online",
        "count": len(prices),
        "prices": {tk: d for tk, d in sorted(prices.items())}
    }
    
    with open("prices.json","w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    
    print(f"\n-> prices.json: {len(prices)} tickers")
    for tk, d in list(out["prices"].items())[:20]:
        print(f"   {tk:10s}  ${d['price']:.2f}  {d['change']:+.2f}%")
    
    if len(prices) == 0:
        print("\nWARNING: 0 prices fetched!")
        sys.exit(1)

if __name__ == "__main__":
    main()
