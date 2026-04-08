#!/usr/bin/env bash
# Lanza KDE Teleprompter en el venv del proyecto.
# Si el venv no existe o faltan dependencias, las instala primero.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/venv"

if [ ! -f "$VENV/bin/python3" ]; then
    echo "Creando entorno virtual…"
    # --system-site-packages permite usar PyQt6 del sistema (evita descargarlo)
    python3 -m venv --system-site-packages "$VENV"
fi

# Comprobar que portaudio19-dev está instalado (necesario para compilar pyaudio)
if ! dpkg -s portaudio19-dev &>/dev/null; then
    echo "ERROR: Falta la librería de sistema 'portaudio19-dev'."
    echo "Instálala con:"
    echo ""
    echo "    sudo apt-get install portaudio19-dev"
    echo ""
    exit 1
fi

MARKER="$VENV/.deps_installed"

# Solo instala si el venv es nuevo o requirements.txt cambió
if [ ! -f "$MARKER" ] || [ "$SCRIPT_DIR/requirements.txt" -nt "$MARKER" ]; then
    echo "Instalando/actualizando dependencias…"
    "$VENV/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
    touch "$MARKER"
fi

exec "$VENV/bin/python3" "$SCRIPT_DIR/kdeteleprompter.py" "$@"
