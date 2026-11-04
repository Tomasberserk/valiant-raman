# STAGE 6 — BLOCK C: DESIGN SYSTEM & UI COMPONENTS SPECIFICATION
**Creative Workspace — Short-Form Video Studio**
*Document Version: 1.1 (Audited & Corrected Contractual Precision Baseline)*
*Operating Status: READ-ONLY AUDIT & DESIGN SYSTEM DEFINITION (Zero Code Touched)*

---

## 1. Executive Summary

This document establishes the definitive visual design system, token taxonomy, component architecture, responsive rules, accessibility standards, and FSM-to-DOM mapping for the Valiant Raman Creative Studio frontend (`STAGE 6`).

### Core Strategic Decisions
1. **Refinement & Systematization over Rewrite**: The existing UI possesses a distinctive, high-value dark creative workstation aesthetic (Midnight `#07090e`, Card `#121826`, Accent Cyan `#06b6d4` and Violet `#8b5cf6`). We preserve this foundation without imposing a generic CSS library or SaaS dashboard template; we systematize tokens, eliminate hardcoded values, rectify responsive layout bottlenecks, and enforce rigorous state machines.
2. **Strict Backend Capability Boundary**: The UI strictly reflects the data providable by Stage 5's frozen endpoints. Features requiring non-existent endpoints (such as `GET /api/runs` historical browsing, individual variant regeneration, cancellation in flight, or WebSockets) are classified as `BACKEND CAPABILITY NOT AVAILABLE` and excluded from the component tree.
3. **Multi-layer Resilience**: Transient network hiccups during polling trigger a dedicated, non-catastrophic `NETWORK_DEGRADED` visual state rather than falsely claiming pipeline failure. Polling employs single-flight locks to prevent request collisions.
4. **Architectural Separation for Implementation (Block D)**: Vanilla JS + CSS custom properties + semantic HTML5 remain the runtime stack. No npm packages, frameworks, or external CSS frameworks will be introduced. Block D will be executed in four gated phases (`D.1` Semantic HTML & a11y, `D.2` Tokens & CSS, `D.3` FSM & Polling, `D.4` Playwright E2E verification).

---

## 2. Existing UI Audit (index.html, studio.css, studio.js)

### 2.1 Strengths Identified (To Preserve)
- **Visual Personality**: High-contrast dark studio atmosphere matching audio/video production suites (DaVinci/Blender density) rather than generic business administration tools.
- **Dual Typography**: `Plus Jakarta Sans` for narrative prose and `JetBrains Mono` for metadata, badges, and progress percentages.
- **Vertical 9:16 Video Representation**: Responsive player layout tailored specifically for vertical short-form content.
- **Exclusive Video Playback**: Active event listeners already enforce single-video audio/video playback across variants A/B/C.
- **Micro-interactions**: Pulsing dot indicators and glowing buttons establish clear real-time activity.

### 2.2 Inconsistencies & Anti-Patterns Identified (To Systematize)
- **Hardcoded CSS Colors**: While `:root` defines core tokens, several component rules declare raw hex codes (`#04121d`, `#fda4af`, `#6ee7b7`, `#bae6fd`, `#e2e8f0`, `rgba(4, 7, 13, 0.75)`).
- **Responsive Overflow Vulnerability**: Grid definitions `minmax(310px, 1fr)` and `minmax(320px, 1fr)` combined with `1.5rem` or `2rem` padding overflow viewports of 320px to 360px widths (e.g., iPhone SE), causing horizontal scrollbars.
- **Accessibility & ARIA Deficits**:
  - `#ideaInput` lacks an explicit `<label for="...">`.
  - `#blockedModal` lacks `role="dialog"`, `aria-modal="true"`, and `aria-labelledby`.
  - Progress bar is a plain `<div>` lacking `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`.
  - Stepper stages lack ordered list semantics and `aria-current="step"`.
  - Missing visible `:focus-visible` rings on custom buttons and interactive cards.
