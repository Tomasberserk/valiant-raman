# STAGE 9 — IMPLEMENTATION PLAN: CONTRATOS Y ESPECIFICACIÓN TÉCNICA

**Proyecto:** `valiant-raman`  
**Objetivo:** Transición de Nivel 2 (Functional MVP) a Nivel 3 (Product-Ready MVP) mediante refactor localizado de contratos de medios, saneamiento editorial, dinamismo visual y pulido de UX.  
**Regla:** Cero reescritura de la arquitectura base (FastAPI, SQLite, RunDispatcher, Repository, ThreadPoolExecutor, FFmpeg, Edge-TTS).

---

## 1. ARCHIVOS QUE SERÁN MODIFICADOS

1. [`engine/media/voice.py`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/engine/media/voice.py):
   - Garantizar honestidad de contenedor de audio (conversión a WAV PCM real de 16-bit 24kHz o extensión MP3 legítima).
2. [`engine/media/transcription.py`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/engine/media/transcription.py):
   - Aceptar duración explícita opcional `duration_seconds` y usar fallback infalible con `ffprobe` en lugar de fallar ciegamente a 5.0s con `wave.open`.
3. [`engine/media/compositor.py`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/engine/media/compositor.py):
   - Introducir dinamismo continuo en fondo procedural (slow zoom continuo `zoompan` lavfi) y normalización sonora EBU R128 (`loudnorm=I=-14:tp=-1.0`).
4. [`engine/creative/knowledge.py`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/engine/creative/knowledge.py) **[NUEVO]**:
   - Catálogo local determinista de hechos y cápsulas factuales verificadas (tecnología, ciencia, historia, computación).
5. [`engine/creative/interpreter.py`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/engine/creative/interpreter.py):
   - Extracción de tema nuclear reconociendo patrones comunes ("un dato curioso sobre X", "la historia de X", etc.) y extracción de restricciones de duración (< 30s -> 24s).
6. [`engine/scripting/scriptwriter.py`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/engine/scripting/scriptwriter.py):
   - Integración con `KnowledgeBank`, presupuesto estricto de palabras (*Word Budget*: máx. 50-55 palabras para 24s) y erradicación de retórica abstracta.
7. [`engine/creative/service.py`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/engine/creative/service.py):
   - Soportar edición de gancho en `select_concept(concept_id, custom_hook=None)` y propagar duración objetivo al compilar.
8. [`engine/pipeline.py`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/engine/pipeline.py):
   - Pasar `duration_seconds=audio_result.duration_seconds` a `transcription_provider.transcribe()`.
9. [`web/routes/creative.py`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/web/routes/creative.py):
   - Aceptar payload opcional `SelectConceptRequest(custom_hook: Optional[str] = None)` en `POST /api/concepts/{id}/select`.
10. [`web/static/js/studio.js`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/web/static/js/studio.js):
    - Exclusión mutua de audio en `<video>`, edición inline de ganchos en tarjetas y toasts no bloqueantes en lugar de `alert()`.
11. [`web/templates/index.html`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/web/templates/index.html) y [`web/static/css/studio.css`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/web/static/css/studio.css):
    - Contenedor Toast de notificaciones y estilos para ganchos editables.
