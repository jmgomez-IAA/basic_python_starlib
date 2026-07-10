# star-spw-basic-apps

Mini-proyecto **independiente** (no forma parte de la tesis SpaceEdge-IoT) con
aplicaciones básicas en Python para gestionar dispositivos SpaceWire de
STAR-Dundee (Brick Mk3, GR718B, etc.) usando la **API oficial en Python de
STAR-System** (`STAR_system`, instalada junto al SDK), desde Linux.

## Requisitos

1. **STAR-System instalado** (incluye el driver, `libstar-api.so`, y el
   paquete Python en `apis/python_api/STAR_system`). Típicamente en:
   ```
   /usr/local/STAR-Dundee/STAR-System/
   ```
2. Dependencias Python de la API oficial (según su propio `__init__.py`):
   ```bash
   pip install numpy psutil dill
   ```
3. Que `libstar-api.so` sea localizable por el linker dinámico. Dos opciones:
   - Añadirlo a `LD_LIBRARY_PATH`:
     ```bash
     export LD_LIBRARY_PATH=/usr/local/STAR-Dundee/STAR-System/lib/x86-64:$LD_LIBRARY_PATH
     ```
   - O instalarlo en una ruta estándar del sistema (`/usr/local/lib`) y ejecutar `ldconfig`.

## Configuración rápida

Edita `setup_env.sh` con las rutas reales de tu instalación, y cárgalo antes
de ejecutar cualquier app:

```bash
source setup_env.sh
python apps/01_api_version.py
```

## Apps incluidas

| Script | Qué hace |
|---|---|
| `apps/01_api_version.py` | Comprueba que la librería carga y muestra la versión de STAR-API |
| `apps/02_list_devices.py` | Lista todos los dispositivos STAR-Dundee conectados (Brick, routers, etc.) |
| `apps/03_device_info.py` | Muestra información detallada de un dispositivo (nombre, S/N, tipo, canales) |
| `apps/04_open_close_channel.py` | Abre y cierra un canal de un dispositivo, para validar comunicación básica |

Ejecuta en ese orden — cada una es más exigente que la anterior, así que si
algo falla, sabrás exactamente en qué capa está el problema (carga de
librería → detección de dispositivo → apertura de canal).

## Nota sobre las rutas en Linux

Ajusta `PYTHON_API_PATH` en cada script (o mejor, en `setup_env.sh` como
variable de entorno `PYTHONPATH`) según dónde te haya instalado STAR-System
el paquete `STAR_system`. Suele estar en:
```
/usr/local/STAR-Dundee/STAR-System/apis/python_api
```
pero puede variar según cómo se haya instalado en tu sistema.