- **Motion Accessibility**: No `@media (prefers-reduced-motion: reduce)` queries exist to dampen pulsing glows or modal transitions for users sensitive to motion.
- **State Monolith in studio.js**: State variables (`pollInterval`, `currentIdeaId`, etc.) live in a single closure without discrete FSM transitions or single-flight concurrency guarantees.

---

## 3. Design Tokens & Visual Primitives

### 3.1 Color System

Tokens are categorized into Surfaces, Borders, Typography, Semantic Statuses, and Brand Accents.

```css
:root {
  /* Surfaces & Canvas */
  --color-bg-canvas: #07090e;        /* Deepest background base */
  --color-bg-subtle: #0d121d;        /* Section wrapper / input base */
  --color-surface-card: #121826;     /* Primary container card */
  --color-surface-elevated: #182032; /* Hovered card / dropdown surface */
  --color-surface-overlay: rgba(7, 9, 14, 0.85); /* Modal backdrop / header blur */

  /* Borders & Dividers */
  --color-border-subtle: #1e293b;     /* Default 1px card/section border */
  --color-border-hover: #334155;      /* Subtle border brightening on hover */
  --color-border-strong: #475569;     /* Separator line between major zones */
  --color-border-focus: #38bdf8;      /* High-contrast keyboard focus ring */

  /* Typography / Foreground */
  --color-text-primary: #f8fafc;     /* Headings, titles, active labels */
  --color-text-secondary: #94a3b8;   /* Body paragraphs, descriptions */
  --color-text-muted: #64748b;       /* Metadata, timestamps, counters */
  --color-text-disabled: #475569;    /* Inactive buttons, disabled inputs */

  /* Creative Brand Accents */
  --color-accent-cyan: #06b6d4;      /* Primary studio action, ideation glow */
  --color-accent-cyan-hover: #0891b2;
  --color-accent-cyan-subtle: rgba(6, 182, 212, 0.12);
  --color-accent-cyan-glow: rgba(6, 182, 212, 0.25);

  --color-accent-violet: #8b5cf6;    /* Pipeline dispatch, generative power */
  --color-accent-violet-hover: #7c3aed;
  --color-accent-violet-subtle: rgba(139, 92, 246, 0.12);
  --color-accent-violet-glow: rgba(139, 92, 246, 0.25);

  /* Semantic State Tokens */
  --color-status-success: #10b981;   /* Completed runs, valid counters */
  --color-status-success-subtle: rgba(16, 185, 129, 0.12);
  --color-status-warning: #f59e0b;   /* Network degraded, attention */
  --color-status-warning-subtle: rgba(245, 158, 11, 0.12);
  --color-status-error: #f43f5e;     /* Pipeline failure, terminal validation */
  --color-status-error-subtle: rgba(244, 63, 94, 0.12);
  --color-status-info: #0284c7;      /* Empirical facts, informational banners */
  --color-status-info-subtle: rgba(2, 132, 199, 0.12);
}
```

### 3.2 Typography Scale

Dual font stack:
- **Narrative / UI**: `Plus Jakarta Sans`, system-ui, -apple-system, sans-serif
- **Technical / Telemetry**: `JetBrains Mono`, monospace

