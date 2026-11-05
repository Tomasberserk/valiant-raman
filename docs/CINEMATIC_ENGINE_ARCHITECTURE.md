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

### Fase 2: Visual Orchestrator & Asset Generation (COMPLETADA)
- `engine/visual/providers.py`: Protocolo `ImageProvider` extensible (`MockImageProvider`, `ProceduralCanvasProvider`, `OpenAIImageProvider`, `ComfyUIProvider`).
- Inyección canónica de `CharacterAnchor` en el `action_prompt_en` de cada toma garantizando consistencia visual y de estilo.
- `engine/visual/cache.py`: Caché de tomas (`VisualAssetCache`) con hash SHA256 para renderizado idempotente y preservación de cuota.
- `engine/visual/orchestrator.py`: Orquestación multi-toma generando keyframes y renders de cámara Ken-Burns.
- Verificación: 5/5 tests pasando en `tests/test_visual_orchestrator.py`.

### Fase 3: Audio Director & Sidechain Ducking (COMPLETADA)
- `engine/audio/sfx_library.py`: Librería y sintetizador acústico procedural de efectos sonoros (`sword_blade_ring`, `thunder_crack`, `monster_screech`, `cinematic_whoosh`).
- `engine/audio/music_director.py`: Generador de bandas sonoras atmosféricas BGM según `music_mood`.
- `engine/audio/audio_director.py`: Mezclador de audio multipista en FFmpeg con posicionamiento milimétrico de SFX (`adelay`), atenuación de volumen (`volume_db`) y mezcla estéreo a 48kHz.
- Verificación: 3/3 tests pasando en `tests/test_audio_director.py`.

### Fase 4: Integración al Pipeline Central & End-to-End Test (COMPLETADA)
- `engine/pipeline.py`: Bifurcación inteligente del pipeline. Cuando `content_mode == "narrative_fiction"`, se despacha el flujo cinemático de Storyboard (planificación dramática, orquestación visual de tomas, mezcla de SFX/BGM y ensamblado de línea de tiempo con `TimelineAssembler`).
- `tests/test_end_to_end_narrative_pipeline.py`: Prueba de integración end-to-end con el prompt de la espada, verificando captura de idea, selección de concepto narrativo, generación de las 6 tomas individuales, composición del master 9:16 y registro de render en SQLite.
- Verificación: 24/24 tests pasando en la suite completa cinemática.
