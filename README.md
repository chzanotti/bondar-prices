# bondar-prices

Precios de bonos argentinos en USD. Actualizados automaticamente desde IOL cada 30 minutos.

## Setup rapido (5 minutos)

### 1. Fork este repo
Clic en "Fork" arriba a la derecha.

### 2. Activar GitHub Pages
- Settings → Pages → Source: "Deploy from a branch" → Branch: `main` → folder: `/ (root)`
- Guardar

### 3. Activar workflows
- Ir a la tab "Actions" en tu fork
- Clic en "I understand my workflows, go ahead and enable them"

### 4. Primera ejecucion manual
- Actions → "Scrape IOL Prices" → "Run workflow" → "Run workflow"
- Esperar ~2-3 minutos

### 5. Tu URL de precios
```
https://TU_USUARIO.github.io/bondar-prices/prices.json
```
Reemplaza TU_USUARIO con tu nombre de usuario de GitHub.

### 6. Configurar en BondAR
- Abrir BondAR_Dashboard.html
- Clic en boton "⚙ GitHub URL" (topbar derecha)
- Pegar la URL del paso 5
- Clic en "Precios IOL" para actualizar

Los precios se actualizan solos cada 30 minutos en dias habiles argentinos.

## Tickers incluidos (USD CCL / MEP)
AL29D AL30D AL35D AL41D GD29D GD30D GD35D GD38D GD41D GD46D
AE38D AO27D AO28D AN29D BPY26D BPD7D BPOB8 ONs en USD...