| Style Token | Font Family | Weight | Size | Line Height | Letter Spacing | Applied Elements |
|---|---|---|---|---|---|---|
| `text-display` | Sans | 800 | 2.0rem (32px) | 1.20 | -0.03em | Studio Brand Title |
| `text-h1` | Sans | 700 | 1.6rem (25.6px) | 1.25 | -0.025em | Section Headings (`<h2>`) |
| `text-h2` | Sans | 700 | 1.3rem (20.8px) | 1.30 | -0.02em | Modal / Launch Titles (`<h3>`) |
| `text-h3` | Sans | 700 | 1.15rem (18.4px) | 1.35 | -0.015em | Concept Card Titles (`<h4>`) |
| `text-body` | Sans | 400/500 | 1.0rem (16px) | 1.55 | 0 | Textarea input, descriptions |
| `text-body-sm`| Sans | 400/500 | 0.875rem (14px) | 1.50 | 0 | Sub-captions, toast messages |
| `text-badge` | Mono | 700 | 0.72rem (11.5px) | 1.00 | +0.08em | Step badges, format badges |
| `text-telemetry` | Mono | 600/700 | 0.75rem - 1.4rem | 1.20 | +0.02em | Stage tags, progress % digits |
| `text-meta` | Mono | 500 | 0.78rem (12.5px) | 1.30 | 0 | Char counters, durations, video dims |
| `text-btn` | Sans | 600/700 | 0.92rem (14.7px) | 1.00 | -0.01em | Primary & secondary buttons |

### 3.3 Spacing & Layout Scale

Base unit: `4px` / `0.25rem`. No arbitrary prime-number paddings.

```css
:root {
  --space-2xs: 0.25rem;  /* 4px  - Micro margins, dot gaps */
  --space-xs:  0.50rem;  /* 8px  - Icon + text gap, compact padding */
  --space-sm:  0.75rem;  /* 12px - Input padding Y, tag spacing */
  --space-md:  1.00rem;  /* 16px - Standard button padding, grid gap sm */
  --space-lg:  1.50rem;  /* 24px - Card internal padding, section margins */
  --space-xl:  2.00rem;  /* 32px - Large card padding, outer container gap */
  --space-2xl: 2.50rem;  /* 40px - Major section vertical spacing */
  --space-3xl: 3.50rem;  /* 56px - Hero zone spacing */
}
```

### 3.4 Borders, Radii & Depth

```css
:root {
  --radius-xs: 4px;   /* Inline code badges */
  --radius-sm: 8px;   /* Stage tags, small buttons, inner inputs */
  --radius-md: 12px;  /* Standard buttons, concept cards */
  --radius-lg: 18px;  /* Video cards, monitor container */
  --radius-xl: 24px;  /* Major ideation & launch hero cards */
  --radius-pill: 9999px; /* Status dots, pills, progress bars */

  /* Elevation Shadows */
  --shadow-flat: none;
  --shadow-raised: 0 4px 12px rgba(0, 0, 0, 0.35);
  --shadow-floating: 0 12px 28px rgba(0, 0, 0, 0.45);
  --shadow-overlay: 0 25px 60px rgba(0, 0, 0, 0.75);
}
```

---

## 4. Component Architecture & Responsibility Matrix

The UI is composed of 14 discrete, single-responsibility components with strict DOM boundaries:

```
[ AppShell ]
   ├── [ StudioHeader ]
   │      ├── [ BrandBadge & Title ]
   │      ├── [ BlockedTriggerButton ]
   │      └── [ EngineStatusPill ]
   ├── [ ToastContainer ] -> [ ToastItem ]
   ├── [ BlockedModalDialog ]
   ├── [ IdeaComposerCard ]
   │      ├── [ InputModeSelector ]
   │      ├── [ IdeaTextarea ]
   │      ├── [ SpeechRecognitionToolbar ]
   │      └── [ AnalyzeSubmitButton ]
   ├── [ ConceptsSection ]
   │      ├── [ SectionHeader & RegenerateAction ]
   │      └── [ ConceptsGrid ] -> [ ConceptCard ] (A / B / C)
   │             ├── [ HookTypeBadge ]
   │             ├── [ ConceptTitle & AngleDesc ]
   │             ├── [ CustomHookEditor ]
   │             └── [ ConceptActions (Select / Reject) ]
   ├── [ LaunchBannerCard ]
   │      ├── [ SelectedConceptBrief ]
   │      └── [ DispatchPipelineButton ]
   ├── [ RunMonitorCard ]
   │      ├── [ MonitorHeader (PulseDot + StatusLabel) ]
   │      ├── [ ProgressPercentageDigit ]
   │      ├── [ ProgressBarTrack & Fill ]
   │      ├── [ StageStepper ] -> [ ObservedStageTag ]
   │      └── [ NetworkDegradedBanner ]
   ├── [ ResultsSection ]
   │      ├── [ ResultsHeader & NewIdeaButton ]
   │      └── [ VariantsGrid ] -> [ VideoResultCard ] (A / B / C)
   │             ├── [ VariantCodeBadge (A / B / C) ]
   │             ├── [ VideoPlayerContainer (9:16) ]
   │             ├── [ VariantMetadataBar (Resolution, Duration, Format) ]
   │             └── [ DownloadMediaAction ]
   └── [ StudioFooter ]
```

