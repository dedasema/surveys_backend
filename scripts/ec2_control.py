"""
Script de gestión automatizada del ciclo de vida y costos de la EC2 de Surveys Backend.
Permite encender, apagar, consultar estado y monitorear gasto en AWS.
"""
import os
import sys
import csv
import json
import subprocess
from pathlib import Path

INSTANCE_ID = "i-0993ffcac611bcef7"
REGION = "us-east-1"
CSV_PATH = Path(__file__).resolve().parent.parent / "agent-deployer_accessKeys.csv"

def get_credentials():
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        if CSV_PATH.exists():
            with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    access_key = row.get("Access key ID") or row.get("access_key_id")
                    secret_key = row.get("Secret access key") or row.get("secret_access_key")
                    break
    return access_key, secret_key

def run_aws_cmd(args):
    access_key, secret_key = get_credentials()
    env = os.environ.copy()
    if access_key and secret_key:
        env["AWS_ACCESS_KEY_ID"] = access_key
        env["AWS_SECRET_ACCESS_KEY"] = secret_key
    env["AWS_DEFAULT_REGION"] = REGION
    cmd = ["aws"] + args
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error AWS CLI: {res.stderr.strip()}", file=sys.stderr)
        return None
    return res.stdout.strip()

def status():
    out = run_aws_cmd([
        "ec2", "describe-instances",
        "--instance-ids", INSTANCE_ID,
        "--query", "Reservations[0].Instances[0].[State.Name,PublicIpAddress,InstanceType]"
    ])
    if out:
        state, ip, itype = json.loads(out)
        print(f"[EC2 Status] ID: {INSTANCE_ID} | Tipo: {itype} | Estado: {state.upper()} | IP Publica: {ip or 'N/A (Detenida)'}")

def start():
    print(f"Iniciando instancia {INSTANCE_ID}...")
    run_aws_cmd(["ec2", "start-instances", "--instance-ids", INSTANCE_ID])
    print("Comando de encendido enviado. Esperando estado 'running'...")
    run_aws_cmd(["ec2", "wait", "instance-running", "--instance-ids", INSTANCE_ID])
    status()

def stop():
    print(f"Apagando instancia {INSTANCE_ID} para no consumir credito...")
    run_aws_cmd(["ec2", "stop-instances", "--instance-ids", INSTANCE_ID])
    print("Comando de apagado enviado. El computo ahora esta en $0.00/h.")

def cost():
    from datetime import datetime, timedelta
    end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = datetime.now().strftime("%Y-%m-01")
    out = run_aws_cmd([
        "ce", "get-cost-and-usage",
        "--time-period", f"Start={start_date},End={end_date}",
        "--granularity", "MONTHLY",
        "--metrics", "UnblendedCost"
    ])
    if out:
        data = json.loads(out)
        amount = data.get("ResultsByTime", [{}])[0].get("Total", {}).get("UnblendedCost", {}).get("Amount", "0")
        print(f"[AWS Cost Explorer] Gasto acumulado del mes ({start_date} a {end_date}): ${float(amount):.4f} USD")

if __name__ == "__main__":
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "status"
    if action == "start":
        start()
    elif action == "stop":
        stop()
    elif action == "cost":
        cost()
    else:
        status()
