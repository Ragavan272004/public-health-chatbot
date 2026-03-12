// ── DOM refs ───────────────────────────────────────────
const chat       = document.getElementById('chat');
const speakerBtn = document.getElementById('speaker2');
const micBtn     = document.getElementById('mic2');
const msgInput   = document.getElementById('msg');
const sendBtn    = document.getElementById('send');
const clearBtn   = document.getElementById('clear');
const helpBtn    = document.getElementById('help');
const newsBox    = document.getElementById('news');
const langSelect = document.getElementById('lang-select');

// ── State ──────────────────────────────────────────────
let typingEl      = null;
let isWaiting     = false;
let speakerModeOn = false;
let currentLang   = 'en';
let uiStrings     = {};

// ── Language maps ──────────────────────────────────────
const LANG_SPEECH = {
  en: 'en-IN', hi: 'hi-IN', ta: 'ta-IN', te: 'te-IN',
  kn: 'kn-IN', ml: 'ml-IN', bn: 'bn-IN', mr: 'mr-IN',
  gu: 'gu-IN', pa: 'pa-IN'
};

const LANG_NAMES = {
  en: 'English',  hi: 'हिन्दी', ta: 'தமிழ்', te: 'తెలుగు',
  kn: 'ಕನ್ನಡ',   ml: 'മലയാളം', bn: 'বাংলা', mr: 'मराठी',
  gu: 'ગુજరાతી', pa: 'ਪੰਜਾਬੀ'
};

const LANG_LOCALE = {
  en: 'en-IN', hi: 'hi-IN', ta: 'ta-IN', te: 'te-IN',
  kn: 'kn-IN', ml: 'ml-IN', bn: 'bn-IN', mr: 'mr-IN',
  gu: 'gu-IN', pa: 'pa-IN'
};

function getSpeechLang() { return LANG_SPEECH[currentLang] || 'en-IN'; }

// ── Voice loader ──────────────────────────────────────
function getVoicesReady() {
  return new Promise(resolve => {
    const voices = window.speechSynthesis?.getVoices() || [];
    if (voices.length > 0) { resolve(voices); return; }
    const handler = () => {
      window.speechSynthesis.onvoiceschanged = null;
      resolve(window.speechSynthesis.getVoices());
    };
    window.speechSynthesis.onvoiceschanged = handler;
    setTimeout(() => {
      window.speechSynthesis.onvoiceschanged = null;
      resolve(window.speechSynthesis?.getVoices() || []);
    }, 3000);
  });
}

async function getBestVoice(bcp47) {
  const voices     = await getVoicesReady();
  const langCode   = bcp47.toLowerCase();
  const langPrefix = langCode.split('-')[0];
  let voice = voices.find(v => v.lang.toLowerCase() === langCode);
  if (!voice) voice = voices.find(v => v.lang.toLowerCase().startsWith(langPrefix));
  if (!voice) voice = voices.find(v =>
    v.name.toLowerCase().includes('google') && v.lang.toLowerCase().startsWith(langPrefix)
  );
  return voice || null;
}

// ── Typing indicator ───────────────────────────────────
function showTyping() {
  if (typingEl) return;
  typingEl = document.createElement('div');
  typingEl.className = 'msg bot typing-bubble';
  typingEl.innerHTML = `<div class="typing"><span></span><span></span><span></span></div>`;
  chat.appendChild(typingEl);
  scrollToBottom();
}

function hideTyping()     { typingEl?.remove(); typingEl = null; }
function scrollToBottom() { chat.scrollTop = chat.scrollHeight; }

// ── Text helpers ───────────────────────────────────────
function cleanText(s) {
  return String(s ?? '')
    .replace(/\*{1,2}/g, '')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^\s*-\s+/gm, '• ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function escapeHtml(s) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(s ?? '').replace(/[&<>"']/g, c => map[c]);
}

