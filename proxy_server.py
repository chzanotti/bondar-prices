#!/usr/bin/env python3
"""BondAR Proxy Server v5 - IOL scraper USD only"""
import http.server, json, os, sys, threading, time, webbrowser

PORT = 8080
CACHE = {}
CACHE_TTL = 300

IOL_BONOS = "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos"
IOL_ONS   = "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones-negociables/todos"

def is_usd(ticker, price):
    t = ticker.upper().strip()
    if price <= 0 or price >= 500: return False
    if t.endswith('D') and len(t) >= 4: return True
    if t.endswith('O') and len(t) >= 4: return True
    if t in ['BPD7D','BPOB8','BPOC7','BPOC8']: return True
    return False

def scrape(key):
    now = time.time()
    if key in CACHE and (now - CACHE[key]['t']) < CACHE_TTL:
        print(f"  [CACHE] {key}: {CACHE[key]['count']} items")
        return CACHE[key]['data']
    url = IOL_ONS if key == 'ons' else IOL_BONOS
    print(f"  [IOL] Scraping {key}: {url}")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [!] Playwright not installed"); return {}
    results = []
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
            ctx = br.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36',
                locale='es-AR', viewport={'width':1920,'height':1080})
            page = ctx.new_page()
            api_rows = []
            def on_resp(resp):
                try:
                    if resp.status != 200: return
                    if 'json' not in resp.headers.get('content-type',''): return
                    if any(s in resp.url.lower() for s in ['google','analytics','cdn','font','hotjar']): return
                    body = resp.json()
                    rows = None
                    if isinstance(body, list) and len(body) > 0: rows = body
                    elif isinstance(body, dict):
                        for k in ['data','items','titulos','result','cotizaciones']:
                            if isinstance(body.get(k), list) and len(body[k]) > 0:
                                rows = body[k]; break
                    if rows:
                        print(f"    [API] {len(rows)} rows: {resp.url[:70]}")
                        api_rows.extend(rows)
                except: pass
            page.on('response', on_resp)
            page.goto(url, wait_until='domcontentloaded', timeout=40000)
            for sel in ['table tbody tr:nth-child(5)','tbody tr:nth-child(5)']:
                try: page.wait_for_selector(sel, timeout=12000); break
                except: pass
            prev = 0
            for _ in range(20):
                page.evaluate("window.scrollBy(0,500)")
                page.wait_for_timeout(600)
                n = len(page.query_selector_all('tbody tr'))
                if n == prev and _ > 5: break
                prev = n
            page.wait_for_timeout(2000)
            if api_rows:
                for item in api_rows:
                    r = parse_item(item)
                    if r: results.append(r)
            if not results:
                rows = page.query_selector_all('table tbody tr, tbody tr')
                for row in rows:
                    try:
                        cells = [c.inner_text().strip() for c in row.query_selector_all('td')]
                        r = parse_html(cells)
                        if r: results.append(r)
                    except: pass
            br.close()
    except Exception as e:
        print(f"  [IOL] Error: {e}")
        import traceback; traceback.print_exc()
    # Filter USD only
    usd = {r['ticker']: r for r in results if is_usd(r['ticker'], r['price'])}
    out = {'all': list(usd.values()), 'index': usd, 'count': len(usd)}
    CACHE[key] = {'data': out, 't': time.time(), 'count': len(usd)}
    print(f"  [IOL] {len(results)} total -> {len(usd)} USD kept")
    return out

def parse_item(item):
    try:
        ticker = None
        for f in ['simbolo','ticker','symbol','Simbolo','especie']:
            v = item.get(f)
            if v and isinstance(v, str) and 1 < len(v.strip()) <= 12:
                ticker = v.strip().upper(); break
        if not ticker: return None
        price = 0
        for f in ['ultimoPrecio','ultimo','Ultimo','UltimoPrecio','lastPrice','precioUltimo']:
            v = item.get(f)
            if v is not None:
                try:
                    p = float(str(v).replace(',','.').replace('$',''))
                    if 0 < p: price = p; break
                except: pass
        if price <= 0: return None
        change = 0
        for f in ['variacion','variacionPorcentual','change','Variacion']:
            v = item.get(f)
            if v is not None:
                try: change = round(float(str(v).replace(',','.').replace('%','')),2); break
                except: pass
        name = ''
        for f in ['descripcion','nombre','name','Descripcion']:
            v = item.get(f)
            if v and isinstance(v, str) and len(v) > 1: name = v.strip()[:50]; break
        return {'ticker':ticker,'price':price,'change':change,'name':name,'volume':0}
    except: return None

