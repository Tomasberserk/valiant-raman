# Short-Form Content Engine (`valiant-raman`)

Motor modular de producción y experimentación audiovisual original para formatos cortos verticales (TikTok, YouTube Shorts, Instagram Reels). Diseñado bajo principios rigurosos de reproducibilidad, trazabilidad científica (*provenance*) y *compliance* ético y legal desde el diseño.

---

## 0. Principio Fundamental

Este proyecto es un **Motor de Experimentación Audiovisual Original**. 

**No es una herramienta para:**
* Evadir sistemas de detección algorítmica ni Content ID.
* Ocultar la procedencia de activos ni aparentar ubicaciones geográficas falsas.
* Reutilizar contenido de terceros mediante modificaciones cosméticas (zoom, espejos o cambios de velocidad).
* Generar engagement artificial o automatizar subidas clandestinas.

Toda transformación audiovisual tiene una finalidad editorial, estética y experimental legítima. La procedencia de cada asset y la reproducibilidad del pipeline son requisitos estrictos de arquitectura.

---

## 1. Arquitectura del Sistema

```text
Experiment
    ↓
Hypothesis (Variable independiente + Métrica primaria)
    ↓
Variants A / B / C (QUESTION / STATEMENT / SURPRISE)
    ↓
Structured Scripts (Pydantic schemas con hooks y segmentos validados)
    ↓
Voice (VoiceProvider abstracto con Dummy y Edge-TTS)
    ↓
Transcription (TranscriptionProvider abstracto con Dummy y Whisper)
    ↓
Subtitles (.ass vertical 1080x1920 con tipografía editorial)
    ↓
Composition (FFmpeg con auto-detección NVENC y fallback a libx264)
    ↓
QA (MediaValidator con 10 checks no destructivos)
    ↓
Render (MP4 H.264 1080x1920)
    ↓
SQLite Provenance (Trazabilidad relacional completa en experiments.db)
```

---

## 2. Modelado de Datos (SQLite + SQLAlchemy 2.x)

* **`Experiment`**: Contenedor principal de la prueba.
* **`Hypothesis`**: Hipótesis científica con variable independiente y criterio de éxito.
* **`Variant`**: Especificación de variantes A/B/C (`hook_type`, parámetros JSON).
* **`ExperimentRun`**: Registro inmutable de cada ejecución del pipeline con hash de configuración.
* **`Asset`**: Inventario de medios con metadatos obligatorios de procedencia (`source`, `license`, `creator`).
* **`Render`**: Archivo final con resolución, duración, códec, tamaño y resultado QA.
* **`RenderAsset`**: Tabla puente que asocia los activos utilizados en cada render específico (`role`).
* **`Publication` & `Metric`**: Registro de métricas de retención, vistas y tasa de finalización.

---

## 3. Requisitos Previos e Instalación

### Requisitos del Sistema
* **Python**: 3.10 o superior (verificado en Python 3.13.2).
* **FFmpeg & ffprobe**: Instalados y disponibles en el `PATH` del sistema (con soporte para `libx264`, `aac` y opcionalmente `h264_nvenc`).

### Instalación
```bash
# 1. Clonar el repositorio y entrar al directorio
git clone <repo-url>
cd valiant-raman

# 2. (Opcional) Crear y activar entorno virtual
python -m venv .venv
# En Windows PowerShell:
.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt
```

---

## 4. Uso de la Interfaz CLI

```bash
# 1. Inicializar esquema SQLite y directorios
python cli.py init

# 2. Registrar un asset multimedia con trazabilidad de procedencia
python cli.py asset register --type audio --source "assets/ambient_bg.wav" --license "CC-BY-4.0" --creator "OpenAcoustics"

# 3. Crear un nuevo experimento e hipótesis
python cli.py experiment create --name "James Webb Retention" --desc "Test de ganchos en astronomía"

# 4. Ejecutar el Demo Determinista 100% Offline (Genera variantes A, B y C)
python cli.py run-demo --topic "el Telescopio Espacial James Webb"

# 5. Listar experimentos, ejecuciones y renders con estatus QA
python cli.py list
```

---

## 5. Ejecución de Pruebas

Toda la suite de pruebas corre de forma autónoma e independiente de internet:

```bash
python -m pytest tests/ -v
```
