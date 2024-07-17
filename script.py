from pyzabbix import ZabbixAPI
import datetime
import time
import requests
import logging
from dotenv import load_dotenv
import os
import socket

###################################################################

def animacion_carga():
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    import time
    import datetime
    import platform

    console = Console()
    start_time = datetime.datetime.now()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
        transient=False,  # Cambiado a False para no eliminar la barra de progreso
    ) as progress:
        task = progress.add_task("Iniciando aplicación...", total=100)
        
        while not progress.finished:
            progress.update(task, advance=1)
            time.sleep(0.05)
        
    end_time = datetime.datetime.now()
    elapsed_time = (end_time - start_time).total_seconds()
    
    # Mostrar tiempo transcurrido, información del sistema y mensaje de éxito
    console.print(f"Tiempo transcurrido: {elapsed_time:.2f} segundos", style="bold yellow")
    system_info = f"Python version: {platform.python_version()} | " \
                  f"System: {platform.system()} | " \
                  f"Machine: {platform.machine()} | " \
                  f"Processor: {platform.processor()}"
    console.print(system_info, style="bold blue")
    console.print("[bold green]¡Aplicación iniciada![/bold green]")

# Llamar a la animación de carga
animacion_carga()

###############################################
# Cargar variables de entorno desde .env
load_dotenv()

# Acceder a los valores de configuración
LOG_FILE = os.getenv("LOG_FILE")
ZABBIX_URL = os.getenv("ZABBIX_URL_PRD")
ZABBIX_API_TOKEN = os.getenv("ZABBIX_PRD_API_TOKEN")
NOTIFICATION_URL = os.getenv("NOTIFICATION_URL")
ADMIN_NUMBERS = os.getenv("ADMIN_NUMBER")
NOTIFICATION_NUMBERS = os.getenv("NOTIFICATION_NUMBERS")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL"))

MENSAJE_SOLUCION = "✅ Se resuelve alerta\n"
MENSAJE_ALERTA = "⚠️ Se detecta alerta, ya en revisión\n"

headers = {'Content-Type': 'application/json'}

# Configuración de logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Conexión Zabbix (una sola vez al inicio)
zapi = ZabbixAPI(ZABBIX_URL)
zapi.login(api_token=ZABBIX_API_TOKEN)
logging.info(f"Conectado a Zabbix API Versión {zapi.api_version()}")

def format_timestamp(dt):
    """Convierte datetime a timestamp de Zabbix (segundos)."""
    return int(dt.timestamp())

def get_problem_period():
    """Obtiene el período de tiempo a consultar (últimos 10 segundos)."""
    now = datetime.datetime.now().replace(microsecond=0)
    start_time = now - datetime.timedelta(seconds=CHECK_INTERVAL)
    return format_timestamp(start_time), format_timestamp(now)

def send_notification(message, number):
    """Envía notificaciones a través de la API especificada."""
    data = {"phone": number, "message": message}
    try:
        response = requests.post(NOTIFICATION_URL, headers=headers, json=data, timeout=10)
        response.raise_for_status()  # Lanzar excepción si hay error
    except requests.RequestException as e:
        logging.error(f"Error al enviar notificación a {number}: {e}")

# crear un informe de conexion
# Se ha iniciado una sesion desde la IP
message = "Se ha iniciado correctamente una sesion desde la IP: " + socket.gethostbyname(socket.gethostname())
message = message + "\nFecha: " + str(datetime.datetime.now())

# Enviar una notificación inicial
send_notification(message=message, number=ADMIN_NUMBERS)

def verificar_resueltos(time_from, time_till):
    events = zapi.event.get(
        time_from=time_from,
        time_till=time_till,
        output="extend",
        sortorder="DESC",
        selectHosts=['hostid', 'name']
    )

    if not events:
        return
    
    for event in events:
        if event['value'] == '0':
    
            if 'hosts' in event:
                host_names = [host['name'] for host in event['hosts']]
            else:
                host_names = ['Unknown']
            host_names = ', '.join(host_names)
            
            message = (
                f"{MENSAJE_SOLUCION}Problema: {event['name']}\n"
                f"Hosts: {host_names}\n"
                f"Fecha: {datetime.datetime.fromtimestamp(int(event['clock']))}\n"
            )
            logging.info(message)
            send_notification(message, NOTIFICATION_NUMBERS)

def verificar_problemas(time_from, time_till):
    # Consultar los problemas
    problems = zapi.problem.get(
        time_from=time_from,
        time_till=time_till,
        recent=True,
        output="extend",
        sortorder="DESC"
    )

    if not problems:
        return
    
    for problem in problems:
        timestamp = datetime.datetime.fromtimestamp(int(problem["clock"]))
        

        # Obtener el host relacionado con el problema
        event = zapi.event.get(
            eventids=problem['eventid'],
            selectHosts=['hostid', 'name']
        )
        host_names = [host['name'] for host in event[0]['hosts']] if event and 'hosts' in event[0] else ['Unknown']
        host_names = ', '.join(host_names)

        message = (
            f"{MENSAJE_ALERTA}Problema: {problem['name']}\n"
            f"Hosts: {host_names}\n"
            f"Fecha: {timestamp}\n"
        )
        logging.info(message)  # Log antes de enviar
        send_notification(message, NOTIFICATION_NUMBERS)

def main():
    # Consultar los problemas
    time_from, time_till = get_problem_period()

    # obtener tiempo actual
    verificar_resueltos(time_from, time_till)
    verificar_problemas(time_from, time_till)

    logging.info(f"Esperando {CHECK_INTERVAL} segundos antes de la siguiente verificación.")
    time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    while True:
        try:
            delta1 = datetime.datetime.now()
            main()
            delta2 = datetime.datetime.now()
            elapsed_time = (delta2 - delta1).total_seconds()
            sleep_time = max(CHECK_INTERVAL - elapsed_time, 0)
            logging.info(f"Esperando {sleep_time} segundos antes de la siguiente verificación.")
            time.sleep(sleep_time)
            
        except Exception as e:
            logging.error(f"Error inesperado: {e}")
            time.sleep(CHECK_INTERVAL)  # Esperar antes de volver a intentar