> [!NOTE]
> **Component Precision**: "QA Stamp" is eliminated from `VideoResultCard`. Only factual, demonstrable metadata (Variant code, Hook type, Resolution, Duration, Format MP4) are displayed.

---

## 5. Component State Matrix

Every interactive component exhibits well-defined visual and functional states:

| Component | Default | Hover | Focus-Visible | Active / Pressed | Disabled | Loading / In-flight | Error / Alert |
|---|---|---|---|---|---|---|---|
| **Button (Primary)** | Cyan gradient, dark text | Brightness +10%, Y: -1px, glow | 2px solid `--color-border-focus`, offset 2px | Y: 0px, brightness -5% | Opacity 0.45, cursor: not-allowed | Spinner inline, text: *"Procesando..."* | N/A |
| **Button (Secondary)**| Charcoal bg, 1px border | Border: `--color-border-hover` | Focus ring cyan | Darker bg | Opacity 0.45 | Inline spinner | N/A |
| **IdeaTextarea** | Dark charcoal bg, subtle border | Border: `--color-border-hover` | Border: cyan, box-shadow: cyan glow | Border: cyan | Opacity 0.5, readonly | Spinner on overlay | Border: `--color-status-error`, red text |
| **ConceptCard** | Solid card, 1px subtle border | Y: -3px, border: cyan 40%, shadow | Focus ring on inner interactive elements | Border: cyan strong | N/A | Skeleton shimmer on load | Red tint if rejected |
| **ConceptCard (Selected)**| Cyan 2px border, cyan subtle glow | Elevated shadow | Retains focus outline | N/A | N/A | N/A | N/A |
| **LaunchBanner** | Violet-to-cyan gradient subtle border | Elevated glow | Retains focus ring on launch btn | Button pressed | Inactive / hidden | Launch button disabled, spinner | Banner turns amber if connection drops |
| **StageStep** | Muted text, subtle border | N/A | N/A | N/A | N/A | Active: cyan text, cyan border, subtle glow | Done: emerald text |
| **VideoPlayer** | Vertical 9:16 poster, play icon overlay | Controls visible | Focus ring on native video container | Playing (pauses siblings) | N/A | Native buffering spinner | Red message: *"No se pudo reproducir streaming"* |
| **Toast** | Semi-transparent card with type border | Opacity 1.0 | N/A | N/A | N/A | Slides in 0.25s | Auto-dismisses 4.5s |

---

## 6. FSM-to-UI Mapping & Operational Semantics

This mapping synchronizes the finite state machine defined in BLOCK B with visible DOM nodes:

