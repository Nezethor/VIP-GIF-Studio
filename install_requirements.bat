@echo off
title Instalando Requisitos - VIP GIF Studio
echo ========================================================
echo   Instalando dependencias necesarias para VIP GIF Studio...
echo ========================================================
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo ========================================================
echo   Instalacion completada con exito!
echo ========================================================
pause
