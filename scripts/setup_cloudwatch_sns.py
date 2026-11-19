import os
import sys
import csv
import json
import boto3
from pathlib import Path

INSTANCE_ID = "i-0993ffcac611bcef7"
REGION = "us-east-1"
CSV_PATH = Path(__file__).resolve().parent.parent / "agent-deployer_accessKeys.csv"
ALERT_EMAIL = "dedasema734012@gmail.com"
TOPIC_NAME = "surveys-backend-alerts"

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

def main():
    access_key, secret_key = get_credentials()
    if not access_key or not secret_key:
        print("Error: Credenciales de AWS no encontradas.")
        sys.exit(1)

    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=REGION
    )

    sns = session.client("sns")
    cw = session.client("cloudwatch")

    print(f"1. Creando o recuperando tema SNS: {TOPIC_NAME}...")
    topic_res = sns.create_topic(Name=TOPIC_NAME)
    topic_arn = topic_res["TopicArn"]
    print(f"SNS Topic ARN: {topic_arn}")

    print(f"2. Suscribiendo correo {ALERT_EMAIL} al tema...")
    # Verificar suscripciones existentes
    subs = sns.list_subscriptions_by_topic(TopicArn=topic_arn).get("Subscriptions", [])
    already_sub = any(s.get("Endpoint") == ALERT_EMAIL for s in subs)
    if not already_sub:
        sub_res = sns.subscribe(
            TopicArn=topic_arn,
            Protocol="email",
            Endpoint=ALERT_EMAIL
        )
        print(f"Suscripción creada: {sub_res.get('SubscriptionArn')}. (Se envió correo de confirmación de AWS).")
    else:
        print(f"El correo {ALERT_EMAIL} ya estaba suscrito.")

    print("3. Creando Alarmas de CloudWatch...")

    # Alarma 1: CPU Utilization > 80%
    print("- Alarma: EC2-High-CPU-Utilization (>80%)")
    cw.put_metric_alarm(
        AlarmName="SurveysBackend-High-CPU-Utilization",
        ComparisonOperator="GreaterThanThreshold",
        EvaluationPeriods=2,
        MetricName="CPUUtilization",
        Namespace="AWS/EC2",
        Period=300,
        Statistic="Average",
        Threshold=80.0,
        ActionsEnabled=True,
        AlarmActions=[topic_arn],
        AlarmDescription="Alarma cuando el uso promedio de CPU supera el 80% durante 10 minutos en Surveys Backend EC2",
        Dimensions=[
            {
                "Name": "InstanceId",
                "Value": INSTANCE_ID
            }
        ],
        Unit="Percent"
    )

    # Alarma 2: StatusCheckFailed >= 1
    print("- Alarma: EC2-StatusCheckFailed")
    cw.put_metric_alarm(
        AlarmName="SurveysBackend-EC2-StatusCheckFailed",
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        EvaluationPeriods=1,
        MetricName="StatusCheckFailed",
        Namespace="AWS/EC2",
        Period=60,
        Statistic="Maximum",
        Threshold=1.0,
        ActionsEnabled=True,
        AlarmActions=[topic_arn],
        AlarmDescription="Alarma cuando falla el chequeo de estado de la instancia EC2 o del hardware subyacente",
        Dimensions=[
            {
                "Name": "InstanceId",
                "Value": INSTANCE_ID
            }
        ]
    )

    # Alarma 3: 5xx Errors / HTTP Failures Metric Alarm
    print("- Alarma: SurveysBackend-5xx-Application-Errors")
    cw.put_metric_alarm(
        AlarmName="SurveysBackend-5xx-Application-Errors",
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        EvaluationPeriods=1,
        MetricName="HTTPCode_5XX_Count",
        Namespace="SurveysBackend/Application",
        Period=300,
        Statistic="Sum",
        Threshold=5.0,
        ActionsEnabled=True,
        AlarmActions=[topic_arn],
        AlarmDescription="Alarma cuando se registran 5 o más errores 5xx en un período de 5 minutos en el backend",
        TreatMissingData="notBreaching"
    )

    # Alarma 4: Disk Space Warning Metric Alarm (CWAgent o custom metric)
    print("- Alarma: SurveysBackend-High-Disk-Utilization")
    cw.put_metric_alarm(
        AlarmName="SurveysBackend-High-Disk-Utilization",
        ComparisonOperator="GreaterThanThreshold",
        EvaluationPeriods=1,
        MetricName="disk_used_percent",
        Namespace="CWAgent",
        Period=300,
        Statistic="Average",
        Threshold=85.0,
        ActionsEnabled=True,
        AlarmActions=[topic_arn],
        AlarmDescription="Alarma cuando el espacio en disco supera el 85% de utilización",
        Dimensions=[
            {
                "Name": "InstanceId",
                "Value": INSTANCE_ID
            }
        ],
        Unit="Percent",
        TreatMissingData="notBreaching"
    )

    print("\nVerificando alarmas configuradas:")
    alarms = cw.describe_alarms(AlarmNamePrefix="SurveysBackend-")
    for a in alarms.get("MetricAlarms", []):
        print(f"  • {a['AlarmName']} | Estado: {a['StateValue']} | Métrica: {a['Namespace']}/{a['MetricName']}")

    print("\n[OK] Alarmas y tema SNS configurados exitosamente.")

if __name__ == "__main__":
    main()