| FSM State | Dominant View Zone | Hidden Sections | Primary Allowed Actions | Strictly Blocked Actions |
|---|---|---|---|---|
| `IDLE` | `IdeaComposerCard` active, empty or draft input | `ConceptsSection`, `LaunchSection`, `ProgressSection`, `ResultsSection` | Type idea text, toggle speech input, click *"Generar 3 Conceptos"* | Click launch, inspect results, trigger polling |
| `ANALYZING` | `IdeaComposerCard` disabled, button in loading state | All other sections | Cancel browser HTTP fetch via `AbortController` (local fetch abort only; does NOT cancel backend) | Edit idea text, submit new idea, interact with cards |
| `CONCEPTS_READY`| `ConceptsSection` with 3 cards | `LaunchSection`, `ProgressSection`, `ResultsSection` | Edit custom hook, click *"Elegir este"*, click *"Descartar"* | Launch pipeline without selecting a concept |
| `CONCEPT_CONFIGURING` | Concept card highlighted, textarea focused | `ProgressSection`, `ResultsSection` | Modify hook text, click *"Confirmar selección"* | Launch unselected variants |
| `LAUNCHING` | `LaunchSection` active, launch button in spinner state | `ProgressSection`, `ResultsSection` | None (atomic transition) | Double-click launch button, navigate away |
| `POLLING_ACTIVE`| `RunMonitorCard` active with live progress bar and stages | `ConceptsSection`, `LaunchSection`, `ResultsSection` | Observe telemetry, inspect stage badges | Re-submit ideas, modify selected concept |
| `NETWORK_DEGRADED`| `RunMonitorCard` + amber top banner *"Reconectando..."* | Same as `POLLING_ACTIVE` | Wait for automatic single-flight backoff | Treat as failure, reset application state |
| `COMPLETED` | `ResultsSection` with 3 vertical video players (A/B/C) | `ProgressSection`, `LaunchSection` | Play video variants, download MP4, click *"Nueva Idea"* | Re-render individual variant (not supported) |
| `RUN_FAILED` | `RunMonitorCard` in failure state (red accent, error info) | `ResultsSection` | Click **"Volver al estudio"** (primary) or **"Crear nuevo experimento"** (secondary) | Re-render / "Reintentar run" (no retry endpoint exists in backend) |

### 6.1 AbortController Semantics Rule
> [!IMPORTANT]
> `AbortController` may cancel an in-flight browser HTTP request only. It **MUST NEVER** be represented in the UI as cancelling, stopping, or reverting a backend pipeline execution. (Stage 5 possesses no run cancellation or abort endpoints).

### 6.2 Retry & Failure Semantics Rule
> [!IMPORTANT]
> Stage 5 has no `POST /api/runs/{id}/retry`. When a run enters `RUN_FAILED`, the UI provides:
> - **"Volver al estudio"** (returns to concept selection or editing to launch a *new* execution).
> - **"Crear nuevo experimento"** (clears active session and resets to IDLE).
> The UI must **never** offer a "Reintentar run" button, as rerun of an existing run ID is not a backend capability.

---

## 7. Backend Contract Mapping & Capability Boundaries

### 7.1 Field-to-UI Mapping (Stage 5 Contract Verified)

The monitor and result views derive strictly from the agreed contract fields:

```text
[RunStatusResponse]
  ├── run_id            --> Technical telemetry tag (Mono font: run_88600f0e)
  ├── status            --> Drives FSM transition: 'queued' | 'running' | 'completed' | 'failed'
  ├── progress_percent  --> Injected directly into width: `${progress_percent}%` & textual digit `#progressPercent`
  ├── stage             --> Processed via Stage Presentation Mapping (Observed string -> UI label)
  ├── renders           --> Hydrates `VariantsGrid` with List[RenderDTO]
  └── error             --> Rendered inside ErrorPanel on status == 'failed' (from error/error_message)

[RenderDTO]
  ├── id                --> Unique DOM key for the player container
  ├── variant_code      --> Badge label: "Variante A", "Variante B", "Variante C"
  ├── hook_type         --> Semantic tag: "QUESTION" (Cyan), "STATEMENT" (Violet), "SURPRISE" (Amber)
  ├── duration_seconds  --> Duration meta: `⏱ ${duration_seconds.toFixed(1)}s`
  ├── width / height    --> Resolution meta: `${width}x${height} (9:16)`
  └── media_url         --> Native <video><source src="${media_url}"> and <a> download link
