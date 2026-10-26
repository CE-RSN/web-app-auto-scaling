"""
Web de demostración de Auto Scaling · ARCN · UD3

Muestra qué instancia EC2 ha atendido cada petición (ID, zona de
disponibilidad, IP...) y permite estresar su CPU para que el grupo de
Auto Scaling lance instancias nuevas.

Rutas:
  GET  /                  Página principal
  GET  /api/info          Datos de la instancia que responde (JSON)
  POST /api/estres        Estresa la CPU N minutos. Cuerpo: {"minutos": 10}
  POST /api/estres/parar  Detiene el estrés de la instancia que responde
  GET  /health            Comprobación de estado para el balanceador
"""
import os
import socket
import threading
import time
import urllib.request

from flask import Flask, jsonify, make_response, render_template, request

import estres

app = Flask(__name__)

MINUTOS_MAX = 15

# Un color por zona de disponibilidad (la letra final: us-east-1a, 1b...)
COLORES_ZONA = {
    "a": "#2563eb",  # azul
    "b": "#16a34a",  # verde
    "c": "#ea580c",  # naranja
    "d": "#9333ea",  # morado
    "e": "#db2777",  # rosa
    "f": "#0d9488",  # turquesa
}


# ---------------------------------------------------------------------------
# Metadatos de la instancia (IMDSv2)
# Cada instancia EC2 puede preguntarse a sí misma quién es en la dirección
# 169.254.169.254. Con IMDSv2 primero se pide un token y luego se usa.
# ---------------------------------------------------------------------------
IMDS = "http://169.254.169.254/latest"
_sin_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_cerrojo_meta = threading.Lock()
_metadatos = None
_ultimo_intento = 0.0


def _pedir_imds(ruta, metodo="GET", cabeceras=None):
    peticion = urllib.request.Request(IMDS + ruta, method=metodo, headers=cabeceras or {})
    with _sin_proxy.open(peticion, timeout=1) as respuesta:
        return respuesta.read().decode().strip()


def _leer_metadatos():
    token = _pedir_imds(
        "/api/token", metodo="PUT",
        cabeceras={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
    )
    cabeceras = {"X-aws-ec2-metadata-token": token}

    def leer(campo):
        return _pedir_imds("/meta-data/" + campo, cabeceras=cabeceras)

    return {
        "en_ec2": True,
        "instancia": leer("instance-id"),
        "zona": leer("placement/availability-zone"),
        "ip": leer("local-ipv4"),
        "tipo": leer("instance-type"),
        "ami": leer("ami-id"),
    }


def metadatos():
    """Devuelve los metadatos de la instancia (se leen una vez y se guardan)."""
    global _metadatos, _ultimo_intento
    with _cerrojo_meta:
        if _metadatos and _metadatos["en_ec2"]:
            return _metadatos
        # Fuera de EC2 (por ejemplo, en tu portátil) se reintenta cada 30 s
        if _metadatos is None or time.time() - _ultimo_intento > 30:
            _ultimo_intento = time.time()
            try:
                _metadatos = _leer_metadatos()
            except Exception:
                _metadatos = {
                    "en_ec2": False,
                    "instancia": "local-" + socket.gethostname(),
                    "zona": "fuera-de-ec2",
                    "ip": "127.0.0.1",
                    "tipo": "-",
                    "ami": "-",
                }
        return _metadatos


def color_zona(zona):
    return COLORES_ZONA.get(zona[-1:], "#64748b")


# ---------------------------------------------------------------------------
# Uso de CPU de toda la máquina, leído de /proc/stat (solo Linux)
# ---------------------------------------------------------------------------
_cerrojo_cpu = threading.Lock()
_muestra_cpu = None  # (instante, tiempo_inactivo, tiempo_total)
_cpu_pct = None


def _leer_proc_stat():
    with open("/proc/stat") as f:
        valores = [int(v) for v in f.readline().split()[1:9]]
    inactivo = valores[3] + valores[4]  # idle + iowait
    return inactivo, sum(valores)


def uso_cpu():
    global _muestra_cpu, _cpu_pct
    try:
        with _cerrojo_cpu:
            ahora = time.time()
            if _cpu_pct is not None and ahora - _muestra_cpu[0] < 1:
                return _cpu_pct
            if _muestra_cpu is None or ahora - _muestra_cpu[0] > 5:
                # Muestra antigua o inexistente: medimos un instante ahora
                inactivo, total = _leer_proc_stat()
                time.sleep(0.25)
                _muestra_cpu = (ahora, inactivo, total)
            inactivo, total = _leer_proc_stat()
            d_inactivo = inactivo - _muestra_cpu[1]
            d_total = total - _muestra_cpu[2]
            if d_total > 0:
                _cpu_pct = round(max(0.0, min(100.0, 100 * (1 - d_inactivo / d_total))), 1)
            _muestra_cpu = (time.time(), inactivo, total)
            return _cpu_pct
    except (OSError, ValueError, IndexError):
        return None  # sin /proc/stat (macOS, Windows...)


def segundos_encendida():
    try:
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))
    except (OSError, ValueError, IndexError):
        return None


def info_actual():
    datos = dict(metadatos())
    e = estres.estado()
    datos.update({
        "color": color_zona(datos["zona"]),
        "cpu": uso_cpu(),
        "encendida_s": segundos_encendida(),
        "estres": e["activo"],
        "estres_restante_s": e["restante"],
        "hora": time.strftime("%H:%M:%S"),
    })
    return datos


def _sin_cache(respuesta):
    # Que ni el navegador ni nadie guarde la respuesta: queremos ver
    # en cada consulta qué instancia contesta de verdad
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.get("/")
def inicio():
    html = render_template("index.html", info=info_actual(), minutos_max=MINUTOS_MAX)
    return _sin_cache(make_response(html))


@app.get("/api/info")
def api_info():
    return _sin_cache(jsonify(info_actual()))


@app.post("/api/estres")
def api_estres():
    datos = request.get_json(silent=True) or {}
    try:
        minutos = int(datos.get("minutos", 10))
    except (TypeError, ValueError):
        minutos = 10
    minutos = max(1, min(MINUTOS_MAX, minutos))

    iniciado = estres.iniciar(minutos * 60)
    info = info_actual()
    info["iniciado"] = iniciado
    info["mensaje"] = (
        "CPU estresada durante {} min".format(minutos) if iniciado
        else "Esta instancia ya estaba estresada"
    )
    return _sin_cache(jsonify(info))


@app.post("/api/estres/parar")
def api_parar():
    parada = estres.parar()
    info = info_actual()
    info["parada"] = parada
    info["mensaje"] = "Estrés detenido" if parada else "Esta instancia no estaba estresada"
    return _sin_cache(jsonify(info))


@app.get("/health")
def health():
    # El balanceador llama aquí cada pocos segundos: si responde 200, la
    # instancia está sana y puede recibir tráfico
    return "OK", 200, {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"}


if __name__ == "__main__":
    # Solo para probar en local. En EC2 la arranca gunicorn (ver web-app.service)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