// ── Add message ────────────────────────────────────────
// Speaker is handled HERE — every bot message auto-speaks if mode is ON
function addMessage(text, who = 'bot', isFallback = false) {
  const el = document.createElement('div');
  el.className = `msg ${who}${isFallback ? ' fallback' : ''}`;
  el.textContent = String(text ?? '');

  const meta = document.createElement('div');
  meta.className = 'meta';
  const locale = LANG_LOCALE[currentLang] || 'en-IN';
  let metaText = `${who === 'user' ? 'You' : 'HealthBot'} • ` +
    new Date().toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
  if (isFallback) metaText += ' • offline info';
  meta.textContent = metaText;

  el.appendChild(meta);
  chat.appendChild(el);
  scrollToBottom();

  // ── Auto-speak every bot reply while speaker mode is ON ──
  if (who === 'bot' && speakerModeOn) {
    speakNow(String(text ?? ''));
  }
}

// ── Backend chat ───────────────────────────────────────
async function sendToBackend(userText) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 42000);
  try {
    const res = await fetch('/chat', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message: userText, lang: currentLang }),
      signal:  controller.signal
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

// ── TTS audio tracker ──────────────────────────────────
let currentTtsAudio = null;

// stopSpeaking() stops audio but does NOT change speakerModeOn
// Only toggleSpeakerMode() changes the ON/OFF state
function stopSpeaking() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  if (currentTtsAudio) {
    currentTtsAudio.pause();
    currentTtsAudio.currentTime = 0;
    URL.revokeObjectURL(currentTtsAudio.src);
    currentTtsAudio = null;
  }
}

async function speakNow(text) {
  const t = String(text ?? '').trim();
  if (!t) return;

  // Stop whatever is currently playing, then start new
  stopSpeaking();

  // Try browser TTS first (fast)
  if ('speechSynthesis' in window) {
    try {
      const voice = await getBestVoice(getSpeechLang());
      if (voice) {
        const utter  = new SpeechSynthesisUtterance(t);
        utter.lang   = getSpeechLang();
        utter.rate   = 0.95;
        utter.pitch  = 1;
        utter.voice  = voice;
        window.speechSynthesis.speak(utter);
        return;
      }
    } catch (e) { console.warn('Browser TTS failed:', e); }
  }

  // Fallback: Python gTTS
  try {
    const res = await fetch('/speak', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ text: t, lang: currentLang })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const ct = res.headers.get('Content-Type') || '';
    if (!ct.includes('audio')) throw new Error(`Unexpected content-type: ${ct}`);

    const audioBlob = await res.blob();
    const audioUrl  = URL.createObjectURL(audioBlob);
    const audio     = new Audio(audioUrl);
    currentTtsAudio = audio;
    audio.play().catch(e => console.warn('Audio play failed:', e));
    audio.onended = () => { URL.revokeObjectURL(audioUrl); currentTtsAudio = null; };
  } catch (e) {
    console.error('Python TTS failed:', e);
  }
}

// ── Speaker toggle — ONLY place that flips speakerModeOn ──
function toggleSpeakerMode() {
  speakerModeOn = !speakerModeOn;
  speakerBtn.classList.toggle('active', speakerModeOn);

  if (!speakerModeOn) {
    // User turned it OFF — stop all audio immediately
    stopSpeaking();
  }
  // When turned ON, next bot reply will auto-speak via addMessage()
}

// ── Video detection ────────────────────────────────────
const VIDEO_RE = /\b(video|videos|youtube|watch)\b/i;
function isVideoRequest(text) { return VIDEO_RE.test(text); }
function extractVideoTopic(text) {
  return text
    .replace(/\b(suggest|show|open|watch|youtube|video|videos|me|please|of|about|on|healthcare|health)\b/gi, '')
    .replace(/\s{2,}/g, ' ').trim() || 'public health awareness';
}
function openWHOSearch(query) {
  window.open(
    `https://www.youtube.com/results?search_query=${encodeURIComponent(query + ' World Health Organization official')}`,
    '_blank'
  );
}