12. [`tests/test_real_providers.py`](file:///c:/Users/merid/Documents/antigravity/valiant-raman/tests/test_real_providers.py):
    - Tests de integridad: duración de audio vs subtítulos, presupuesto de palabras y normalización sonora.

---

## 2. FIRMAS ACTUALES

### 2.1 `engine/media/base.py` / `engine/media/transcription.py`
```python
# engine/media/base.py
class TranscriptionProvider(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        reference_text: Optional[str] = None,
    ) -> List[WordTimestamp]:
        pass

# engine/media/transcription.py
class DummyTranscriptionProvider(TranscriptionProvider):
    def transcribe(
        self,
        audio_path: Path,
        reference_text: Optional[str] = None,
    ) -> List[WordTimestamp]:
```

### 2.2 `engine/media/voice.py`
```python
class EdgeTTSVoiceProvider(VoiceProvider):
    def generate_audio(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> AudioResult:
```

### 2.3 `engine/creative/interpreter.py`
```python
class CreativeInterpreter:
    def interpret(self, raw_input: str) -> InterpretationResult:
    def _extract_topic(self, text: str) -> str:
```

### 2.4 `engine/creative/service.py`
```python
class CreativeService:
    def select_concept(self, concept_id: str) -> Concept:
```

### 2.5 `web/routes/creative.py`
```python
@router.post("/concepts/{concept_id}/select", response_model=ConceptDTO)
def select_concept(
    concept_id: str,
    service: CreativeService = Depends(get_service),
):
```

---

## 3. FIRMAS PROPUESTAS

### 3.1 `engine/media/base.py` & `engine/media/transcription.py`
```python
# Firma propuesta en TranscriptionProvider:
@abstractmethod
def transcribe(
    self,
    audio_path: Path,
    reference_text: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> List[WordTimestamp]:
```
* **Motivo:** Permite al pipeline inyectar la duración ya confirmada por el sintetizador (`audio_result.duration_seconds`), eliminando la necesidad de inspección redundante o fallos de códec.
* **Compatibilidad:** El parámetro `duration_seconds` es opcional con valor por defecto `None`. Si no se pasa, la implementación calcula la duración mediante `ffprobe` (o `wave.open` si es WAV real). 100% retrocompatible con tests previos.

### 3.2 `engine/media/voice.py` (`EdgeTTSVoiceProvider`)
* **Firma se mantiene idéntica:**
```python
def generate_audio(
    self,
    text: str,
    voice_id: str,
    output_path: Path,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> AudioResult:
```
* **Cambio interno de contrato de archivo:** Si `output_path` termina en `.wav`, Edge-TTS sintetiza a un archivo temporal (`.mp3`) y FFmpeg lo convierte de inmediato a PCM WAV real (`pcm_s16le`, 24kHz mono). Así, `output_path` es un archivo WAV legítimo con cabecera RIFF válida. Si termina en `.mp3`, se guarda directo.
* **Compatibilidad:** Callers existentes no requieren cambios. Cualquier herramienta downstream (incluyendo `wave.open`) ahora procesa el `.wav` sin excepciones.

### 3.3 `engine/creative/interpreter.py`
```python
# Firma propuesta:
def interpret(self, raw_input: str) -> InterpretationResult:
def _extract_topic_and_constraints(self, text: str) -> Tuple[str, float, Optional[str]]:
```
* **Motivo:** Identifica el tema real extrayendo prefijos como *"un dato curioso sobre"*, *"la historia de"*, limpia truncamientos y detecta restricciones de duración (ej. *"menos de 30 segundos"* fija `target_duration_seconds = 24.0`).
* **Compatibilidad:** `interpret(raw_input)` mantiene su firma pública y devuelve el mismo modelo `InterpretationResult`.

### 3.4 `engine/creative/service.py`
```python
# Firma propuesta:
def select_concept(self, concept_id: str, custom_hook: Optional[str] = None) -> Concept:
```
* **Motivo:** Permite actualizar el gancho del concepto si el usuario lo editó en la UI antes de compilar el experimento.
* **Compatibilidad:** `custom_hook=None` por defecto. Si no se pasa, opera idéntico a Stage 4-6.

### 3.5 `web/routes/creative.py`
```python
class SelectConceptRequest(BaseModel):
    custom_hook: Optional[str] = None

@router.post("/concepts/{concept_id}/select", response_model=ConceptDTO)
def select_concept(
    concept_id: str,
    payload: Optional[SelectConceptRequest] = None,
    service: CreativeService = Depends(get_service),
):
```
* **Motivo:** Permite a la UI enviar `{ "custom_hook": "..." }`.
* **Compatibilidad:** `payload` es opcional; llamadas POST vacías (como las de los tests existentes) devuelven 200 OK y seleccionan el concepto normalmente.

---

## 4. CONTRATOS DE DATOS Y CAMPOS A CONSERVAR

### 4.1 `AudioResult` (`engine/media/base.py`)
* **Campos obligatorios:**
  - `file_path: Path` (Ruta física absoluta al archivo de audio válido)
  - `duration_seconds: float` (Duración real > 0, extraída mediante ffprobe)
  - `voice_id: str` (Identificador de voz usado, ej: `es-ES-AlvaroNeural`)
  - `provider: str` (Nombre del proveedor, ej: `EdgeTTSVoiceProvider`)
  - `sample_rate: int` (Tasa de muestreo, 24000 Hz)
* **Conservación:** 100% de los campos se mantienen.

### 4.2 `WordTimestamp` (`engine/media/base.py`)
* **Campos obligatorios:**
  - `word: str` (Palabra normalizada)
  - `start: float` (Tiempo de inicio en segundos $\ge 0$)
  - `end: float` (Tiempo de fin en segundos $> start$)
* **Conservación:** 100% compatible con `generate_ass_subtitles`.

### 4.3 `StructuredScript` (`engine/scripting/schema.py`)
* **Campos obligatorios:**
  - `title: str`
  - `hook_type: HookType` (`QUESTION`, `STATEMENT`, `SURPRISE`, etc.)
  - `hook: str`
  - `segments: List[ScriptSegment]` (Segmentos ordenados $1..N$)
  - `target_duration_sec: float`
  - `cta: str`
  - `metadata: Dict[str, Any]`
* **Nuevo invariante editorial:**
  - Presupuesto de palabras: $\text{Total words in } full\_text() \le \lfloor (target\_duration\_sec - 2.0) \times 2.1 \rfloor$.

### 4.4 `Concept` (`engine/creative/models.py`)
* **Campos preservados en SQLite:**
  - `id: str`, `idea_id: str`, `generation: int`, `concept_number: int` (1 a 3)
  - `title: str`, `hook_text: str`, `hook_type: str`, `angle_description: str`
  - `status: str` (`proposed`, `selected`, `converted`, `rejected`)
* **Conservación:** Cero cambios de esquema en base de datos. Se preserva compatibilidad con SQLite histórico.

### 4.5 `Render` (`engine/experiments/models.py`)
* **Campos preservados en SQLite:**
  - `id: str`, `experiment_run_id: str`, `variant_id: str`, `file_path: str`
  - `duration_seconds: float`, `width: int`, `height: int`, `fps: float`
  - `codec: str`, `file_size_bytes: int`, `qa_passed: bool`, `qa_report_json: str`
* **Conservación:** Cero cambios de esquema.
