#!/usr/bin/env bash
# start_essential_hk.sh — Verifica dependencias y lanza 11_essential_hk_service.py

set -e

# 1. Mosquitto (broker MQTT)
sudo systemctl is-active --quiet mosquitto || sudo systemctl start mosquitto
sudo systemctl is-active --quiet mosquitto && echo "[OK] mosquitto" || { echo "[FALLO] mosquitto no arranca"; exit 1; }

# 2. InfluxDB
sudo systemctl is-active --quiet influxdb || sudo systemctl start influxdb
sudo systemctl is-active --quiet influxdb && echo "[OK] influxdb" || { echo "[FALLO] influxdb no arranca"; exit 1; }
curl -sf http://localhost:8086/health > /dev/null && echo "[OK] influxdb responde en :8086" || { echo "[FALLO] influxdb no responde"; exit 1; }

# 3. Telegraf (puente MQTT -> InfluxDB)
sudo systemctl is-active --quiet telegraf || sudo systemctl start telegraf
sudo systemctl is-active --quiet telegraf && echo "[OK] telegraf" || { echo "[FALLO] telegraf no arranca"; exit 1; }

# 4. Bucket de InfluxDB existe
influx bucket list | grep -q spacewire && echo "[OK] bucket 'spacewire' existe" || { echo "[FALLO] bucket 'spacewire' no encontrado"; exit 1; }

# 5. Entorno de la API oficial STAR-System + lanzar el servicio
echo "Todo OK. Lanzando 11_essential_hk_service.py..."
source setup_env.sh
python apps/11_essential_hk_service.py