```

> [!CAUTION]
> **No Synthetic Fields**: `RunStatusResponse.message` is completely eliminated from the UI specification. Human-readable status in the monitor is derived solely from the combination of `status`, `stage`, and `progress_percent`.

### 7.2 Stage Presentation Mapping (Backend Fact vs. UI Translation)

The contract guarantees:
```text
Backend fact: stage is a string.
```

The frontend maintains a translation table for known observed stage strings, but strictly adheres to this rule:
> **The frontend can translate known `stage` values to user-friendly labels, but it MUST NOT represent a stage as completed or present a rigid milestone sequence as fact unless the backend has actually reported or traversed it.**

| Observed Backend `stage` String | Frontend UI Friendly Label | Visual Status |
|---|---|---|
| `"queued"` | *"En cola de asignación"* | Stepper in waiting mode, pulsing indicator |
| `"scripting"` / `"variant_started"` | *"Estructura Narrativa & Hooks"* | Active stage indicator |
| `"voice"` | *"Síntesis Vocal Neural"* | Active stage indicator |
| `"subtitles"` | *"Sincronización de Subtítulos"* | Active stage indicator |
| `"rendering"` | *"Composición Audiovisual FFmpeg"* | Active stage indicator |
| `"qa"` / `"finalizing"` | *"Validación de Calidad Final"* | Active stage indicator |
| `"completed"` | *"Experimento Finalizado"* | All observed stages shown done |
| *Cualquier string no mapeado previamente* | Mostrado textualmente: `Etapa: "${stage}"` | Displayed dynamically as observed stage |

---

## 8. Responsive System & Breakpoint Specifications

### 8.1 Breakpoint Scale

| Breakpoint | Viewport Target | Layout Structure | Key Responsive Adjustments |
|---|---|---|---|
| **Compact Mobile** | `320px - 374px` (iPhone SE) | Single column, 100% width | Section padding reduced to `1.0rem`. Grid minmax set to `100%`. Textarea min-height `90px`. Video player occupies full container width with 9:16 aspect ratio. Header elements stack or hide subtitle. |
| **Standard Mobile** | `375px - 479px` (iPhone 13/14) | Single column | Section padding `1.25rem`. Toolbar buttons wrap cleanly with full-width primary button. |
| **Tablet Portrait** | `480px - 767px` | 1 to 2 columns | Concept cards flow 1 col. Launch banner stacks info and button vertically. |
| **Tablet Landscape**| `768px - 1023px` | 2 columns | Concepts grid: 2 cols + 1 col wrap. Brand subtitle displays in header. Monitor stages wrap into 2 rows. |
| **Desktop Base** | `1024px - 1279px` | 3 columns | Concepts grid: 3 equal columns (`repeat(3, 1fr)`). Video variants: 3 vertical cards side-by-side. |
| **Wide Desktop** | `1280px+` | Max-width container (`1100px`) centered | Generous margins, full ambient background glow enabled. |

### 8.2 Horizontal Overflow Prevention Rule
All grid containers must use `minmax(0, 1fr)` or dynamic calculation:
```css
/* CORRECT: Never overflows viewports smaller than 320px */
.concepts-grid, .variants-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
  gap: var(--space-md);
  width: 100%;
}
```

---

## 9. Accessibility (a11y) System

Target: **WCAG 2.1 Level AA Compliance**.

### 9.1 Keyboard Navigation Matrix
- `Tab` / `Shift+Tab`: Natural DOM tab order (Header -> Idea Composer -> Concepts -> Actions).
- `Enter` / `Space`: Activates buttons, toggles speech recognition, triggers concept selection.
- `Escape`: Closes `BlockedModalDialog` immediately and returns keyboard focus to `#btnBlocked`.

