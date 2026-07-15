@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   Limpiador de bases de contactos - Windows
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] No se encontro Python.
  echo Instalalo desde https://www.python.org/downloads/ y marca "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Primera vez: creando entorno virtual...
  python -m venv .venv
)

call .venv\Scripts\activate.bat
echo Instalando/actualizando dependencias (puede tardar la primera vez)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo.
echo Abriendo la herramienta en tu navegador (http://localhost:8501)...
echo Para cerrarla, cierra esta ventana o presiona Ctrl+C.
echo.
streamlit run app.py

pause
