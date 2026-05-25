# bondar-prices

Precios de bonos argentinos USD actualizados automaticamente desde IOL.

## Setup (5 minutos)

1. Fork este repositorio en tu cuenta GitHub
2. Ve a Settings > Pages > Source: "GitHub Actions"  
3. Ve a Actions > habilitar workflows
4. Ejecuta manualmente: Actions > "Scrape IOL Prices" > Run workflow
5. La URL de tu JSON sera:
   `https://TU_USUARIO.github.io/bondar-prices/prices.json`
6. En el dashboard BondAR, boton "GitHub URL" del topbar, pega esa URL
7. Luego "Precios IOL" trae los precios sin necesitar proxy local

Los precios se actualizan solos cada 30 minutos en dias habiles.