### 9.2 Focus Visibility
Interactive elements must display a high-contrast focus indicator without relying on default browser styling:
```css
:focus-visible {
  outline: 2px solid var(--color-border-focus);
  outline-offset: 2px;
}
```

### 9.3 Semantic & ARIA Enhancements for Block D
1. **Idea Composer**:
   - Add `<label for="ideaInput" class="visually-hidden">Premisa o idea creativa</label>`.
   - Add `aria-live="polite"` to `#charCount` to announce character validation without interrupting screen readers.
2. **Blocked Suggestions Modal**:
   - Attribute `role="dialog"`, `aria-modal="true"`, `aria-labelledby="blockedModalTitle"`.
   - Focus trapping implemented in JS during open state; focus returned to trigger on close.
3. **Progress Monitor**:
   - Container marked with `role="region" aria-label="Monitor de Renderizado en Vivo"`.
   - Progress bar marked with `role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"`.
   - Status updates announced via `aria-live="assertive"` on state transitions (`COMPLETED`, `FAILED`).
4. **Video Result Cards**:
   - Each player container labeled: `aria-label="Reproductor de video variante A: Gancho tipo Pregunta"`.
   - Download links contain descriptive text: `aria-label="Descargar video MP4 de la variante A"`.

---

## 10. Motion & Micro-Interactions Specification

### 10.1 Motion Values
```css
:root {
  --motion-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --motion-normal: 250ms cubic-bezier(0.4, 0, 0.2, 1);
  --motion-smooth: 400ms cubic-bezier(0.16, 1, 0.3, 1);
}
```

### 10.2 Interaction Rules
- **Pulsing Indicator**: Dot pulses between `scale(0.95)` and `scale(1.1)` with box-shadow dissipation to communicate background rendering activity.
- **Card Hover**: Subtle `translateY(-3px)` with border color interpolation. No excessive 3D tilts or jarring zoom effects.
- **Modal Transition**: Backdrop fades in `200ms`; modal card transitions `opacity` and `transform: scale(0.98) -> scale(1)`.

### 10.3 Reduced Motion Override
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
  .pulsing-dot {
    animation: none !important;
    box-shadow: 0 0 6px var(--color-accent-cyan) !important;
  }
}
```

---

## 11. Error & Resilience Visual Language

The UI categorizes disruptions into four distinct visual levels:

```
┌────────────────────────────────────────────────────────────────────────┐
│ 1. INLINE VALIDATION (Subtle / Local)                                  │
│    • Less than 10 characters in idea input                             │
│    • Counter displays warning text: "0 caracteres (mín. 10)"           │
│    • Analyze button disabled with 45% opacity                          │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│ 2. RECOVERABLE NETWORK DEGRADATION (Top Banner / Non-destructive)      │
│    • HTTP polling fetch drops / laptop sleep                           │
│    • Amber status pill: "⚠ Reconectando con el pipeline..."           │
│    • Backoff retries active in background; UI does NOT wipe state      │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│ 3. RESOURCE NOT FOUND / STALE SESSION (Toast / Reset Modal)            │
│    • 404 on run_id after DB purge or server restart                    │
│    • Amber Toast: "Sesión anterior no encontrada en el servidor."      │
│    • Safe cleanup of sessionStorage and graceful return to IDLE        │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│ 4. TERMINAL PIPELINE FAILURE (Monitor Error Panel)                     │
│    • Status == 'failed' returned by Stage 5 backend                    │
│    • Red progress bar, rose status badge: "Fallo en la Producción"     │
│    • Displays exact observed backend stage + error description         │
│    • Primary button: "Volver al Estudio"                               │
│    • Secondary button: "Crear Nuevo Experimento"                       │
│    • Strictly NO "Reintentar Run" button (unsupported by backend)     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Video & Media Representation Rules

