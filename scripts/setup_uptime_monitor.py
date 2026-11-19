"""
Script de integración con monitores de disponibilidad externa (UptimeRobot / BetterStack / CloudWatch Synthetics).
Permite registrar un monitor HTTP GET / con alertas automáticas al correo del administrador.
"""
import os
import sys
import httpx
from pathlib import Path

TARGET_URL = "http://32.197.191.95:8000/"
MONITOR_NAME = "SurveysBackend-API-Production"
ALERT_EMAIL = "dedasema734012@gmail.com"

def main():
    api_key = os.getenv("UPTIMEROBOT_API_KEY")
    if not api_key:
        print("[INFO] UPTIMEROBOT_API_KEY no detectada en variables de entorno.")
        print(f"Para registrar el monitor externamente en UptimeRobot:")
        print(f"  • URL Objetivo: {TARGET_URL}")
        print(f"  • Intervalo: Cada 5 minutos (o 1 minuto en plan Pro)")
        print(f"  • Correo de Alerta: {ALERT_EMAIL}")
        print(f"  • Verificación esperada: Código HTTP 200 OK")
        print("\nSi posees una API Key de UptimeRobot, ejecuta:")
        print("  UPTIMEROBOT_API_KEY=tu_key python scripts/setup_uptime_monitor.py")
        return

    print(f"Registrando monitor en UptimeRobot para {TARGET_URL}...")
    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "cache-control": "no-cache"
    }
    payload = {
        "api_key": api_key,
        "format": "json",
        "type": "1",  # HTTP(s)
        "friendly_name": MONITOR_NAME,
        "url": TARGET_URL,
        "interval": "300"
    }

    try:
        response = httpx.post("https://api.uptimerobot.com/v2/newMonitor", data=payload, headers=headers)
        res_data = response.json()
        if res_data.get("stat") == "ok":
            print(f"[OK] Monitor UptimeRobot creado con éxito: {res_data.get('monitor', {}).get('id')}")
        else:
            print(f"[ERROR] UptimeRobot API: {res_data}")
    except Exception as exc:
        print(f"Error conectando a UptimeRobot: {exc}")

if __name__ == "__main__":
    main()
