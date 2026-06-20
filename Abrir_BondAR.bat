@echo off
title BondAR Dashboard v5
color 0A
echo.
echo  ============================================
echo   BondAR - Precios USD desde IOL
echo   1a actualizacion: ~20 seg
echo   Siguientes: cache 5 minutos
echo  ============================================
echo.
set "DIR=%~dp0"
if not exist "%DIR%BondAR_Dashboard.html" (echo ERROR: Falta BondAR_Dashboard.html & pause & exit)
if not exist "%DIR%proxy_server.py" (echo ERROR: Falta proxy_server.py & pause & exit)
python --version >nul 2>&1 || (echo Python no instalado - bajar de python.org & pause & exit)
echo  Iniciando... el browser se abre solo.
echo  NO cierres esta ventana.
echo.
cd /d "%DIR%"
python proxy_server.py
pause