1. **Aspect Ratio**: Every short-form video container is rigidly locked to `9 / 16`.
2. **Playback Isolation (Mutual Exclusion)**: Listening to the native HTML5 `play` event on any `<video>` element immediately pauses any other `<video>` element on the page.
3. **No Phantom Controls**: Buttons for "Regenerar solo variante B" or "Editar subtítulos de variante A" must never be rendered, as they are not supported by the backend.
4. **Factual Badges Only**: Only verifiable properties (`VARIANT A`, `MP4`, `1080x1920`, `⏱ 30.0s`) are rendered. No speculative "QA PASS" stamps.
5. **Streaming Failure Fallback**: If a video resource fails to stream (e.g. 404 or corrupted MP4), the card renders an inline fallback box:
   *"No se pudo cargar el stream de video. Intenta descargar el archivo directamente."*

---

## 13. Implementation Boundaries & Gated Execution Plan (For Block D)

To ensure maximum safety and zero architectural drift, BLOCK D will be executed in **four sequential, gated phases**:

```text
┌────────────────────────────────────────────────────────────────────────┐
│ D.1 — Semantic HTML & Accessibility                                    │
│       • index.html refactoring: labels, ARIA roles, dialog semantics   │
│       • Form and button accessibility enhancements                     │
│       └─► GATE D.1 AUDIT & APPROVAL                                    │
├────────────────────────────────────────────────────────────────────────┤
│ D.2 — Design Tokens, CSS & Responsive                                  │
│       • studio.css tokenization, removal of raw hex hardcodes          │
│       • Anti-overflow responsive grids for 320px+                      │
│       • prefers-reduced-motion queries & focus rings                   │
│       └─► GATE D.2 AUDIT & APPROVAL                                    │
├────────────────────────────────────────────────────────────────────────┤
│ D.3 — FSM Controller, Session Recovery & Polling                       │
│       • studio.js FSM state transitions                                │
│       • sessionStorage hydration for active_run_id                     │
│       • Single-flight lock polling with NETWORK_DEGRADED backoff       │
│       • Mutual exclusive video playback & clean error handling         │
│       └─► GATE D.3 AUDIT & APPROVAL                                    │
├────────────────────────────────────────────────────────────────────────┤
│ D.4 — Playwright / Browser Verification & Test Regression              │
│       • Automated UI verification and screenshot evidence              │
│       • Full repository regression (207/207 backend tests pass)        │
│       └─► STAGE 6 RELEASE GATE (LOCK)                                  │
└────────────────────────────────────────────────────────────────────────┘
```

### Strictly Forbidden in BLOCK D:
- Modifying any Python file in `engine/`, `web/routes/`, `web/schemas.py`, or `storage/`.
- Altering the SQLite schema or touching `storage/experiments.db`.
- Introducing any npm build tool (Webpack, Vite), JS framework (React, Vue), or CSS preprocessor/framework (Tailwind, Bootstrap).

---

## 14. BLOCK C Acceptance Checklist

- [x] Full audit of `index.html`, `studio.css`, and `studio.js` completed.
- [x] Complete design token taxonomy defined (Colors, Typography, Spacing, Radii, Shadows).
- [x] `RunStatusResponse.message` removed from specification (monitor relies strictly on `status`, `stage`, `progress_percent`, `renders`, `error`).
- [x] StageStepper distinguished between backend fact (`stage: string`) and presentation mapping, prohibiting false completed milestones.
- [x] "QA Stamp" removed from video cards, retaining only demonstrable facts (Variant code, hook type, resolution, duration).
- [x] `AbortController` explicitly documented as browser-fetch abort only, never backend pipeline cancellation.
- [x] Retry semantics corrected: "Volver al estudio" / "Crear nuevo experimento" replacing non-existent "Reintentar run".
- [x] Four-tier gated execution roadmap established for BLOCK D (`D.1` -> `D.2` -> `D.3` -> `D.4`).
- [x] Zero backend capabilities invented; capability boundaries preserved.
- [x] Zero production code files modified during BLOCK C.
