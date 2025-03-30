from flask import Flask
import os
import shutil
from datetime import datetime
import tempfile

app = Flask(__name__)

# Configuración
WORLD_FOLDER = "./world"
BACKUPS_FOLDER = "./saves"

def ensure_folders_exist():
    """Asegura que las carpetas necesarias existan"""
    os.makedirs(WORLD_FOLDER, exist_ok=True)
    os.makedirs(BACKUPS_FOLDER, exist_ok=True)

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
    
    try:
        # Usamos copytree que es más fiable que system calls
        shutil.copytree(WORLD_FOLDER, dest_path)
        return True, backup_name
    except Exception as e:
        return False, str(e)

def restore_backup(backup_name: str):
    """
    Restaura una copia de seguridad
    Primero hace backup del mundo actual antes de restaurar
    """
    ensure_folders_exist()
    
    backup_path = os.path.join(BACKUPS_FOLDER, backup_name)
    if not os.path.exists(backup_path):
        return False, "La copia de seguridad no existe"
    
    # Primero hacemos backup del mundo actual
    success, result = create_backup()
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

@app.route("/")
def list_backups():
    """Lista todas las copias de seguridad disponibles"""
    backups = read_folders(BACKUPS_FOLDER)
    return {
        "status": "success",
        "backups": backups,
        "count": len(backups)
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
            "backup_name": result
        }
    else:
        return {
            "status": "error",
            "message": result
        }, 400

@app.route("/restore/<backup_name>")
def restore_backup_route(backup_name):
    """Endpoint para restaurar una copia de seguridad"""
    success, result = restore_backup(backup_name)
    if success:
        return {
            "status": "success",
            "message": f"Mundo restaurado desde: {result}",
            "backup_name": result
        }
    else:
        return {
            "status": "error",
            "message": result
        }, 400

if __name__ == "__main__":
    ensure_folders_exist()
    app.run(host='0.0.0.0', port=4000)