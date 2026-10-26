# 🌐 web-app-auto-scaling

Web en Python (Flask) para la práctica de **Auto Scaling con balanceador de carga** de la UD3 de ARCN.

Cada vez que la abres te dice **qué instancia EC2 te ha respondido**: su ID, su zona de disponibilidad (con un color distinto por zona) y su IP privada. Además permite **estresar la CPU** de la instancia para que el grupo de Auto Scaling lance instancias nuevas y puedas verlas aparecer en directo.

## ✨ Qué muestra

- La instancia que acaba de atender tu petición, su zona, IP, tipo, AMI y uso de CPU.
- Una tabla con **todas las instancias que te han respondido** desde que abriste la página. Así se ve cómo el balanceador reparte las peticiones y cómo aparecen (o desaparecen) instancias al escalar.
- Botones para **estresar** la CPU (5, 10 o 15 minutos) y para **parar** el estrés.

## 🔌 Rutas

| Ruta | Método | Para qué sirve |
|---|---|---|
| `/` | GET | Página principal |
| `/api/info` | GET | Datos de la instancia que responde, en JSON |
| `/api/estres` | POST | Pone la CPU al 100 % durante N minutos. Cuerpo: `{"minutos": 10}` (máximo 15) |
| `/api/estres/parar` | POST | Detiene el estrés de la instancia que responde |
| `/health` | GET | Devuelve `OK`. Es la ruta que usa el balanceador para saber si la instancia está sana |

## 🚀 Instalación en una instancia EC2 (Amazon Linux 2023)

Como **datos de usuario** (*user data*) al lanzar la instancia:

```bash
#!/bin/bash
dnf install -y git
git clone https://github.com/brodriguezp09/web-app-auto-scaling.git /opt/web-app-auto-scaling
bash /opt/web-app-auto-scaling/install.sh
```

O a mano, conectado a la instancia:

```bash
sudo dnf install -y git
git clone https://github.com/brodriguezp09/web-app-auto-scaling.git
cd web-app-auto-scaling
sudo bash install.sh
```

El script instala Python, crea un entorno virtual con las dependencias y registra el servicio `web-app` en systemd, que sirve la web con gunicorn en el **puerto 80** y la arranca sola en cada encendido.

> La instancia necesita salida a Internet durante la instalación (para GitHub y PyPI). Una vez instalada, ya no: por eso se puede crear una AMI a partir de ella y lanzar copias en subredes privadas.

## 🛠️ Comandos útiles en la instancia

```bash
systemctl status web-app              # ¿está en marcha el servicio?
journalctl -u web-app -n 50           # últimas líneas del registro del servicio
sudo cat /var/log/cloud-init-output.log   # qué pasó al ejecutar los datos de usuario
curl http://localhost/health          # debe devolver OK
```

## 💻 Probarla en tu ordenador

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abre <http://localhost:8080>. Fuera de EC2 la web muestra `fuera-de-ec2` como zona, y el uso de CPU solo se mide en Linux.

## 📁 Estructura

```text
web-app-auto-scaling/
├── app.py              # La web Flask: metadatos de la instancia, CPU y rutas
├── estres.py           # Estrés de CPU en procesos aparte
├── templates/
│   └── index.html      # La página (HTML, CSS y JavaScript)
├── requirements.txt    # Dependencias: Flask y gunicorn
├── install.sh          # Instalador para Amazon Linux 2023
└── web-app.service     # Servicio de systemd
```

> [!WARNING]
> La ruta de estrés es pública a propósito para la práctica. No despliegues esta web en un entorno real.
