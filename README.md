# bondar-prices v7

Precios USD de bonos argentinos desde IOL. Actualización automática cada 30 min.

Ya **no usa Playwright/Chromium** (eso era lo que lo hacía pesado y frágil). Ahora
funciona igual que tu Apps Script: descarga el HTML de la página de cotizaciones
y lo parsea con expresiones regulares buscando los `data-field` de cada fila
(Simbolo, UltimoPrecio, Variacion, Descripcion). Corre en segundos en GitHub
Actions sin instalar nada extra.

## Setup
1. Fork este repo
2. Settings → Pages → Branch: main → / (root) → Save
3. Actions → habilitar → Run workflow ("Actualizar precios IOL")
4. URL: https://TU_USUARIO.github.io/bondar-prices/prices.json
5. En BondAR: botón "GitHub URL" → pegar URL → "Precios IOL"

## Si algún ticker no aparece
IOL a veces cambia el nombre de los `data-field`. Si ves que faltan instrumentos,
avisame el ticker y reviso qué nombre de campo está usando esa página puntual
(se agrega a la lista de candidatos en `FIELD_PRICE` / `FIELD_TICKER` del script).