def parse_html(cells):
    try:
        if len(cells) < 3: return None
        ticker = cells[0].strip().upper()
        if not ticker or len(ticker) < 2 or len(ticker) > 12: return None
        if ticker in ['SIMBOLO','TICKER','ESPECIE']: return None
        name = cells[1].strip() if len(cells) > 1 else ticker
        price = 0
        for ci in range(2, min(len(cells),8)):
            txt = cells[ci].replace('.','').replace(',','.').replace('$','').strip()
            try:
                v = float(txt)
                if 0.5 < v < 999999: price = v; break
            except: pass
        if price <= 0: return None
        change = 0
        for ci in range(3, min(len(cells),8)):
            try:
                v = float(cells[ci].replace(',','.').replace('%','').strip())
                if -100 < v < 200: change = round(v,2); break
            except: pass
        return {'ticker':ticker,'price':price,'change':change,'name':name,'volume':0}
    except: return None

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
    def cors(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','*')
    def do_OPTIONS(self):
        self.send_response(200); self.cors(); self.end_headers()
    def do_GET(self):
        if self.path == '/test':
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.cors(); self.end_headers()
            self.wfile.write(json.dumps({'ok':True,'version':'5.0'}).encode()); return
        if self.path.startswith('/iol/'):
            key = self.path[5:].split('?')[0].rstrip('/')
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.cors(); self.end_headers()
            try:
                data = scrape(key)
                self.wfile.write(json.dumps({'ok':True,'all':data.get('all',[]),'index':data.get('index',{}),'count':data.get('count',0)}).encode())
            except Exception as e:
                self.wfile.write(json.dumps({'ok':False,'all':[],'index':{},'error':str(e)}).encode())
            return
        if self.path == '/clear-cache':
            CACHE.clear(); self.send_response(200); self.cors()
            self.send_header('Content-Type','application/json'); self.end_headers()
            self.wfile.write(json.dumps({'ok':True}).encode()); return
        super().do_GET()

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("\n  BondAR Proxy v5 - IOL USD Only")
    print(f"  http://localhost:{PORT}")
    if not os.path.exists('BondAR_Dashboard.html'):
        print("  ERROR: No encuentro BondAR_Dashboard.html"); input(); sys.exit(1)
    try:
        from playwright.sync_api import sync_playwright
        print("  [OK] Playwright listo")
    except ImportError:
        print("  [!] Playwright no instalado.")
        r = input("  Instalar ahora? (S/n): ").strip().lower()
        if r != 'n':
            import subprocess as sp
            sp.call([sys.executable,'-m','pip','install','playwright','--break-system-packages','-q'])
            sp.call([sys.executable,'-m','playwright','install','chromium'])
            os.execv(sys.executable,[sys.executable]+sys.argv)
    print("  Cache: 5 min | NO cerrar esta ventana | Ctrl+C para apagar\n")
    threading.Thread(target=lambda:(time.sleep(2),webbrowser.open(f'http://localhost:{PORT}/BondAR_Dashboard.html')),daemon=True).start()
    try:
        with http.server.HTTPServer(('',PORT),Handler) as srv: srv.serve_forever()
    except OSError as e:
        if '10048' in str(e) or 'in use' in str(e):
            print(f"\n  Puerto ocupado. Abri: http://localhost:{PORT}/BondAR_Dashboard.html")
        input("\n  Enter para cerrar...")
    except KeyboardInterrupt:
        print("\n  Cerrado.")