// ── Send message ───────────────────────────────────────
async function sendMessage(text) {
  const trimmed = String(text ?? '').trim();
  if (!trimmed || isWaiting) return;

  addMessage(trimmed, 'user');
  msgInput.value = '';
  autoResizeTextarea();

  if (isVideoRequest(trimmed)) {
    const topic = extractVideoTopic(trimmed);
    openWHOSearch(topic);
    addMessage(`Opening WHO official videos for: ${topic}`, 'bot');
    return;
  }

  isWaiting = true;
  sendBtn.disabled = true;
  showTyping();

  try {
    const data    = await sendToBackend(trimmed);
    const cleaned = cleanText(data.reply || '');
    hideTyping();
    addMessage(cleaned, 'bot', data.fallback === true);
    // NOTE: no speakNow() here — addMessage() handles it automatically
  } catch (err) {
    hideTyping();
    addMessage(
      err.name === 'AbortError'
        ? 'Request timed out. Please try again.'
        : 'Server error. Please try again.',
      'bot'
    );
  } finally {
    isWaiting = false;
    sendBtn.disabled = false;
    msgInput.focus();
  }
}

// ── Voice input ────────────────────────────────────────
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const recognition       = SpeechRecognition ? new SpeechRecognition() : null;

if (recognition) {
  recognition.interimResults  = false;
  recognition.maxAlternatives = 1;
  recognition.onstart  = () => micBtn.classList.add('active');
  recognition.onend    = () => micBtn.classList.remove('active');
  recognition.onresult = e => {
    const transcript = (e.results[0][0].transcript || '').trim();
    if (transcript) sendMessage(transcript);
  };
  recognition.onerror = () => addMessage('Could not capture voice. Please try again.', 'bot');
}

function startVoiceInput() {
  if (isWaiting) return;
  if (!recognition) {
    addMessage('Voice input is not supported in this browser. Try Chrome.', 'bot');
    return;
  }
  recognition.lang = getSpeechLang();
  try { recognition.start(); } catch (_) {}
}

// ── News rendering ─────────────────────────────────────
function renderNews(items) {
  if (!items || !items.length) {
    newsBox.innerHTML = `<div class="news-empty">${uiStrings.no_news || 'Could not load WHO news.'}</div>`;
    return;
  }
  newsBox.innerHTML = '';
  const frag = document.createDocumentFragment();
  items.forEach(item => {
    const a = document.createElement('article');
    a.className = 'news-item';
    a.innerHTML = `
      <a href="${escapeHtml(item.link)}" target="_blank" rel="noopener noreferrer" class="news-link">
        <div class="news-content">
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.desc)}</p>
        </div>
      </a>`;
    frag.appendChild(a);
  });
  newsBox.appendChild(frag);
}

