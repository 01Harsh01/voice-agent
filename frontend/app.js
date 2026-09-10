/**
 * VoiceFlow Client Application.
 * Manages WebSocket communication, Web Audio API streaming playback with timeline scheduling,
 * user gesture audio unlocking, speech recognition, barge-in interruption, and live debug trace rendering.
 */

// State
let ws = null;
let conversationId = 'convo_' + Date.now();
let isRecording = false;
let recognition = null;
let audioContext = null;
let activeSourceNodes = [];
let nextPlayTime = 0;
let isPlayingAudio = false;
let currentRequestId = null;
let turnCount = 0;
let lastAssistantText = "";
let isDemoMode = false;
let demoUtterance = null;

// DOM Elements
const statusIndicator = document.querySelector('.status-indicator');
const statusLabel = document.getElementById('status-label');
const voiceOrb = document.getElementById('voice-orb');
const micBtn = document.getElementById('mic-btn');
const interruptBtn = document.getElementById('interrupt-btn');
const clearBtn = document.getElementById('clear-btn');
const liveTranscript = document.getElementById('live-transcript');
const messagesContainer = document.getElementById('messages-container');
const textForm = document.getElementById('text-input-form');
const textInput = document.getElementById('manual-text-input');
const turnCountElem = document.getElementById('turn-count');
const audioTestBtn = document.getElementById('audio-test-btn');
const audioStatusDot = document.getElementById('audio-status-dot');
const audioStatusText = document.getElementById('audio-status-text');

// Settings & Demo Mode Elements
const demoModeToggle = document.getElementById('demo-mode-toggle');
const demoModeLabel = document.getElementById('demo-mode-label');
const modeDot = document.getElementById('mode-dot');
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const closeModalBtn = document.getElementById('close-modal-btn');
const backendUrlInput = document.getElementById('backend-url-input');
const saveGatewayBtn = document.getElementById('save-gateway-btn');
const resetGatewayBtn = document.getElementById('reset-gateway-btn');
const modalDemoBtn = document.getElementById('modal-demo-btn');

// Trace Drawer Elements
const traceDrawer = document.getElementById('trace-drawer');
const toggleTraceBtn = document.getElementById('toggle-trace-btn');
const closeTraceBtn = document.getElementById('close-trace-btn');
const traceEvents = document.getElementById('trace-events');
const traceReqId = document.getElementById('trace-req-id');
const traceLlmLat = document.getElementById('trace-llm-lat');
const traceTtfb = document.getElementById('trace-ttfb');

// Visualizer Canvas
const canvas = document.getElementById('visualizer-canvas');
const ctx = canvas.getContext('2d');

// --- Audio Context Setup & Gesture Unlock ---
function getAudioContext() {
  if (!audioContext) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    audioContext = new AudioCtx();
    console.log('[Audio] AudioContext created. Sample rate:', audioContext.sampleRate, 'State:', audioContext.state);
  }
  return audioContext;
}

function unlockAudio() {
  const ac = getAudioContext();
  if (ac.state === 'suspended') {
    ac.resume().then(() => {
      console.log('[Audio] AudioContext unlocked successfully via user gesture.');
      updateAudioUI(true);
    }).catch(err => {
      console.warn('[Audio] Failed to unlock AudioContext:', err);
    });
  } else {
    updateAudioUI(true);
  }
}

function updateAudioUI(isUnlocked) {
  if (!audioStatusText || !audioStatusDot) return;
  if (isUnlocked) {
    audioStatusDot.className = 'indicator-dot online';
    audioStatusText.textContent = '🔊 Sound: Active';
  } else {
    audioStatusDot.className = 'indicator-dot rime';
    audioStatusText.textContent = '🔇 Click to Enable Sound';
  }
}

// Unlock audio on ANY user gesture anywhere on page
['click', 'keydown', 'touchstart', 'pointerdown'].forEach(evtType => {
  document.addEventListener(evtType, () => unlockAudio(), { passive: true });
});

// Sound test button
if (audioTestBtn) {
  audioTestBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    unlockAudio();
    playChime();
  });
}

