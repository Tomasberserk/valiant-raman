/**
 * Creative Workspace Studio - Vanilla JS Controller
 * STAGE 6: Production-grade FSM, Single-Flight Polling & Session Hydration
 */

document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  const ideaInput = document.getElementById('ideaInput');
  const charCount = document.getElementById('charCount');
  const btnSpeech = document.getElementById('btnSpeech');
  const speechStatus = document.getElementById('speechStatus');
  const btnAnalyze = document.getElementById('btnAnalyze');

  const conceptsSection = document.getElementById('conceptsSection');
  const conceptsGrid = document.getElementById('conceptsGrid');
  const conceptIdeaTheme = document.getElementById('conceptIdeaTheme');
  const btnRegenerate = document.getElementById('btnRegenerate');

  const launchSection = document.getElementById('launchSection');
  const selectedConceptTitle = document.getElementById('selectedConceptTitle');
  const selectedConceptHook = document.getElementById('selectedConceptHook');
  const btnLaunch = document.getElementById('btnLaunch');

  const progressSection = document.getElementById('progressSection');
  const networkBanner = document.getElementById('networkBanner');
  const progressBar = document.getElementById('progressBar');
  const progressBarTrack = document.getElementById('progressBarTrack');
  const progressPercent = document.getElementById('progressPercent');
  const monitorStatusText = document.getElementById('monitorStatusText');
  const monitorMessage = document.getElementById('monitorMessage');
  const monitorFailureActions = document.getElementById('monitorFailureActions');
  const btnReturnToStudio = document.getElementById('btnReturnToStudio');
  const btnRestartExperiment = document.getElementById('btnRestartExperiment');

  const stageScript = document.getElementById('stageScript');
  const stageVoice = document.getElementById('stageVoice');
  const stageSubtitles = document.getElementById('stageSubtitles');
  const stageRender = document.getElementById('stageRender');
  const stageQA = document.getElementById('stageQA');

  const resultsSection = document.getElementById('resultsSection');
  const variantsGrid = document.getElementById('variantsGrid');
  const btnNewIdea = document.getElementById('btnNewIdea');

  const btnBlocked = document.getElementById('btnBlocked');
  const blockedModal = document.getElementById('blockedModal');
  const btnCloseBlocked = document.getElementById('btnCloseBlocked');
  const blockedFact = document.getElementById('blockedFact');
  const blockedOpportunity = document.getElementById('blockedOpportunity');
  const blockedHypothesis = document.getElementById('blockedHypothesis');
  const btnUseHypothesis = document.getElementById('btnUseHypothesis');

  // --- FSM States ---
  const STATES = {
    IDLE: 'IDLE',
    ANALYZING: 'ANALYZING',
    CONCEPTS_READY: 'CONCEPTS_READY',
    CONCEPT_CONFIGURING: 'CONCEPT_CONFIGURING',
    LAUNCHING: 'LAUNCHING',
    POLLING_ACTIVE: 'POLLING_ACTIVE',
    NETWORK_DEGRADED: 'NETWORK_DEGRADED',
    COMPLETED: 'COMPLETED',
    RUN_FAILED: 'RUN_FAILED'
  };

  let currentState = STATES.IDLE;

  // --- Volatile Memory State ---
  let currentIdeaId = null;
  let currentConcepts = [];
  let selectedConceptId = null;
  let activeRunId = null;
  let speechRecognition = null;
  let isRecording = false;

  // --- Single-Flight Polling State ---
  let isPollingActive = false;
  let isFetchInFlight = false;
  let pollTimeoutId = null;
  let consecutiveNetworkFailures = 0;

  // --- Stage Mapping Contract ---
  const STAGE_LABELS = {
    'queued': 'En cola de asignación de worker FIFO...',
    'scripting': '1. Estructura Narrativa & Hooks',
    'variant_started': '1. Estructura Narrativa & Hooks',
    'voice': '2. Síntesis Vocal Neural',
    'subtitles': '3. Sincronización de Subtítulos',
    'rendering': '4. Composición Audiovisual FFmpeg',
    'qa': '5. Control de Calidad Audiovisual',
    'finalizing': '5. Finalizando empaquetado de variantes...',
    'completed': '¡Experimento Renderizado Exitosamente!'
  };

  // --- State Transition Controller ---
  function transitionTo(newState, data = {}) {
    console.debug(`[FSM] Transition: ${currentState} -> ${newState}`, data);
    currentState = newState;

    switch (newState) {
      case STATES.IDLE:
        stopPolling();
        clearSessionPersistence();
        btnAnalyze.disabled = ideaInput.value.trim().length < 10;
        btnAnalyze.innerHTML = '<span>Generar 3 Conceptos</span><span class="btn-arrow" aria-hidden="true">→</span>';
        conceptsSection.classList.add('hidden');
        launchSection.classList.add('hidden');
        progressSection.classList.add('hidden');
        resultsSection.classList.add('hidden');
        if (networkBanner) networkBanner.classList.add('hidden');
        if (monitorFailureActions) monitorFailureActions.classList.add('hidden');
        break;

      case STATES.ANALYZING:
        btnAnalyze.disabled = true;
        btnAnalyze.innerHTML = '<span>Interpretando idea...</span>';
        conceptsSection.classList.add('hidden');
        launchSection.classList.add('hidden');
        progressSection.classList.add('hidden');
        resultsSection.classList.add('hidden');
        break;

      case STATES.CONCEPTS_READY:
        btnAnalyze.disabled = false;
        btnAnalyze.innerHTML = '<span>Generar 3 Conceptos</span><span class="btn-arrow" aria-hidden="true">→</span>';
        conceptsSection.classList.remove('hidden');
        launchSection.classList.add('hidden');
        progressSection.classList.add('hidden');
        resultsSection.classList.add('hidden');
        conceptsSection.scrollIntoView({ behavior: 'smooth' });
        break;

      case STATES.CONCEPT_CONFIGURING:
        launchSection.classList.remove('hidden');
        progressSection.classList.add('hidden');
        resultsSection.classList.add('hidden');
        launchSection.scrollIntoView({ behavior: 'smooth' });
        break;

      case STATES.LAUNCHING:
        btnLaunch.disabled = true;
        btnLaunch.innerHTML = '<span>Encolando producción...</span>';
        break;

      case STATES.POLLING_ACTIVE:
        if (networkBanner) networkBanner.classList.add('hidden');
        if (monitorFailureActions) monitorFailureActions.classList.add('hidden');
        launchSection.classList.add('hidden');
        conceptsSection.classList.add('hidden');
        progressSection.classList.remove('hidden');
        resultsSection.classList.add('hidden');
        monitorStatusText.textContent = 'Ejecutando pipeline...';
        monitorStatusText.style.color = '';
        progressSection.scrollIntoView({ behavior: 'smooth' });
        break;

      case STATES.NETWORK_DEGRADED:
        if (networkBanner) networkBanner.classList.remove('hidden');
        break;

      case STATES.COMPLETED:
        stopPolling();
        progressSection.classList.add('hidden');
        resultsSection.classList.remove('hidden');
        resultsSection.scrollIntoView({ behavior: 'smooth' });
        break;

      case STATES.RUN_FAILED:
        stopPolling();
        monitorStatusText.textContent = 'Fallo en la producción';
        monitorStatusText.style.color = 'var(--color-status-error)';
        if (monitorFailureActions) monitorFailureActions.classList.remove('hidden');
        if (networkBanner) networkBanner.classList.add('hidden');
        break;
    }
  }

  // --- Session Storage Hydration (F5 Resilience) ---
  function hydrateSession() {
    const savedRunId = sessionStorage.getItem('active_run_id');
    if (savedRunId) {
      console.info(`[Hydration] Active run recovered from sessionStorage: ${savedRunId}`);
      activeRunId = savedRunId;
      transitionTo(STATES.POLLING_ACTIVE);
      startStatusPolling(activeRunId);
    } else {
      transitionTo(STATES.IDLE);
    }
  }

  function persistActiveRun(runId, conceptId) {
    sessionStorage.setItem('active_run_id', runId);
    if (conceptId) sessionStorage.setItem('active_concept_id', conceptId);
  }

  function clearSessionPersistence() {
    sessionStorage.removeItem('active_run_id');
    sessionStorage.removeItem('active_concept_id');
  }

  // --- 1. IDEA INPUT & VALIDATION ---
  function updateCharCount() {
    const len = ideaInput.value.trim().length;
    charCount.textContent = `${len} caracteres ${len >= 10 ? '✓' : '(mín. 10)'}`;
    charCount.classList.toggle('valid', len >= 10);
    btnAnalyze.disabled = len < 10 || currentState === STATES.ANALYZING;
  }

  ideaInput.addEventListener('input', updateCharCount);

  // --- 2. WEB SPEECH API SUPPORT ---
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRec) {
    speechRecognition = new SpeechRec();
    speechRecognition.continuous = true;
    speechRecognition.interimResults = true;
    speechRecognition.lang = 'es-ES';

    speechRecognition.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        transcript += event.results[i][0].transcript;
      }
      if (transcript.trim()) {
        ideaInput.value = (ideaInput.value + ' ' + transcript).trim();
        updateCharCount();
      }
    };

    speechRecognition.onerror = (err) => {
      console.warn('Speech recognition error:', err);
      stopRecording();
    };

    speechRecognition.onend = () => {
      stopRecording();
    };

    btnSpeech.addEventListener('click', () => {
      if (!isRecording) {
        startRecording();
      } else {
        stopRecording();
      }
    });
  } else {
    btnSpeech.disabled = true;
    btnSpeech.title = 'Tu navegador no soporta Web Speech API. Puedes escribir tu idea directamente.';
    speechStatus.textContent = 'Voz no soportada';
  }

  function startRecording() {
    try {
      speechRecognition.start();
      isRecording = true;
      speechStatus.textContent = 'Escuchando...';
      btnSpeech.classList.add('recording');
    } catch (e) {
      console.warn(e);
    }
  }

  function stopRecording() {
    if (speechRecognition && isRecording) {
      speechRecognition.stop();
    }
    isRecording = false;
    speechStatus.textContent = 'Dictar idea';
    btnSpeech.classList.remove('recording');
  }

  // --- Toast Notifications ---
  function showToast(message, type = 'error') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = type === 'success' ? '✓' : (type === 'error' ? '⚠' : (type === 'warning' ? '⚡' : 'ℹ'));
    toast.innerHTML = `<span aria-hidden="true">${icon}</span><span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 350);
    }, 4500);
  }

  // --- 3. GENERATE CONCEPTS (POST /api/ideas) ---
  btnAnalyze.addEventListener('click', async () => {
    const text = ideaInput.value.trim();
    if (text.length < 10) return;

    transitionTo(STATES.ANALYZING);

    try {
      const response = await fetch('/api/ideas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_text: text, input_type: 'text' })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Error al capturar idea');
      }

      const ideaData = await response.json();
      currentIdeaId = ideaData.id;
      currentConcepts = ideaData.concepts;

      conceptIdeaTheme.textContent = `Tema central detectado: "${ideaData.theme}" (${ideaData.suggested_format})`;
      renderConcepts(currentConcepts);

      transitionTo(STATES.CONCEPTS_READY);
    } catch (error) {
      showToast(error.message, 'error');
      transitionTo(STATES.IDLE);
    }
  });

  // Render Concept Cards
  function renderConcepts(concepts) {
    conceptsGrid.innerHTML = '';
    concepts.forEach(concept => {
      const card = document.createElement('div');
      card.className = `concept-card ${concept.status === 'selected' ? 'selected' : (concept.status === 'rejected' ? 'rejected' : '')}`;
      card.dataset.id = concept.id;

      const tagClass = concept.hook_type === 'QUESTION' ? 'tag-question' : 
                       (concept.hook_type === 'STATEMENT' ? 'tag-statement' : 'tag-surprise');

      card.innerHTML = `
        <div class="concept-top">
          <span class="concept-tag ${tagClass}">${concept.hook_type}</span>
          <span class="concept-number">#0${concept.concept_number}</span>
        </div>
        <h4 class="concept-title">${escapeHtml(concept.title)}</h4>
        <div class="concept-hook-label" id="labelHook${concept.id}">Gancho inicial (Editable):</div>
        <textarea class="concept-hook-input" rows="2" data-id="${concept.id}" aria-labelledby="labelHook${concept.id}">${escapeHtml(concept.hook_text)}</textarea>
        <p class="concept-angle">${escapeHtml(concept.angle_description)}</p>
        <div class="concept-actions">
          <button class="btn btn-primary btn-sm btn-select" data-id="${concept.id}" aria-label="Elegir concepto ${concept.concept_number}: ${escapeHtml(concept.title)}">Elegir este</button>
          <button class="btn btn-ghost btn-sm btn-reject" data-id="${concept.id}" aria-label="Descartar concepto ${concept.concept_number}">Descartar</button>
        </div>
      `;

      card.querySelector('.btn-select').addEventListener('click', () => selectConcept(concept));
      card.querySelector('.btn-reject').addEventListener('click', () => rejectConcept(concept.id));

      conceptsGrid.appendChild(card);
    });
  }

  // --- 4. CONCEPT ACTIONS (SELECT / REJECT) ---
  async function selectConcept(concept) {
    try {
      const inputEl = document.querySelector(`.concept-hook-input[data-id="${concept.id}"]`);
      const editedHook = inputEl ? inputEl.value.trim() : concept.hook_text;

      const resp = await fetch(`/api/concepts/${concept.id}/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ custom_hook: editedHook })
      });
      if (!resp.ok) throw new Error('No se pudo seleccionar el concepto');

      const updatedConcept = await resp.json();
      selectedConceptId = concept.id;

      // Update card visual states
      document.querySelectorAll('.concept-card').forEach(c => {
        if (c.dataset.id === concept.id) {
          c.classList.add('selected');
          c.classList.remove('rejected');
        } else {
          c.classList.remove('selected');
          c.classList.add('rejected');
        }
      });

      // Show launch banner with updated text
      selectedConceptTitle.textContent = updatedConcept.title;
      selectedConceptHook.textContent = `Gancho (${updatedConcept.hook_type}): "${updatedConcept.hook_text}"`;
      transitionTo(STATES.CONCEPT_CONFIGURING);
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  async function rejectConcept(conceptId) {
    try {
      await fetch(`/api/concepts/${conceptId}/reject`, { method: 'POST' });
      const card = document.querySelector(`.concept-card[data-id="${conceptId}"]`);
      if (card) card.classList.add('rejected');
    } catch (e) {
      console.warn(e);
    }
  }

  // Regenerate Concepts
  btnRegenerate.addEventListener('click', async () => {
    if (!currentIdeaId) return;
    btnRegenerate.disabled = true;
    btnRegenerate.textContent = '↻ Generando...';
    try {
      const resp = await fetch(`/api/ideas/${currentIdeaId}/concepts`);
      if (resp.ok) {
        const concepts = await resp.json();
        renderConcepts(concepts);
      }
    } finally {
      btnRegenerate.disabled = false;
      btnRegenerate.textContent = '↻ Proponer otros 3';
    }
  });

  // --- 5. LAUNCH EXPERIMENT (POST /api/concepts/{id}/launch) ---
  btnLaunch.addEventListener('click', async () => {
    if (!selectedConceptId) return;

    transitionTo(STATES.LAUNCHING);

    try {
      const resp = await fetch(`/api/concepts/${selectedConceptId}/launch`, { method: 'POST' });
      if (!resp.ok && resp.status !== 202) {
        const err = await resp.json();
        throw new Error(err.detail || 'Fallo al despachar experimento');
      }

      const launchData = await resp.json();
      activeRunId = launchData.run_id;

      // Persist run in sessionStorage for F5 recovery
      persistActiveRun(activeRunId, selectedConceptId);

      // Transition and begin single-flight status polling
      transitionTo(STATES.POLLING_ACTIVE);
      startStatusPolling(activeRunId);
    } catch (error) {
      showToast(`Error al lanzar: ${error.message}`, 'error');
      btnLaunch.disabled = false;
      btnLaunch.innerHTML = '<span class="rocket-icon" aria-hidden="true">🚀</span><span>Producir Experimento A/B/C</span>';
      transitionTo(STATES.CONCEPT_CONFIGURING);
    }
  });

  // --- 6. SINGLE-FLIGHT POLLING & RESILIENCE CONTROLLER ---
  function startStatusPolling(runId) {
    stopPolling();
    isPollingActive = true;
    consecutiveNetworkFailures = 0;

    pollTick(runId);
  }

  function stopPolling() {
    isPollingActive = false;
    isFetchInFlight = false;
    if (pollTimeoutId) {
      clearTimeout(pollTimeoutId);
      pollTimeoutId = null;
    }
  }

  async function pollTick(runId) {
    if (!isPollingActive) return;

    // Single-Flight lock guard: prevent stacking requests
    if (isFetchInFlight) {
      console.debug('[Polling] Request already in flight, skipping tick');
      return;
    }

    isFetchInFlight = true;

    try {
      const resp = await fetch(`/api/runs/${runId}/status`);

      if (!resp.ok) {
        if (resp.status === 404) {
          // Stale session or wiped DB
          console.warn(`[Polling] Run ${runId} not found (404). Cleaning stale session.`);
          showToast('Sesión no encontrada en el servidor. Reiniciando estudio.', 'warning');
          transitionTo(STATES.IDLE);
          return;
        }
        throw new Error(`HTTP ${resp.status}`);
      }

      const data = await resp.json();

      // Successful tick: restore normal polling state if previously degraded
      if (currentState === STATES.NETWORK_DEGRADED) {
        transitionTo(STATES.POLLING_ACTIVE);
      }
      consecutiveNetworkFailures = 0;

      updateProgressUI(data);

      if (data.status === 'completed') {
        clearSessionPersistence();
        setTimeout(() => {
          transitionTo(STATES.COMPLETED);
          showResults(data);
        }, 500);
        return;
      } else if (data.status === 'failed') {
        clearSessionPersistence();
        transitionTo(STATES.RUN_FAILED);
        monitorMessage.textContent = data.error_message || data.error || 'Ocurrió un error inesperado durante el renderizado audiovisual.';
        return;
      }

      // Schedule next tick if still running or queued
      if (isPollingActive) {
        pollTimeoutId = setTimeout(() => pollTick(runId), 1500);
      }
    } catch (err) {
      console.warn('[Polling] Transient network error:', err);
      consecutiveNetworkFailures++;

      // Enter NETWORK_DEGRADED mode: inform user, apply backoff, DO NOT wipe state
      transitionTo(STATES.NETWORK_DEGRADED);

      const backoffMs = Math.min(12000, 1500 * Math.pow(1.5, consecutiveNetworkFailures));
      if (isPollingActive) {
        pollTimeoutId = setTimeout(() => pollTick(runId), backoffMs);
      }
    } finally {
      isFetchInFlight = false;
    }
  }

  // Update Progress UI strictly from contract fields
  function updateProgressUI(data) {
    const percent = Math.min(100, Math.max(0, data.progress_percent || 0));
    progressBar.style.width = `${percent}%`;
    progressPercent.textContent = `${percent}%`;
    if (progressBarTrack) progressBarTrack.setAttribute('aria-valuenow', percent);

    // Derived Stage Label: no synthetic message
    const rawStage = (data.stage || '').toLowerCase();
    const stageDisplay = STAGE_LABELS[rawStage] || (rawStage ? `Etapa observada: "${data.stage}"` : 'Procesando pipeline audiovisual...');
    monitorMessage.textContent = stageDisplay;

    // Stage tags milestone presentation
    resetStageTags();

    if (rawStage === 'scripting' || rawStage === 'variant_started') {
      setActiveStage(stageScript);
    } else if (rawStage === 'voice') {
      setDoneStage(stageScript);
      setActiveStage(stageVoice);
    } else if (rawStage === 'subtitles') {
      setDoneStage(stageScript);
      setDoneStage(stageVoice);
      setActiveStage(stageSubtitles);
    } else if (rawStage === 'rendering') {
      setDoneStage(stageScript);
      setDoneStage(stageVoice);
      setDoneStage(stageSubtitles);
      setActiveStage(stageRender);
    } else if (rawStage === 'qa' || rawStage === 'finalizing') {
      setDoneStage(stageScript);
      setDoneStage(stageVoice);
      setDoneStage(stageSubtitles);
      setDoneStage(stageRender);
      setActiveStage(stageQA);
    } else if (data.status === 'completed') {
      setDoneStage(stageScript);
      setDoneStage(stageVoice);
      setDoneStage(stageSubtitles);
      setDoneStage(stageRender);
      setDoneStage(stageQA);
    }
  }

  function resetStageTags() {
    [stageScript, stageVoice, stageSubtitles, stageRender, stageQA].forEach(t => {
      t.className = 'stage-tag';
    });
  }

  function setActiveStage(el) { if (el) el.className = 'stage-tag active'; }
  function setDoneStage(el) { if (el) el.className = 'stage-tag done'; }

  // --- Failure Actions (Gate D.3: Return to Studio / New Experiment) ---
  if (btnReturnToStudio) {
    btnReturnToStudio.addEventListener('click', () => {
      // Return to concept selection so user can pick another concept or re-dispatch
      if (currentConcepts && currentConcepts.length > 0) {
        transitionTo(STATES.CONCEPTS_READY);
      } else {
        transitionTo(STATES.IDLE);
      }
    });
  }

  if (btnRestartExperiment) {
    btnRestartExperiment.addEventListener('click', () => {
      ideaInput.value = '';
      updateCharCount();
      transitionTo(STATES.IDLE);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // --- 7. SHOW FINAL RESULTS & VIDEO PLAYERS ---
  function showResults(data) {
    variantsGrid.innerHTML = '';

    const renders = data.renders || [];
    renders.forEach(r => {
      const card = document.createElement('div');
      card.className = 'variant-card';

      const tagClass = r.hook_type === 'QUESTION' ? 'tag-question' : 
                       (r.hook_type === 'STATEMENT' ? 'tag-statement' : 'tag-surprise');

      card.innerHTML = `
        <div class="variant-header">
          <div class="variant-code-badge">Variante ${r.variant_code}</div>
          <span class="concept-tag ${tagClass}">${r.hook_type}</span>
          <span class="concept-tag" style="background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3);">MP4</span>
        </div>

        <div class="video-container">
          <video class="video-player" controls preload="metadata" playsinline aria-label="Reproductor de video variante ${r.variant_code}: Gancho ${r.hook_type}">
            <source src="${r.media_url}" type="video/mp4">
            Tu navegador no soporta reproducción de video MP4.
          </video>
        </div>

        <div class="variant-meta">
          <span>${r.width}x${r.height} (9:16)</span>
          <span>⏱ ${r.duration_seconds.toFixed(1)}s</span>
        </div>

        <a href="${r.media_url}" download="variant_${r.variant_code}.mp4" class="btn btn-secondary btn-sm" style="width: 100%;" aria-label="Descargar archivo MP4 de la variante ${r.variant_code}">
          ⬇ Descargar MP4
        </a>
      `;

      variantsGrid.appendChild(card);
    });

    // Mutual Exclusive Playback: pausing sibling videos when one starts
    const players = variantsGrid.querySelectorAll('.video-player');
    players.forEach(player => {
      player.addEventListener('play', () => {
        players.forEach(other => {
          if (other !== player && !other.paused) {
            other.pause();
          }
        });
      });
    });
  }

  // --- 8. BLOCKED SUGGESTIONS MODAL (GET /api/blocked) ---
  let lastFocusedElement = null;

  function openBlockedModal() {
    lastFocusedElement = document.activeElement;
    btnBlocked.setAttribute('aria-expanded', 'true');
    blockedModal.classList.remove('hidden');
    btnCloseBlocked.focus();
    document.addEventListener('keydown', handleModalKeyDown);
  }

  function closeBlockedModal() {
    blockedModal.classList.add('hidden');
    btnBlocked.setAttribute('aria-expanded', 'false');
    document.removeEventListener('keydown', handleModalKeyDown);
    if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
      lastFocusedElement.focus();
    }
  }

  function handleModalKeyDown(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeBlockedModal();
      return;
    }
    if (e.key === 'Tab') {
      const focusable = [btnCloseBlocked, btnUseHypothesis];
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  btnBlocked.addEventListener('click', async () => {
    openBlockedModal();
    try {
      const resp = await fetch('/api/blocked');
      if (resp.ok) {
        const data = await resp.json();
        blockedFact.textContent = data.fact;
        blockedOpportunity.textContent = data.opportunity;
        blockedHypothesis.textContent = data.hypothesis;
      }
    } catch (e) {
      blockedFact.textContent = 'Error al consultar historial empírico.';
    }
  });

  btnCloseBlocked.addEventListener('click', closeBlockedModal);

  btnUseHypothesis.addEventListener('click', () => {
    ideaInput.value = blockedHypothesis.textContent;
    updateCharCount();
    closeBlockedModal();
    ideaInput.focus();
  });

  // --- 9. NEW IDEA RESET ---
  btnNewIdea.addEventListener('click', () => {
    ideaInput.value = '';
    updateCharCount();
    selectedConceptId = null;
    activeRunId = null;
    transitionTo(STATES.IDLE);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // --- Online / Offline Window Listeners ---
  window.addEventListener('online', () => {
    console.info('[Network] Browser online event detected.');
    if (currentState === STATES.NETWORK_DEGRADED && activeRunId) {
      consecutiveNetworkFailures = 0;
      pollTick(activeRunId);
    }
  });

  window.addEventListener('offline', () => {
    console.warn('[Network] Browser offline event detected.');
    if (currentState === STATES.POLLING_ACTIVE) {
      transitionTo(STATES.NETWORK_DEGRADED);
    }
  });

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Initialize session hydration on startup
  hydrateSession();
});
