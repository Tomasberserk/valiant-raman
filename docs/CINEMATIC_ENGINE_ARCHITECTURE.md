# Arquitectura del Motor Cinemático Multiescena (Cinematic Engine)

## 1. Contexto y Auditoría Dual (Claude 3.5 Sonnet & ChatGPT o1)
A partir de la auditoría de código tras la falla en prompts narrativos de acción (donde el prompt `"un chico encuentra una espada..."` colapsaba a una plantilla de curiosidad documental `¿Sabías que existe un hecho fascinante...?`), se rediseñó el núcleo del motor audiovisual para separar fundamentalmente los modos de contenido y establecer el contrato canónico de **Storyboard Multitoma**.

### Decisiones de Auditoría Aprobadas (Consenso Dual)
1. **Unidad Atómica de Producción:** La toma (`VisualShot`), no el video completo ni un solo fondo estático por video. Duración estricta entre 2.0s y 6.0s (típicamente 2.5s–4.5s).
2. **Modo Explícito y Detección Temprana (`ContentModeRouter`):**
   - `NARRATIVE_FICTION`: Generación dramática de beats, personajes, estilo cinematográfico y SFX.
   - `FACTUAL_CURIOSITY`: Datos comprobables, hook educativo, tomas de apoyo/stock.
3. **Erradicación de Fallbacks Silenciosos:**
   - La librería jamás inyectará plantillas de relleno si falla un LLM o falta una API key. Se lanzan excepciones tipadas (`KnowledgeNotFoundError`, `SemanticPolicyViolationError`).
4. **Contrato Canónico `Storyboard`:**
   - Estructura Pydantic v2 inmutable (`frozen=True`, `extra='forbid'`).
   - `Scene.duration_sec = sum(shots.duration_sec)`.
   - `AudioTrackPlan` con `music_intensity` por escena, `music_dip_start`/`end` para silencios dramáticos, y `sfx_cues` con offset relativo a la escena.
5. **Separación Estricta de Plan y Render:**
   - El `Storyboard` describe la intención creativa.
   - `ShotRenderResult` almacena las rutas de los archivos generados y sus metadatos de render.
6. **Movimientos de Cámara Ken Burns Anti-Jitter:**
   - Canvas intermedio 2x (`2160x3840`) antes del `zoompan` para evitar temblor subpixel en FFmpeg.

---

## 2. Mapa de Fases de Implementación

### Fase 0: Fail-Fast, Mode Router & Anti-Template Guardrails (COMPLETADA)
- `engine/creative/modes.py`: `ContentModeRouter` con detección regex y heurística de modo narrativo vs factual.
- `engine/creative/knowledge.py`: Eliminado el generador ficticio de cápsulas `dynamic_custom`.
- `engine/story/semantic_qa.py`: `SemanticAntiTemplateValidator` que bloquea frases cliché de IA (`"¿Sabías que existe..."`, `"Al investigar a fondo..."`).
- `engine/creative/interpreter.py`: Genera conceptos narrativos dramáticos directos sin consultar `KnowledgeBank`.

### Fase 1: Storyboard Engine & Thin-Slice Pipeline (COMPLETADA)
- `engine/story/storyboard.py`: Modelos Pydantic v2 canónicos (`VisualShot`, `Scene`, `Storyboard`, `AudioTrackPlan`, `SfxCue`, `CharacterAnchor`, `StyleBible`, etc.).
- `engine/story/storyboard_planner.py`: Planificador dramático de 6 beats (`HOOK`, `INCIDENT`, `TURNING_POINT`, `ESCALATION`, `CLIMAX`, `CLIFFHANGER`).
- `engine/story/camera_engine.py`: Motor de animación de cámara Ken Burns (`PUSH_IN`, `PULL_OUT`, `PAN_LEFT`, `PAN_RIGHT`, `TILT_UP`, `STATIC`) con upscale 2x anti-jitter.
- `engine/story/mock_visual_renderer.py`: Renderizador de diagnóstico vertical (`1080x1920`) con tipografía cinemática e indicadores de toma.
- `engine/story/timeline_assembler.py`: Ensamblador de línea de tiempo con concatenación de tomas e inyección de audio master en MP4.
- Verificación: 15/15 tests pasando en `tests/test_golden_narrative.py`, `tests/test_storyboard_contracts.py` y `tests/test_thin_slice_pipeline.py`.

### Fase 2: Visual Orchestrator & Asset Generation (EN PROCESO)
- Protocolo `ImageProvider` extensible (`MockImageProvider`, `ComfyUIProvider`, `FluxProvider`, `DallEProvider`).
- Inyección obligatoria de `CharacterAnchor` en el `action_prompt_en` de cada toma para mantener consistencia visual.
- Caché de tomas (`shot_id` + hash del prompt) para renderizado idempotente y reanudable.

### Fase 3: Audio Director & Sidechain Ducking
- Generación de SFX (`sound_tag` mapeado a librería de efectos local / procedimental).
- Mezcla multipista en FFmpeg (`sidechaincompress` para voz sobre BGM, `adelay` para SFX por toma).
- Silencios dramáticos (`music_dip_start`/`music_dip_end`).

### Fase 4: Integración al Creative Service y Studio Web UI
- Exposición de endpoints de storyboard en FastAPI.
- Vista previa de tomas en el reproductor interactivo de variantes.