function playChime() {
  try {
    const ac = getAudioContext();
    if (ac.state === 'suspended') ac.resume();
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, ac.currentTime); // D5
    osc.frequency.exponentialRampToValueAtTime(880, ac.currentTime + 0.15); // A5
    gain.gain.setValueAtTime(0.15, ac.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.4);
    osc.connect(gain);
    gain.connect(ac.destination);
    osc.start();
    osc.stop(ac.currentTime + 0.4);
    liveTranscript.textContent = 'Audio test played. Speaker is ready.';
    updateAudioUI(true);
  } catch (err) {
    console.error('Failed to play chime:', err);
  }
}

// --- Visualizer Animation ---
let visualizerPhase = 0;
function drawVisualizer() {
  requestAnimationFrame(drawVisualizer);
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const isSpeaking = voiceOrb.classList.contains('speaking');
  const isListening = voiceOrb.classList.contains('listening');
  const isReasoning = voiceOrb.classList.contains('reasoning');

  let amplitude = 2;
  let color = 'rgba(255, 255, 255, 0.15)';

  if (isSpeaking) {
    amplitude = 18;
    color = '#00f2fe';
  } else if (isListening) {
    amplitude = 12;
    color = '#ff4757';
  } else if (isReasoning) {
    amplitude = 8;
    color = '#f5a623';
  }

  visualizerPhase += 0.08;
  ctx.beginPath();
  ctx.lineWidth = 2;
  ctx.strokeStyle = color;

  const sliceWidth = canvas.width / 40;
  for (let i = 0; i <= 40; i++) {
    const x = i * sliceWidth;
    const y = (canvas.height / 2) + Math.sin(visualizerPhase + i * 0.3) * amplitude * Math.sin(i / 40 * Math.PI);
    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  }
  ctx.stroke();
}
drawVisualizer();

// --- WebSocket Gateway Resolution & Connection ---
function getStoredGatewayUrl() {
  return localStorage.getItem('voiceflow_ws_url') || '';
}

