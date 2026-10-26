"""
Estrés de CPU para provocar el autoescalado.

Se usa de dos formas:
  - Desde app.py, con iniciar(segundos), parar() y estado().
  - Como programa: python estres.py SEGUNDOS  (es lo que lanza iniciar()).

El estrés corre en procesos aparte, con menos prioridad que la web, para
que esta siga respondiendo al balanceador aunque la CPU esté al 100 %.
"""
import contextlib
import fcntl
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import tempfile
import time

# En EC2, systemd crea /run/web-app solo para la web (ver web-app.service)
DIR_ESTADO = os.environ.get("WEB_APP_DIR_ESTADO") or tempfile.gettempdir()
FICHERO_ESTADO = os.path.join(DIR_ESTADO, "web-app-estres.json")
FICHERO_CERROJO = FICHERO_ESTADO + ".lock"


@contextlib.contextmanager
def _cerrojo():
    # gunicorn arranca varios procesos: el cerrojo evita que dos peticiones
    # simultáneas lancen el estrés dos veces en la misma máquina
    with open(FICHERO_CERROJO, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _leer():
    try:
        with open(FICHERO_ESTADO) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _escribir(datos):
    temporal = FICHERO_ESTADO + ".tmp"
    with open(temporal, "w") as f:
        json.dump(datos, f)
    os.replace(temporal, FICHERO_ESTADO)


def _vivo(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _estado():
    datos = _leer()
    pid = datos.get("pid")
    restante = int(datos.get("hasta", 0) - time.time())
    if pid and restante > 0 and _vivo(pid):
        return {"activo": True, "restante": restante, "pid": pid}
    return {"activo": False, "restante": 0, "pid": None}


def estado():
    with _cerrojo():
        return _estado()


def iniciar(segundos):
    """Lanza el estrés en segundo plano. Devuelve False si ya estaba en marcha."""
    with _cerrojo():
        if _estado()["activo"]:
            return False
        # Se lanza a través de un shell que termina en el acto: el proceso de
        # estrés queda huérfano y lo adopta el sistema, que lo recoge al acabar
        orden = [sys.executable, os.path.abspath(__file__), str(int(segundos))]
        salida = subprocess.run(
            ["/bin/sh", "-c", 'nohup "$@" >/dev/null 2>&1 & echo $!', "sh"] + orden,
            capture_output=True, text=True, check=True, timeout=5,
        )
        _escribir({"pid": int(salida.stdout.strip()), "hasta": time.time() + segundos})
        return True


def parar():
    """Detiene el estrés. Devuelve False si no había ninguno en marcha."""
    with _cerrojo():
        e = _estado()
        if not e["activo"]:
            return False
        pid = e["pid"]
        for matar in (lambda: os.killpg(pid, signal.SIGTERM), lambda: os.kill(pid, signal.SIGTERM)):
            try:
                matar()
            except OSError:
                pass
        _escribir({})
        return True


def _quemar(hasta):
    # Bucle vacío: mantiene un núcleo al 100 % hasta la hora indicada
    while time.time() < hasta:
        pass


def _principal(segundos):
    try:
        os.setsid()  # grupo de procesos propio, para poder pararlos todos juntos
    except OSError:
        pass
    try:
        os.nice(10)  # menos prioridad que la web
    except OSError:
        pass
    hasta = time.time() + segundos
    procesos = [
        multiprocessing.Process(target=_quemar, args=(hasta,))
        for _ in range(os.cpu_count() or 1)  # uno por cada vCPU
    ]
    for p in procesos:
        p.start()
    for p in procesos:
        p.join()


if __name__ == "__main__":
    _principal(int(sys.argv[1]) if len(sys.argv) > 1 else 300)
