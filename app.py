from flask import Flask
import os
import shutil
from datetime import datetime
import tempfile
import subprocess
import time
import psutil
from threading import Lock

app = Flask(__name__)

# Configuración
WORLD_FOLDER = "./world"
BACKUPS_FOLDER = "./saves"
SERVER_JAR = "server.jar"
JAVA_COMMAND = ["java", "-Xmx20G", "-jar", SERVER_JAR, "nogui"]
SERVER_PROCESS = None
SERVER_LOCK = Lock()

def ensure_folders_exist():
    """Asegura que las carpetas necesarias existan"""
    os.makedirs(WORLD_FOLDER, exist_ok=True)
    os.makedirs(BACKUPS_FOLDER, exist_ok=True)

def is_server_running():
    """Verifica si el servidor de Minecraft está en ejecución"""
    for proc in psutil.process_iter(['name']):
        if 'java' in proc.info['name'].lower():
            try:
                cmdline = proc.cmdline()
                if SERVER_JAR in ' '.join(cmdline):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    return False

def stop_server(timeout=30):
    """Detiene el servidor de Minecraft de manera segura"""
    global SERVER_PROCESS
    
    if not is_server_running() and SERVER_PROCESS is None:
        return True, "El servidor ya estaba detenido"
    
    try:
        # Versión alternativa usando communicate()
        if SERVER_PROCESS:
            try:
                SERVER_PROCESS.communicate(input="stop\n", timeout=timeout)
            except subprocess.TimeoutExpired:
                SERVER_PROCESS.terminate()
                SERVER_PROCESS.communicate(timeout=5)
        
        # Limpieza adicional de procesos
        for proc in psutil.process_iter():
            try:
                if 'java' in proc.name().lower() and SERVER_JAR in ' '.join(proc.cmdline()):
                    proc.terminate()
                    proc.wait(timeout=5)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        SERVER_PROCESS = None
        time.sleep(2)
        return True, "Servidor detenido correctamente"
    except Exception as e:
        return False, f"Error al detener el servidor: {str(e)}"

def start_server():
    """Inicia el servidor de Minecraft"""
    global SERVER_PROCESS
    
    if is_server_running():
        return False, "El servidor ya está en ejecución"
    
    try:
        with SERVER_LOCK:
            SERVER_PROCESS = subprocess.Popen(
                JAVA_COMMAND,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.getcwd(),
                text=True
            )
        time.sleep(5)  # Espera inicial para que el servidor se inicie
        return True, "Servidor iniciado correctamente"
    except Exception as e:
        return False, f"Error al iniciar el servidor: {str(e)}"

def read_folders(path: str):
    """Lee las carpetas en el path especificado"""
    if not os.path.exists(path):
        return []
    
    folders = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
    return sorted(folders, reverse=True)

def create_backup(backup_name: str = None):
    """
    Crea una copia de seguridad del mundo actual
    Si no se especifica nombre, usa la fecha y hora actual
    """
    ensure_folders_exist()
    
    if not os.path.exists(WORLD_FOLDER):
        return False, "No existe la carpeta del mundo"
    
    if backup_name is None:
        backup_name = f"backup-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
    
    dest_path = os.path.join(BACKUPS_FOLDER, backup_name)
    
    if os.path.exists(dest_path):
        return False, "El nombre de backup ya existe"
    
    # Detener el servidor antes de hacer backup
    success, message = stop_server()
    if not success:
        return False, f"No se pudo detener el servidor para hacer backup: {message}"
    
    try:
        shutil.copytree(WORLD_FOLDER, dest_path)
        return True, backup_name
    except Exception as e:
        return False, str(e)
    finally:
        # Intentar reiniciar el servidor
        start_server()

def restore_backup(backup_name: str):
    """
    Restaura una copia de seguridad
    Primero hace backup del mundo actual antes de restaurar
    """
    ensure_folders_exist()
    
    backup_path = os.path.join(BACKUPS_FOLDER, backup_name)
    if not os.path.exists(backup_path):
        return False, "La copia de seguridad no existe"
    
    # Detener el servidor antes de restaurar
    success, message = stop_server()
    if not success:
        return False, f"No se pudo detener el servidor para restaurar: {message}"
    
    # Primero hacemos backup del mundo actual
    current_backup_name = f"pre-restore-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
    success, result = create_backup(current_backup_name)
    if not success:
        return False, f"No se pudo hacer backup del mundo actual: {result}"
    
    # Usamos un directorio temporal para operación atómica
    temp_dir = tempfile.mkdtemp()
    try:
        # Copiamos el backup al directorio temporal
        temp_world = os.path.join(temp_dir, "world")
        shutil.copytree(backup_path, temp_world)
        
        # Eliminamos el mundo actual
        shutil.rmtree(WORLD_FOLDER, ignore_errors=True)
        
        # Movemos el backup restaurado a la ubicación del mundo
        shutil.move(temp_world, WORLD_FOLDER)
        
        return True, backup_name
    except Exception as e:
        return False, str(e)
    finally:
        # Limpieza del directorio temporal
        shutil.rmtree(temp_dir, ignore_errors=True)
        # Intentar reiniciar el servidor
        start_server()

@app.route("/")
def list_backups():
    """Lista todas las copias de seguridad disponibles"""
    backups = read_folders(BACKUPS_FOLDER)
    return {
        "status": "success",
        "backups": backups,
        "count": len(backups),
        "server_status": "running" if is_server_running() else "stopped"
    }

@app.route("/create-backup", defaults={'backup_name': None})
@app.route("/create-backup/<backup_name>")
def create_backup_route(backup_name):
    """Endpoint para crear una copia de seguridad"""
    success, result = create_backup(backup_name)
    if success:
        return {
            "status": "success",
            "message": f"Backup creado: {result}",
            "backup_name": result,
            "server_status": "running" if is_server_running() else "stopped"
        }
    else:
        return {
            "status": "error",
            "message": result,
            "server_status": "running" if is_server_running() else "stopped"
        }, 400

@app.route("/restore/<backup_name>")
def restore_backup_route(backup_name):
    """Endpoint para restaurar una copia de seguridad"""
    success, result = restore_backup(backup_name)
    if success:
        return {
            "status": "success",
            "message": f"Mundo restaurado desde: {result}",
            "backup_name": result,
            "server_status": "running" if is_server_running() else "stopped"
        }
    else:
        return {
            "status": "error",
            "message": result,
            "server_status": "running" if is_server_running() else "stopped"
        }, 400

@app.route("/start-server")
def start_server_route():
    """Endpoint para iniciar el servidor"""
    success, message = start_server()
    if success:
        return {
            "status": "success",
            "message": message,
            "server_status": "running"
        }
    else:
        return {
            "status": "error",
            "message": message,
            "server_status": "stopped"
        }, 400

@app.route("/stop-server")
def stop_server_route():
    """Endpoint para detener el servidor"""
    success, message = stop_server()
    if success:
        return {
            "status": "success",
            "message": message,
            "server_status": "stopped"
        }
    else:
        return {
            "status": "error",
            "message": message,
            "server_status": "running" if is_server_running() else "stopped"
        }, 400

@app.route("/server-status")
def server_status_route():
    """Endpoint para ver el estado del servidor"""
    return {
        "status": "success",
        "server_status": "running" if is_server_running() else "stopped"
    }

if __name__ == "__main__":
    ensure_folders_exist()
    app.run(host='0.0.0.0', port=4000)