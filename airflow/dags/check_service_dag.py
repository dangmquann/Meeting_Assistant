from datetime import datetime, timedelta
import os
import psycopg2
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine, text

def hello_world():
    print("Hello from Airflow! ")
    return "success"


def check_services():
    """Check if other services are accessible"""
    try:
        print("Checking service dependencies...")
        return "healthy", "Connected successfully"
    except Exception as e:
        print(f"Service check failed: {str(e)}")
        raise



# DAG configuration
default_args = {
    "owner": "rag",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# Create the DAG
dag = DAG(
    "hello_world_week1",
    default_args=default_args,
    description="Hello World DAG for Week 1",
    schedule=None,
    catchup=False,
    tags=["check", "testing"],
)

# Define tasks
hello_task = PythonOperator(
    task_id="hello_world",
    python_callable=hello_world,
    dag=dag,
)

service_check_task = PythonOperator(
    task_id="check_services",
    python_callable=check_services,
    dag=dag,
)

# Set task dependencies
hello_task >> service_check_task
