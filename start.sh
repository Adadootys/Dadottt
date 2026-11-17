#!/bin/bash
# Skrip mudah untuk jalankan TikTok 4K HD Enhancer App

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=8080

echo "=================================================="
echo "  🚀 TikTok 4K HD Enhancer & Uploader App"
echo "=================================================="
echo "Server mula berjalan di:"
echo "👉 http://localhost:${PORT}"
echo "--------------------------------------------------"
echo "Tekan Ctrl + C untuk hentikan app."
echo "=================================================="

python3 "$DIR/server.py"