function resolveGatewayUrl() {
  const custom = getStoredGatewayUrl().trim();
  if (custom) return custom;
  // If hosted on Vercel or Netlify, automatically connect to the live Render backend gateway
  if (window.location.host.includes('vercel.app') || window.location.host.includes('netlify.app')) {
    return `wss://voice-agent-backend-82ca.onrender.com/ws/voice?conversation_id=${conversationId}`;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/voice?conversation_id=${conversationId}`;
}

let wsReconnectTimeout = null;

function initWebSocket() {
  if (isDemoMode) return;

  if (ws) {
    try { ws.close(); } catch (e) {}
    ws = null;
  }
  clearTimeout(wsReconnectTimeout);

  const wsUrl = resolveGatewayUrl();
  statusLabel.innerHTML = 'Connecting to Voice Gateway...';
  statusIndicator.className = 'status-indicator';

  try {
    ws = new WebSocket(wsUrl);
  } catch (err) {
    handleConnectionFailure();
    return;
  }

  ws.onopen = () => {
    statusLabel.innerHTML = 'Connected & Ready (Live Gateway)';
    statusIndicator.className = 'status-indicator ready';
    setOrbState('idle');
  };

  ws.onclose = () => {
    if (!isDemoMode) {
      handleConnectionFailure();
    }
  };

  ws.onerror = (err) => {
    console.warn('WebSocket connection error:', err);
    if (!isDemoMode) {
      handleConnectionFailure();
    }
  };

  ws.onmessage = async (event) => {
    try {
      const data = JSON.parse(event.data);
      handleServerEvent(data);
    } catch (e) {
      console.error('Failed to parse WS message:', e);
    }
  };
}

function handleConnectionFailure() {
  statusIndicator.className = 'status-indicator';
  setOrbState('idle');
  statusLabel.innerHTML = `Gateway Offline &bull; <button id="quick-demo-btn" class="inline-btn">Demo Mode</button> <button id="quick-settings-btn" class="inline-btn">Settings</button>`;
  
  const qDemo = document.getElementById('quick-demo-btn');
  if (qDemo) qDemo.onclick = () => enableDemoMode();
  const qSet = document.getElementById('quick-settings-btn');
  if (qSet) qSet.onclick = () => openSettingsModal();
}

function enableDemoMode() {
  isDemoMode = true;
  if (ws) {
    try { ws.close(); } catch (e) {}
    ws = null;
  }
  if (modeDot) modeDot.className = 'indicator-dot demo';
  if (demoModeLabel) demoModeLabel.textContent = 'Demo Mode (On)';
  statusLabel.innerHTML = 'Interactive Demo Mode (In-Browser)';
  statusIndicator.className = 'status-indicator ready';
  setOrbState('idle');
  closeSettingsModal();
}

function disableDemoMode() {
  isDemoMode = false;
  if (modeDot) modeDot.className = 'indicator-dot rime';
  if (demoModeLabel) demoModeLabel.textContent = 'Demo Mode';
  initWebSocket();
}

// --- Server Event Dispatcher ---
let activeAssistantBubble = null;
let receivedChunksForCurrentRequest = 0;

function handleServerEvent(event) {
  switch (event.type) {
    case 'connection_ready':
      console.log('Voice Gateway ready. Available tools:', event.tools);
      break;

    case 'playback_stop':
      stopAudioPlaybackImmediate('Server requested playback stop');
      break;

    case 'trace':
      renderTraceEvent(event);
      break;

    case 'assistant_text_chunk':
      setOrbState('speaking');
      if (activeAssistantBubble) {
        const textSpan = activeAssistantBubble.querySelector('.bubble-text');
        if (textSpan) {
          textSpan.textContent = event.chunk;
        }
      }
      break;

    case 'assistant_text_final':
      setOrbState('speaking');
      currentRequestId = event.requestId;
      lastAssistantText = event.text;
      receivedChunksForCurrentRequest = 0;
      if (!activeAssistantBubble) {
        activeAssistantBubble = appendAssistantMessage(event.text);
      } else {
        const textSpan = activeAssistantBubble.querySelector('.bubble-text');
        if (textSpan) textSpan.textContent = event.text;
      }
      break;

    case 'audio_chunk':
      currentRequestId = event.requestId;
      receivedChunksForCurrentRequest++;
      queueAudioChunk(event.audio);
      break;

    case 'audio_done':
      console.log(`[Audio] Audio stream finished for ${event.requestId}. Chunks received: ${receivedChunksForCurrentRequest}`);
      // Fallback: If 0 audio chunks were received from TTS, speak via browser SpeechSynthesis
      if (receivedChunksForCurrentRequest === 0 && lastAssistantText) {
        console.warn('[Audio] No TTS chunks received; executing browser speech synthesis fallback.');
        speakBrowserFallback(lastAssistantText);
      }
      break;

    case 'history_cleared':
      messagesContainer.innerHTML = '';
      traceEvents.innerHTML = '<div class="trace-placeholder">History reset. New turn trace will appear here.</div>';
      turnCount = 0;
      updateTurnCount();
      liveTranscript.textContent = 'Conversation history cleared. Ready for your query.';
      break;

    case 'error':
      console.error('Server error:', event.message);
      setOrbState('idle');
      liveTranscript.textContent = `Error: ${event.message}`;
      break;
  }
}

// --- Audio Decoding & Timeline Playback ---
function pcmToAudioBuffer(bytes, sampleRate = 24000) {
  const ac = getAudioContext();
  const numSamples = Math.floor(bytes.length / 2);
  if (numSamples === 0) return null;

  const audioBuffer = ac.createBuffer(1, numSamples, sampleRate);
  const channelData = audioBuffer.getChannelData(0);
  const dataView = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

  for (let i = 0; i < numSamples; i++) {
    const int16 = dataView.getInt16(i * 2, true);
    channelData[i] = int16 < 0 ? int16 / 32768.0 : int16 / 32767.0;
  }
  return audioBuffer;
}

async function queueAudioChunk(base64Audio) {
  try {
    const binary = atob(base64Audio);
    const len = binary.length;
    if (len === 0) return;

    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binary.charCodeAt(i);
    }

    const ac = getAudioContext();
    if (ac.state === 'suspended') {
      await ac.resume();
    }

    let audioBuffer = null;
    const isRiff = len >= 4 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46;
    const isId3 = len >= 3 && bytes[0] === 0x49 && bytes[1] === 0x44 && bytes[2] === 0x33;

    if (isRiff || isId3) {
      try {
        audioBuffer = await ac.decodeAudioData(bytes.buffer.slice(0));
      } catch (e) {
        audioBuffer = pcmToAudioBuffer(bytes, 24000);
      }
    } else {
      audioBuffer = pcmToAudioBuffer(bytes, 24000);
    }

    if (audioBuffer) {
      scheduleAudioBuffer(audioBuffer);
    }
  } catch (err) {
    console.error('[Audio] Error processing audio chunk:', err);
  }
}

function scheduleAudioBuffer(buffer) {
  const ac = getAudioContext();
  const source = ac.createBufferSource();
  source.buffer = buffer;
  source.connect(ac.destination);

  const now = ac.currentTime;
  // Seamless timeline scheduling: append right after previous buffer, or start now + 20ms lead
  const startTime = Math.max(now + 0.02, nextPlayTime);
  source.start(startTime);
  nextPlayTime = startTime + buffer.duration;

  isPlayingAudio = true;
  setOrbState('speaking');
  activeSourceNodes.push(source);

  source.onended = () => {
    activeSourceNodes = activeSourceNodes.filter(s => s !== source);
    if (activeSourceNodes.length === 0 && ac.currentTime >= nextPlayTime - 0.05) {
      isPlayingAudio = false;
      setOrbState('idle');
    }
  };
}

function stopAudioPlaybackImmediate(reason = 'Interrupted') {
  // 1. Stop all active and scheduled buffer source nodes
  activeSourceNodes.forEach(source => {
    try {
      source.stop();
      source.disconnect();
    } catch (e) {}
  });
  activeSourceNodes = [];
  nextPlayTime = 0;
  isPlayingAudio = false;

  // Cancel any active browser speech synthesis
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }

  setOrbState('idle');
  console.log(`[Audio] Playback stopped immediately: ${reason}`);
}

function speakBrowserFallback(text) {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.05;
  utterance.pitch = 1.0;
  
  // Pick preferred natural voice if available
  const voices = window.speechSynthesis.getVoices();
  const preferred = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Samantha')));
  if (preferred) utterance.voice = preferred;

  setOrbState('speaking');
  isPlayingAudio = true;

  utterance.onend = () => {
    isPlayingAudio = false;
    setOrbState('idle');
  };
  utterance.onerror = () => {
    isPlayingAudio = false;
    setOrbState('idle');
  };

  window.speechSynthesis.speak(utterance);
}

// --- Barge-in & Interruption ---
function triggerBargeIn() {
  stopAudioPlaybackImmediate('Barge-in');
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'barge_in' }));
  }
}

// --- Orb State Management ---
function setOrbState(state) {
  voiceOrb.className = `voice-orb ${state}`;
  if (state === 'listening') {
    statusIndicator.className = 'status-indicator listening';
    statusLabel.textContent = 'Listening to speech...';
  } else if (state === 'reasoning') {
    statusIndicator.className = 'status-indicator reasoning';
    statusLabel.textContent = 'Qwen reasoning & tools...';
  } else if (state === 'speaking') {
    statusIndicator.className = 'status-indicator speaking';
    statusLabel.textContent = 'Assistant speaking...';
  } else {
    statusIndicator.className = 'status-indicator ready';
    statusLabel.textContent = 'Connected & Ready';
  }
}

// --- Speech Recognition (STT) with Smart Silence Detection & Fallback ---
let speechSilenceTimer = null;
let accumulatedTranscript = '';
let micStream = null;

function commitSpokenQuery() {
  clearTimeout(speechSilenceTimer);
  if (accumulatedTranscript && accumulatedTranscript.trim()) {
    const queryToSend = accumulatedTranscript.trim();
    accumulatedTranscript = '';
    liveTranscript.textContent = `Sent: "${queryToSend}"`;
    sendUserQuery(queryToSend);
  }
}

function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    console.warn('Web Speech API not supported in this browser. Use manual text input.');
    liveTranscript.textContent = 'Speech recognition requires Chrome, Edge, or Safari. You can still type below!';
    return;
  }

  try {
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      isRecording = true;
      micBtn.classList.add('active');
      setOrbState('listening');
      liveTranscript.textContent = 'Listening... Speak now!';
    };

    recognition.onresult = (event) => {
      let interim = '';
      let final = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcriptPart = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += transcriptPart;
        } else {
          interim += transcriptPart;
        }
      }

      const activeText = final || interim;
      if (activeText && activeText.trim()) {
        accumulatedTranscript = activeText.trim();
        liveTranscript.textContent = `You: "${accumulatedTranscript}"`;

        if (isPlayingAudio) {
          triggerBargeIn();
        }

        // Reset silence timer on every spoken syllable
        clearTimeout(speechSilenceTimer);

        if (final && final.trim()) {
          // Explicit final sentence from browser engine
          commitSpokenQuery();
        } else {
          // Wait 1.3s of silence after speaking, then auto-submit query
          speechSilenceTimer = setTimeout(() => {
            commitSpokenQuery();
          }, 1300);
        }
      }
    };

    recognition.onerror = (event) => {
      console.warn('Speech recognition error:', event.error);
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        liveTranscript.innerHTML = '⚠️ <strong>Microphone blocked.</strong> Click the lock icon in your browser address bar to allow microphone access.';
        stopRecording();
      } else if (event.error === 'network') {
        liveTranscript.innerHTML = '⚠️ Speech network error. Ensure your browser allows speech services or type below.';
      } else if (event.error !== 'no-speech') {
        stopRecording();
      }
    };

    recognition.onend = () => {
      // If speech ended while we still have transcript, commit it
      if (accumulatedTranscript && accumulatedTranscript.trim()) {
        commitSpokenQuery();
      }
      if (isRecording) {
        try { recognition.start(); } catch (e) {}
      } else {
        micBtn.classList.remove('active');
        setOrbState('idle');
      }
    };
  } catch (err) {
    console.error('Failed to initialize SpeechRecognition:', err);
  }
}

async function toggleRecording() {
  unlockAudio();

  if (isRecording) {
    stopRecording();
    return;
  }

  // Request browser microphone permission explicitly first if supported
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    try {
      if (!micStream) {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
    } catch (err) {
      console.warn('Microphone permission request rejected:', err);
      liveTranscript.innerHTML = '⚠️ <strong>Microphone permission denied.</strong> Please click the lock or camera icon in your address bar to allow microphone.';
      return;
    }
  }

  if (!recognition) {
    initSpeechRecognition();
  }

  startRecording();
}

function startRecording() {
  accumulatedTranscript = '';
  clearTimeout(speechSilenceTimer);
  if (recognition) {
    try {
      recognition.start();
    } catch (e) {
      console.warn('Recognition start issue:', e);
      isRecording = true;
      micBtn.classList.add('active');
      setOrbState('listening');
    }
  }
}

function stopRecording() {
  isRecording = false;
  micBtn.classList.remove('active');
  clearTimeout(speechSilenceTimer);
  if (recognition) {
    try {
      recognition.stop();
    } catch (e) {}
  }
  setOrbState('idle');
}

// --- Modal and Settings Handlers ---
function openSettingsModal() {
  if (settingsModal) {
    settingsModal.classList.remove('hidden');
    if (backendUrlInput) {
      backendUrlInput.value = getStoredGatewayUrl();
    }
  }
}

function closeSettingsModal() {
  if (settingsModal) {
    settingsModal.classList.add('hidden');
  }
}

if (settingsBtn) settingsBtn.addEventListener('click', openSettingsModal);
if (closeModalBtn) closeModalBtn.addEventListener('click', closeSettingsModal);
if (modalDemoBtn) modalDemoBtn.addEventListener('click', () => {
  enableDemoMode();
});

if (saveGatewayBtn) {
  saveGatewayBtn.addEventListener('click', () => {
    const val = backendUrlInput ? backendUrlInput.value.trim() : '';
    if (val) {
      localStorage.setItem('voiceflow_ws_url', val);
    } else {
      localStorage.removeItem('voiceflow_ws_url');
    }
    closeSettingsModal();
    disableDemoMode();
  });
}

if (resetGatewayBtn) {
  resetGatewayBtn.addEventListener('click', () => {
    localStorage.removeItem('voiceflow_ws_url');
    if (backendUrlInput) backendUrlInput.value = '';
    closeSettingsModal();
    disableDemoMode();
  });
}

if (demoModeToggle) {
  demoModeToggle.addEventListener('click', () => {
    if (isDemoMode) {
      disableDemoMode();
    } else {
      enableDemoMode();
    }
  });
}

// Close modal when clicking outside
if (settingsModal) {
  settingsModal.addEventListener('click', (e) => {
    if (e.target === settingsModal) {
      closeSettingsModal();
    }
  });
}

// --- Send User Query ---
function sendUserQuery(text) {
  if (!text || !text.trim()) return;

  unlockAudio();

  if (isPlayingAudio) {
    triggerBargeIn();
  } else {
    stopAudioPlaybackImmediate('New user utterance');
  }

  appendUserMessage(text);
  activeAssistantBubble = appendAssistantMessage('Thinking...');
  setOrbState('reasoning');

  if (isDemoMode) {
    runDemoSimulation(text.trim());
    return;
  }

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'user_speech',
      text: text
    }));
  } else {
    console.warn('WebSocket not connected. Switching to Demo Mode.');
    runDemoSimulation(text.trim());
  }
}

// --- Interactive Demo Simulation Runner ---
let demoSimulationTimer = null;

function runDemoSimulation(userText) {
  const reqId = 'demo_' + Math.random().toString(36).substring(2, 9);
  currentRequestId = reqId;

  // 1. Trace: TURN_START
  renderTraceEvent({
    type: 'trace',
    requestId: reqId,
    stage: 'TURN_START',
    timestamp: Date.now() / 1000,
    data: { user_query: userText, mode: 'Interactive Simulation' }
  });

  const lower = userText.toLowerCase();
  const needsWeb = lower.includes('news') || lower.includes('today') || lower.includes('weather') || lower.includes('ai') || lower.includes('who') || lower.includes('what');

  clearTimeout(demoSimulationTimer);

  demoSimulationTimer = setTimeout(() => {
    if (currentRequestId !== reqId) return; // Barge-in cancelled

    if (needsWeb) {
      // Trace: TOOL_CALL_START
      const toolQuery = lower.includes('weather') ? 'current weather forecast' : (lower.includes('news') ? 'top breaking news headlines' : userText);
      renderTraceEvent({
        type: 'trace',
        requestId: reqId,
        stage: 'TOOL_CALL_START',
        timestamp: Date.now() / 1000,
        data: { tool: 'web_research', query: toolQuery }
      });

      demoSimulationTimer = setTimeout(() => {
        if (currentRequestId !== reqId) return;

        // Trace: TOOL_CALL_END
        renderTraceEvent({
          type: 'trace',
          requestId: reqId,
          stage: 'TOOL_CALL_END',
          timestamp: Date.now() / 1000,
          duration_ms: 412,
          data: { tool: 'web_research', status: 'success', live_results: 3 }
        });

        finishDemoResponse(reqId, userText);
      }, 700);
    } else {
      finishDemoResponse(reqId, userText);
    }
  }, 500);
}

function finishDemoResponse(reqId, userText) {
  if (currentRequestId !== reqId) return;

  // Formulate natural response
  const lower = userText.toLowerCase();
  let answer = "";
  if (lower.includes('weather')) {
    answer = "Conditions are currently clear with mild temperatures and a light breeze. Tomorrow is expected to remain pleasant throughout the day.";
  } else if (lower.includes('news') || lower.includes('today') || lower.includes('ai')) {
    answer = "Recent developments in artificial intelligence highlight significant breakthroughs in low-latency real-time voice agents, sub-200 millisecond time-to-first-byte audio, and autonomous tool calling.";
  } else if (lower.includes('hello') || lower.includes('hi')) {
    answer = "Hello! I am VoiceFlow, an autonomous real-time voice assistant powered by Qwen reasoning and streaming speech synthesis. How can I assist you today?";
  } else {
    answer = `I analyzed your request regarding "${userText}". All systems are operational with real-time web tools and audio streaming ready.`;
  }

  // Trace: LLM_RESPONSE
  renderTraceEvent({
    type: 'trace',
    requestId: reqId,
    stage: 'LLM_RESPONSE',
    timestamp: Date.now() / 1000,
    duration_ms: 685,
    data: { synthesized_length: answer.length }
  });

  // Trace: TTS_START & AUDIO_FIRST_BYTE
  renderTraceEvent({
    type: 'trace',
    requestId: reqId,
    stage: 'TTS_START',
    timestamp: Date.now() / 1000,
    data: { speaker: 'coda', mode: 'streaming' }
  });

  renderTraceEvent({
    type: 'trace',
    requestId: reqId,
    stage: 'AUDIO_FIRST_BYTE',
    timestamp: Date.now() / 1000,
    duration_ms: 198
  });

  // Update UI bubble
  if (activeAssistantBubble) {
    const textSpan = activeAssistantBubble.querySelector('.bubble-text');
    if (textSpan) textSpan.textContent = answer;
  }
  lastAssistantText = answer;

  // Speak with browser TTS
  speakBrowserFallback(answer);
}

// --- Chat Messages UI ---
function appendUserMessage(text) {
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble user';
  bubble.innerHTML = `
    <div class="bubble-text">${escapeHtml(text)}</div>
    <div class="bubble-meta">You</div>
  `;
  messagesContainer.appendChild(bubble);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
  turnCount++;
  updateTurnCount();
  return bubble;
}

function appendAssistantMessage(initialText) {
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble assistant';
  bubble.innerHTML = `
    <div class="bubble-meta">
      <span>Assistant</span>
      <span class="tool-tag" style="display: none;"></span>
    </div>
    <div class="bubble-text">${escapeHtml(initialText)}</div>
  `;
  messagesContainer.appendChild(bubble);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
  return bubble;
}

function updateTurnCount() {
  turnCountElem.textContent = `${turnCount} turn${turnCount === 1 ? '' : 's'}`;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// --- Debug Trace Drawer UI ---
function renderTraceEvent(evt) {
  const placeholder = traceEvents.querySelector('.trace-placeholder');
  if (placeholder) placeholder.remove();

  if (evt.requestId) {
    traceReqId.textContent = evt.requestId;
  }
  if (evt.stage === 'LLM_RESPONSE' && evt.duration_ms) {
    traceLlmLat.textContent = `${Math.round(evt.duration_ms)}ms`;
  }
  if (evt.stage === 'AUDIO_FIRST_BYTE' && evt.duration_ms) {
    traceTtfb.textContent = `${Math.round(evt.duration_ms)}ms`;
  }

  if (evt.stage === 'TOOL_CALL_START' && activeAssistantBubble) {
    const tag = activeAssistantBubble.querySelector('.tool-tag');
    if (tag) {
      tag.style.display = 'inline-block';
      tag.textContent = `Tool: ${evt.data.tool || 'web_research'}`;
    }
  }

  const card = document.createElement('div');
  card.className = `trace-card ${evt.stage}`;

  const timeStr = new Date(evt.timestamp * 1000).toLocaleTimeString();
  const durStr = evt.duration_ms ? ` (${Math.round(evt.duration_ms)}ms)` : '';

  let detailsStr = '';
  if (evt.data && Object.keys(evt.data).length > 0) {
    detailsStr = `<div class="trace-details">${escapeHtml(JSON.stringify(evt.data, null, 2))}</div>`;
  }

  card.innerHTML = `
    <div class="trace-top">
      <span class="trace-stage">${evt.stage}</span>
      <span class="trace-duration">${timeStr}${durStr}</span>
    </div>
    ${detailsStr}
  `;

  traceEvents.appendChild(card);
  traceEvents.scrollTop = traceEvents.scrollHeight;
}

// --- Event Listeners ---
micBtn.addEventListener('click', toggleRecording);
voiceOrb.addEventListener('click', toggleRecording);

interruptBtn.addEventListener('click', () => {
  currentRequestId = null;
  clearTimeout(demoSimulationTimer);
  triggerBargeIn();
  liveTranscript.textContent = 'Interrupted speech playback.';
});

clearBtn.addEventListener('click', () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'clear_history' }));
  }
  messagesContainer.innerHTML = '';
  turnCount = 0;
  updateTurnCount();
});

textForm.addEventListener('submit', (e) => {
  e.preventDefault();
  unlockAudio();
  const query = textInput.value.trim();
  if (query) {
    sendUserQuery(query);
    textInput.value = '';
  }
});

toggleTraceBtn.addEventListener('click', () => {
  traceDrawer.classList.toggle('open');
});

closeTraceBtn.addEventListener('click', () => {
  traceDrawer.classList.remove('open');
});

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
  // If loaded directly or on static host without backend, check connection
  initWebSocket();
  initSpeechRecognition();
  updateAudioUI(false);
});

