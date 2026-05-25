#!/usr/bin/env python3
"""BondAR GitHub Actions scraper - corre cada 30min y publica prices.json"""
import json, time
from datetime import datetime

IOL_BONOS = "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos"
IOL_ONS   = "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos"

def scrape_page(url):
    from playwright.sync_api import sync_playwright
    results = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = br.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0',
                             locale='es-AR', viewport={'width':1920,'height':1080})
        page = ctx.new_page()
        api_rows = []
        def on_resp(resp):
            try:
                if resp.status != 200: return
                if 'json' not in resp.headers.get('content-type',''): return
                if any(s in resp.url for s in ['google','analytics','cdn','font']): return
                body = resp.json()
                rows = body if isinstance(body,list) else None
                if not rows and isinstance(body,dict):
                    for k in ['data','items','titulos','result','cotizaciones']:
                        if isinstance(body.get(k),list): rows=body[k]; break
                if rows and len(rows)>0: api_rows.extend(rows)
            except: pass
        page.on('response', on_resp)
        page.goto(url, wait_until='domcontentloaded', timeout=45000)
        for sel in ['table tbody tr:nth-child(5)','tbody tr:nth-child(5)']:
            try: page.wait_for_selector(sel, timeout=12000); break
            except: pass
        prev=0
        for _ in range(20):
            page.evaluate("window.scrollBy(0,500)")
            page.wait_for_timeout(600)
            n=len(page.query_selector_all('tbody tr'))
            if n==prev and _>5: break
            prev=n
        page.wait_for_timeout(2000)
        if api_rows:
            for item in api_rows:
                r=parse_api(item)
                if r: results.append(r)
        if not results:
            for row in page.query_selector_all('table tbody tr,tbody tr'):
                try:
                    cells=[c.inner_text().strip() for c in row.query_selector_all('td')]
                    r=parse_html(cells)
                    if r: results.append(r)
                except: pass
        br.close()
    return results

def parse_api(item):
    try:
        ticker=None
        for f in ['simbolo','ticker','symbol','Simbolo','especie']:
            v=item.get(f)
            if v and isinstance(v,str) and 1<len(v.strip())<=12: ticker=v.strip().upper(); break
        if not ticker: return None
        price=0
        for f in ['ultimoPrecio','ultimo','Ultimo','UltimoPrecio','lastPrice']:
            v=item.get(f)
            if v:
                try: p=float(str(v).replace(',','.').replace('$','')); price=p if p>0 else price; break
                except: pass
        if price<=0: return None
        change=0
        for f in ['variacion','variacionPorcentual','change']:
            v=item.get(f)
            if v:
                try: change=round(float(str(v).replace(',','.').replace('%','')),2); break
                except: pass
        name=''
        for f in ['descripcion','nombre','name']:
            v=item.get(f)
            if v and isinstance(v,str) and len(v)>1: name=v.strip()[:50]; break
        return {'ticker':ticker,'price':price,'change':change,'name':name}
    except: return None

def parse_html(cells):
    try:
        if len(cells)<3: return None
        ticker=cells[0].strip().upper()
        if not ticker or len(ticker)<2 or len(ticker)>12: return None
        if ticker in ['SIMBOLO','TICKER','ESPECIE']: return None
        name=cells[1].strip() if len(cells)>1 else ticker
        price=0
        for ci in range(2,min(len(cells),8)):
            try:
                v=float(cells[ci].replace('.','').replace(',','.').replace('$','').strip())
                if 0.5<v<999999: price=v; break
            except: pass
        if price<=0: return None
        change=0
        for ci in range(3,min(len(cells),8)):
            try:
                v=float(cells[ci].replace(',','.').replace('%','').strip())
                if -100<v<200: change=round(v,2); break
            except: pass
        return {'ticker':ticker,'price':price,'change':change,'name':name}
    except: return None

def is_usd(ticker, price):
    t=ticker.upper()
    if price>=500: return False
    if t.endswith('D') and len(t)>=4: return True
    if t.endswith('O') and len(t)>=4: return True
    if t in ['BPD7D','BPOB8','BPOC7']: return True
    return False

def main():
    print("Scraping bonos...")
    bonos=scrape_page(IOL_BONOS)
    print(f"  {len(bonos)} items")
    print("Scraping ONs...")
    ons=scrape_page(IOL_ONS)
    print(f"  {len(ons)} items")
    all_items=bonos+ons
    prices={}
    for item in all_items:
        tk=item['ticker']
        if not is_usd(tk,item['price']): continue
        if tk not in prices or (tk.endswith('D') and not prices[tk]['ticker'].endswith('D')):
            prices[tk]=item
    out={'updated':datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
         'source':'IOL Invertir Online','count':len(prices),
         'prices':{tk:{'price':d['price'],'change':d['change'],'name':d['name']} for tk,d in sorted(prices.items())}}
    with open('prices.json','w') as f:
        json.dump(out,f,indent=2,ensure_ascii=False)
    print(f"\nGuardado: {len(prices)} precios USD en prices.json")
    for tk,d in list(out['prices'].items())[:15]:
        print(f"  {tk:10s} ${d['price']:.2f}  {d['change']:+.2f}%")

if __name__=='__main__':
    main()