async function loadNews(lang = 'en') {
  newsBox.innerHTML = `<div class="news-empty">${uiStrings.loading_news || 'Loading WHO news…'}</div>`;
  try {
    const res = await fetch(`/news?lang=${lang}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    renderNews(await res.json());
  } catch {
    newsBox.innerHTML = `<div class="news-empty">${uiStrings.no_news || 'Could not load WHO news.'}</div>`;
  }
}

// ── Apply language ─────────────────────────────────────
async function applyLanguage(lang) {
  currentLang = lang;
  document.querySelectorAll('.chip').forEach(c => (c.style.opacity = '0.5'));

  // Update select accent class
  if (langSelect) langSelect.classList.toggle('has-value', lang !== 'en');

  try {
    const res = await fetch('/translate-ui', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ lang })
    });
    uiStrings = await res.json();

    document.getElementById('tagline').textContent        = uiStrings.tagline        || '';
    document.getElementById('chat-heading').textContent   = uiStrings.chat_heading   || 'Chat';
    document.getElementById('chat-subtext').textContent   = uiStrings.chat_subtext   || '';
    document.getElementById('topics-heading').textContent = uiStrings.topics_heading || 'Quick Topics';
    document.getElementById('topics-subtext').textContent = uiStrings.topics_subtext || '';
    document.getElementById('news-heading').textContent   = uiStrings.news_heading   || 'Health News';
    document.getElementById('news-subtext').textContent   = uiStrings.news_subtext   || '';
    document.getElementById('safety-heading').textContent = uiStrings.safety_heading || 'Safety';
    document.getElementById('safety-subtext').textContent = uiStrings.safety_subtext || '';
    document.getElementById('safety-text').textContent    = uiStrings.safety_text    || '';
    document.getElementById('clear').textContent          = uiStrings.btn_clear      || 'Clear';
    document.getElementById('help').textContent           = uiStrings.btn_help       || 'Help';
    msgInput.setAttribute('placeholder', uiStrings.chat_placeholder || 'Type your health question…');

    document.querySelectorAll('.chip').forEach(chip => {
      const key  = chip.dataset.key;
      const qkey = chip.dataset.qkey;
      if (key  && uiStrings[key])  chip.textContent = uiStrings[key];
      if (qkey && uiStrings[qkey]) chip.dataset.q   = uiStrings[qkey];
      chip.style.opacity = '1';
    });

    const welcomeText = document.getElementById('welcome-text');
    if (welcomeText) welcomeText.textContent = uiStrings.welcome_msg || '';
    const welcomeTip = document.getElementById('welcome-tip');
    if (welcomeTip) welcomeTip.textContent = uiStrings.welcome_tip || '';

    if (recognition) recognition.lang = getSpeechLang();

    // Stop current audio on lang switch but keep speakerModeOn as-is
    // so next reply is still spoken in the new language
    stopSpeaking();

    await loadNews(lang);
    addMessage(`✓ ${LANG_NAMES[lang] || lang}`, 'bot');

  } catch {
    document.querySelectorAll('.chip').forEach(c => (c.style.opacity = '1'));
    addMessage('Language switch failed. Please try again.', 'bot');
  }
}

// ── Textarea auto-resize ───────────────────────────────
function autoResizeTextarea() {
  msgInput.style.height = 'auto';
  msgInput.style.height = Math.min(msgInput.scrollHeight, 110) + 'px';
}
msgInput.addEventListener('input', autoResizeTextarea);

// ── Events ─────────────────────────────────────────────
sendBtn.addEventListener('click',    () => sendMessage(msgInput.value));
micBtn.addEventListener('click',     startVoiceInput);
speakerBtn.addEventListener('click', toggleSpeakerMode);

msgInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(msgInput.value); }
});

document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => sendMessage(chip.dataset.q));
  chip.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sendMessage(chip.dataset.q); }
  });
});

clearBtn.addEventListener('click', () => {
  // Stop audio but keep speaker mode ON if it was on
  stopSpeaking();
  speakerBtn.classList.remove('active');
  speakerModeOn = false;

  Array.from(chat.children).forEach(child => {
    if (child.id !== 'welcome-msg') child.remove();
  });

  const welcomeText = document.getElementById('welcome-text');
  if (welcomeText) welcomeText.textContent =
    uiStrings.welcome_msg || 'Hi. Ask me about symptoms, prevention, vaccines, and when to seek care.';
  const welcomeTip = document.getElementById('welcome-tip');
  if (welcomeTip) welcomeTip.textContent =
    uiStrings.welcome_tip || 'Tip: use Quick Topics → or select your language above';

  fetch('/clear-history', { method: 'POST' }).catch(() => {});
});

helpBtn.addEventListener('click', () => {
  addMessage(
    `• ${uiStrings.chip_q_dengue    || 'What are dengue symptoms?'}\n` +
    `• ${uiStrings.chip_q_tb        || 'How does TB spread?'}\n` +
    `• ${uiStrings.chip_q_emergency || 'Emergency warning signs'}\n` +
    `• ${uiStrings.chip_q_vaccine   || 'Bust vaccine myths'}\n` +
    `• ${uiStrings.chip_q_videos    || 'Show videos on dengue prevention'}`,
    'bot'
  );
});

if (langSelect) {
  langSelect.addEventListener('change', () => applyLanguage(langSelect.value));
}

// ── Init ───────────────────────────────────────────────
loadNews('en');
