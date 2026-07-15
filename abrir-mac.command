#!/bin/bash
cd "$(dirname "$0")"

echo "============================================"
echo "   Limpiador de bases de contactos - Mac"
echo "============================================"
echo

if ! command -v python3 &> /dev/null; then
  echo "[ERROR] No se encontro Python 3."
  echo "Instalalo desde https://www.python.org/downloads/ y vuelve a abrir este archivo."
  echo
  read -p "Presiona Enter para salir..."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Primera vez: creando entorno virtual..."
  python3 -m venv .venv
fi

source .venv/bin/activate
echo "Instalando/actualizando dependencias (puede tardar la primera vez)..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo
echo "Abriendo la herramienta en tu navegador (http://localhost:8501)..."
echo "Para cerrarla, cierra esta ventana o presiona Ctrl+C."
echo
streamlit run app.py
