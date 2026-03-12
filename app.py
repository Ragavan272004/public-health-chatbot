import os
import re
import time
import json
import logging
import urllib.request
import threading
import feedparser
import requests
import io
from gtts import gTTS
from flask import Flask, render_template, request, jsonify, send_file, session
from deep_translator import GoogleTranslator

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-in-production")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────
GROQ_API_KEY  = ""
GROQ_MODEL    = "llama-3.3-70b-versatile"
GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"
WHO_FEED_URL  = "https://www.who.int/rss-feeds/news-english.xml"
MAX_MSG_LEN   = 800
MAX_HISTORY   = 6
NEWS_TTL_SECS = 6 * 3600

TRANSLATION_DIR = os.path.join(os.path.dirname(__file__), "translations")
os.makedirs(TRANSLATION_DIR, exist_ok=True)

SYSTEM_PROMPT = (
    "You are a public health awareness assistant for general education only. "
    "You may mention commonly known over-the-counter medicines like paracetamol "
    "only when they are officially recommended by WHO for a condition, and ALWAYS "
    "include the disclaimer to consult a doctor before taking any medicine. "
    "NEVER suggest specific doses, prescription drugs, or treatments. "
    "NEVER say a medicine will cure a disease. "
    "ALWAYS recommend seeing a certified doctor or hospital for any medical condition. "
    "Advise emergency care immediately for severe symptoms such as chest pain, "
    "difficulty breathing, seizures, or bleeding. "
    "Keep answers concise, plain, and easy to understand."
)

# ── Built-in fallback health knowledge ─────────────────
HEALTH_KB = {
    "dengue": (
        "Dengue is a mosquito-borne viral infection spread by the Aedes mosquito.\n\n"
        "• What it is: A viral fever caused by 4 dengue virus types — second infection can be more severe.\n"
        "• Symptoms: High fever (104°F), severe headache, pain behind eyes, joint/muscle pain, skin rash, mild bleeding from nose or gums.\n"
        "• Warning signs: Severe abdominal pain, persistent vomiting, rapid breathing, bleeding — seek emergency care immediately.\n"
        "• Prevention: Use mosquito repellent, wear full-sleeve clothing, eliminate standing water (flower pots, coolers, tyres), use mosquito nets.\n"
        "• Treatment: Rest, fluids, paracetamol for fever (consult a doctor first). Avoid ibuprofen or aspirin — they worsen bleeding.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "malaria": (
        "Malaria is a life-threatening disease caused by Plasmodium parasites, spread through infected female Anopheles mosquito bites.\n\n"
        "• What it is: A parasitic infection affecting red blood cells, causing repeated cycles of fever.\n"
        "• Symptoms: High fever with chills and sweating (cyclical pattern), headache, nausea, vomiting, muscle pain, fatigue.\n"
        "• Prevention: Sleep under insecticide-treated bed nets, use mosquito repellent, wear protective clothing at dusk/dawn.\n"
        "• Treatment: Requires prescription antimalarial drugs — consult a doctor immediately if suspected.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "tuberculosis": (
        "Tuberculosis (TB) is a bacterial infection caused by Mycobacterium tuberculosis, mainly affecting the lungs.\n\n"
        "• What it is: A contagious bacterial disease — one of the world's leading infectious disease killers.\n"
        "• How it spreads: Through the air when an infected person coughs, sneezes, or speaks. NOT spread by touch.\n"
        "• Symptoms: Persistent cough (3+ weeks), coughing blood, chest pain, unexplained weight loss, night sweats, prolonged fever, fatigue.\n"
        "• Prevention: BCG vaccination for newborns, avoid close contact with TB patients, ensure good ventilation.\n"
        "• Treatment: TB is curable with a strict 6-month antibiotic course. Never stop medicine early — causes drug resistance.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "flu": (
        "Influenza (Flu) is a contagious respiratory illness caused by influenza A or B viruses.\n\n"
        "• What it is: A seasonal viral infection affecting the nose, throat, and lungs — comes on suddenly unlike a cold.\n"
        "• Symptoms: Sudden high fever, chills, severe muscle aches, headache, fatigue, dry cough, sore throat, runny nose.\n"
        "• When to see a doctor: Difficulty breathing, chest pain, confusion, persistent vomiting, worsening symptoms.\n"
        "• Prevention: Annual flu vaccine, frequent handwashing, avoid touching face, cover coughs and sneezes.\n"
        "• Treatment: Rest and fluids. Paracetamol for fever (consult a doctor first). Antiviral drugs require a prescription.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "food poisoning": (
        "Food poisoning is illness caused by eating food contaminated with bacteria, viruses, or toxins.\n\n"
        "• What it is: An acute illness from consuming spoiled, undercooked, or contaminated food or water.\n"
        "• Symptoms: Nausea, vomiting, diarrhoea, stomach cramps, fever — usually within hours of eating.\n"
        "• Prevention: Wash hands before handling food, cook meat thoroughly, refrigerate food promptly, use clean water.\n"
        "• Treatment: Drink ORS (Oral Rehydration Solution) to prevent dehydration. See a doctor if severe or lasting 2+ days.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "diabetes": (
        "Diabetes is a chronic condition where the body cannot properly regulate blood sugar (glucose).\n\n"
        "• What it is: Insulin either isn't produced (Type 1) or isn't used effectively (Type 2), causing high blood sugar.\n"
        "• Types: Type 1 — autoimmune. Type 2 — most common. Gestational — during pregnancy.\n"
        "• Symptoms: Frequent urination, excessive thirst, unexplained weight loss, blurred vision, slow-healing wounds, fatigue.\n"
        "• Prevention (Type 2): Healthy weight, exercise 30 min/day, balanced low-sugar diet, avoid sugary drinks.\n"
        "• Management: Requires medical supervision — lifestyle changes, oral medicines, or insulin as prescribed.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "emergency": (
        "Emergency Red-Flag Symptoms — Call 108 or go to hospital immediately:\n\n"
        "• Chest pain, pressure, or tightness (possible heart attack)\n"
        "• Difficulty breathing or sudden shortness of breath\n"
        "• Sudden weakness or numbness in face, arm, or leg (possible stroke)\n"
        "• Sudden confusion or trouble speaking\n"
        "• Seizures or loss of consciousness\n"
        "• Severe or uncontrolled bleeding\n"
        "• High fever with stiff neck or severe headache\n"
        "• Severe abdominal pain\n"
        "• Bluish lips or fingertips\n\n"
        "📞 India Emergency: 108 (Ambulance) | 112 (All emergencies)"
    ),
    "vaccine": (
        "Vaccines train the immune system to fight diseases without causing illness.\n\n"
        "Common Vaccine Myths — Busted:\n"
        "• Myth: Vaccines cause the disease.  Fact: They use inactivated agents — cannot cause the disease.\n"
        "• Myth: Natural immunity is better.  Fact: Vaccines give immunity without the risk of serious illness.\n"
        "• Myth: Vaccines contain harmful ingredients.  Fact: All ingredients are rigorously safety-tested.\n"
        "• Myth: Too many vaccines overwhelm children.  Fact: Combination vaccines are thoroughly tested and safe.\n"
        "• Myth: Vaccines cause autism.  Fact: This claim has been thoroughly debunked by large-scale studies.\n\n"
        "• Always follow your doctor's and India's national immunization schedule."
    ),
    "covid": (
        "COVID-19 is an infectious disease caused by the SARS-CoV-2 coronavirus.\n\n"
        "• What it is: A respiratory illness spreading through droplets and aerosols from infected people.\n"
        "• Symptoms: Fever, dry cough, fatigue, loss of taste/smell, sore throat, headache, body ache. Severe: difficulty breathing.\n"
        "• Prevention: Stay up to date with COVID-19 vaccines, wear masks in crowded spaces, wash hands, ensure ventilation.\n"
        "• Treatment: Rest and fluids for mild cases. Severe cases need hospital care.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "cholera": (
        "Cholera is a severe bacterial infection caused by Vibrio cholerae, spread through contaminated water.\n\n"
        "• What it is: A waterborne disease causing extreme rapid dehydration — can be fatal within hours if untreated.\n"
        "• Symptoms: Sudden profuse watery diarrhoea, vomiting, muscle cramps, rapid dehydration.\n"
        "• Prevention: Drink only boiled or purified water, eat cooked food, wash hands with soap, use sanitary toilets.\n"
        "• Treatment: ORS (Oral Rehydration Solution) is the primary treatment. Severe cases need IV fluids and antibiotics.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "typhoid": (
        "Typhoid fever is a bacterial infection caused by Salmonella typhi, spread through contaminated food and water.\n\n"
        "• What it is: A systemic bacterial illness — common in areas with poor sanitation.\n"
        "• Symptoms: Prolonged high fever, weakness, stomach pain, headache, loss of appetite, constipation or diarrhoea.\n"
        "• Prevention: Typhoid vaccine, drink only safe/boiled water, eat thoroughly cooked food, thorough handwashing.\n"
        "• Treatment: Requires a full course of antibiotics from a doctor. Do not stop medicine early.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "hypertension": (
        "Hypertension (High Blood Pressure) is when blood pressure in arteries is persistently elevated.\n\n"
        "• What it is: Blood pressure above 140/90 mmHg consistently — called the 'silent killer' as it has no obvious symptoms.\n"
        "• Symptoms: Usually none. Severe: headache, dizziness, blurred vision, nosebleeds, chest pain.\n"
        "• Risk factors: Excess salt, obesity, inactivity, smoking, alcohol, stress, family history.\n"
        "• Prevention: Reduce salt, exercise daily, maintain healthy weight, quit smoking, limit alcohol.\n"
        "• Treatment: Lifestyle changes plus medicines prescribed by a doctor. Never stop medicines without consulting a doctor.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "asthma": (
        "Asthma is a chronic inflammatory condition of the airways that causes breathing difficulties.\n\n"
        "• What it is: Airways narrow, swell, and produce extra mucus — making breathing difficult.\n"
        "• Symptoms: Wheezing, shortness of breath, chest tightness, persistent cough — especially at night or during exercise.\n"
        "• Triggers: Dust, pollen, pet dander, smoke, cold air, air pollution, respiratory infections.\n"
        "• Prevention: Identify and avoid triggers, keep home dust-free, use air purifiers, avoid smoking areas.\n"
        "• Treatment: Inhalers (reliever and preventer) prescribed by a doctor. Never skip preventer medication.\n"
        "• Always consult a certified doctor for diagnosis and treatment."
    ),
    "fever": (
        "Fever is a temporary rise in body temperature above 98.6°F (37°C), usually a sign the body is fighting infection.\n\n"
        "• What it is: A natural immune response — a symptom, not a disease itself.\n"
        "• Common causes: Viral infections (flu, cold, COVID-19, dengue), bacterial infections, heat exhaustion.\n"
        "• When to seek emergency care: Fever above 103°F, fever in infants under 3 months, fever lasting 3+ days, fever with stiff neck or rash.\n"
        "• Self-care: Rest, drink plenty of fluids, damp cloth on forehead. Paracetamol can help (consult a doctor first).\n"
        "• Always consult a certified doctor if fever is very high or persists."
    ),
    "headache": (
        "A headache is pain or discomfort in the head, scalp, or neck.\n\n"
        "• What it is: One of the most common complaints — usually not serious, but some types need emergency care.\n"
        "• Common types: Tension headache (most common), migraine (severe throbbing, one-sided), cluster headache, sinus headache.\n"
        "• Emergency signs: Sudden severe 'thunderclap' headache, headache with fever + stiff neck, headache after head injury, with vision changes or weakness.\n"
        "• Self-care: Rest in a quiet dark room, stay hydrated, cold/warm compress, paracetamol (consult a doctor first).\n"
        "• Always consult a certified doctor for frequent, severe, or unusual headaches."
    ),
    "diarrhea": (
        "Diarrhoea is having three or more loose, watery bowel movements in a day.\n\n"
        "• What it is: Usually a gut infection — main danger is dehydration.\n"
        "• Common causes: Viral/bacterial infection, food poisoning, contaminated water.\n"
        "• Key treatment: Drink ORS (Oral Rehydration Solution) immediately — 1 packet in 1 litre clean water. Sip frequently.\n"
        "• Prevention: Wash hands before eating and after toilet, drink safe/boiled water, avoid raw/undercooked food.\n"
        "• When to see a doctor: Blood in stool, fever above 102°F, no improvement after 2 days, severe dehydration signs.\n"
        "• Always consult a certified doctor for severe or prolonged diarrhoea."
    ),
}

_GENERIC_FALLBACK = (
    "I can provide basic health information on these topics:\n\n"
    "• Dengue      • Malaria       • Tuberculosis (TB)\n"
    "• Flu         • Food Safety   • Diabetes\n"
    "• Emergency   • Vaccine Myths • COVID-19\n"
    "• Cholera     • Typhoid       • Hypertension\n"
    "• Asthma      • Fever         • Headache  • Diarrhoea\n\n"
    "Please ask about one of these topics or describe your concern.\n\n"
    "⚠️ This is educational information only. Always consult a certified doctor for diagnosis and treatment."
)

# ── Keyword → topic map ─────────────────────────────────
# Multi-word phrases and single words — all lowercase
TOPIC_MAP = {
    # multi-word first
    "blood pressure":  "hypertension",
    "food poisoning":  "food poisoning",
    "food safety":     "food poisoning",
    "loose motion":    "diarrhea",
    "loose stool":     "diarrhea",
    "watery stool":    "diarrhea",
    "stomach upset":   "diarrhea",
    "stomach pain":    "diarrhea",
    "loose motions":   "diarrhea",
    "high bp":         "hypertension",
    "low bp":          "hypertension",
    "blood sugar":     "diabetes",
    "sugar level":     "diabetes",
    # single words
    "dengue":          "dengue",
    "malaria":         "malaria",
    "tuberculosis":    "tuberculosis",
    "tb":              "tuberculosis",
    "flu":             "flu",
    "influenza":       "flu",
    "diabetes":        "diabetes",
    "insulin":         "diabetes",
    "sugar":           "diabetes",
    "emergency":       "emergency",
    "vaccine":         "vaccine",
    "vaccination":     "vaccine",
    "immunize":        "vaccine",
    "immunise":        "vaccine",
    "covid":           "covid",
    "coronavirus":     "covid",
    "corona":          "covid",
    "cholera":         "cholera",
    "typhoid":         "typhoid",
    "hypertension":    "hypertension",
    "asthma":          "asthma",
    "wheeze":          "asthma",
    "wheezing":        "asthma",
    "inhaler":         "asthma",
    "fever":           "fever",
    "temperature":     "fever",
    "headache":        "headache",
    "migraine":        "headache",
    "diarrhea":        "diarrhea",
    "diarrhoea":       "diarrhea",
    "vomiting":        "food poisoning",
    "vomit":           "food poisoning",
    "nausea":          "food poisoning",
    "food":            "food poisoning",
}


def _tokenize(text: str) -> str:
    """Lowercase and remove punctuation, return cleaned string."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_fallback_response(user_message: str) -> str:
    if not user_message or not user_message.strip():
        return _GENERIC_FALLBACK

    clean = _tokenize(user_message)
    logger.info("KB matching on cleaned text: '%s'", clean)

    # Sort keys: multi-word phrases first (longest first), then single words
    sorted_keys = sorted(TOPIC_MAP.keys(), key=lambda k: (-len(k.split()), -len(k)))

    for phrase in sorted_keys:
        topic = TOPIC_MAP[phrase]
        if " " in phrase:
            # Multi-word: substring match on cleaned text
            matched = phrase in clean
        else:
            # Single word: exact token match to avoid partial hits
            matched = phrase in clean.split()

        if matched:
            value = HEALTH_KB.get(topic)
            if value:
                logger.info("KB matched '%s' → topic '%s'", phrase, topic)
                return value + "\n\n⚠️ This is educational information only — not medical advice."

    logger.info("KB: no match found, returning generic fallback.")
    return _GENERIC_FALLBACK


# ── Regex helpers ────────────────────────────────────────
_MD_BOLD    = re.compile(r"\*{1,2}")
_MD_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MD_BULLET  = re.compile(r"^\s*-\s+", re.MULTILINE)
_MULTI_NL   = re.compile(r"\n{3,}")
_STRIP_TAGS = re.compile(r"<[^>]+>")

SUPPORTED_LANGS = ["en", "hi", "ta", "te", "kn", "ml", "bn", "mr", "gu", "pa"]

UI_STRINGS = {
    "chat_placeholder":  "Type your health question…",
    "chat_heading":      "Chat",
    "chat_subtext":      "Ask symptoms, prevention, vaccines",
    "welcome_msg":       "Hi. Ask me about symptoms, prevention, vaccines, and when to seek care.",
    "welcome_tip":       "Tip: use Quick Topics → or select your language above",
    "topics_heading":    "Quick Topics",
    "topics_subtext":    "tap to ask",
    "news_heading":      "Health News",
    "news_subtext":      "latest",
    "safety_heading":    "Safety",
    "safety_subtext":    "important",
    "safety_text":       "Educational only. This chatbot does not diagnose or prescribe. For severe symptoms (chest pain, difficulty breathing, fainting, seizures, severe bleeding), seek emergency care immediately.",
    "btn_clear":         "Clear",
    "btn_help":          "Help",
    "tagline":           "Public health awareness • no diagnosis",
    "chip_dengue":       "Dengue",
    "chip_malaria":      "Malaria",
    "chip_tb":           "Tuberculosis",
    "chip_flu":          "Flu",
    "chip_food":         "Food Safety",
    "chip_diabetes":     "Diabetes",
    "chip_emergency":    "Emergency Signs",
    "chip_vaccine":      "Vaccine Myths",
    "chip_videos":       "Health Videos",
    "chip_q_dengue":     "What are dengue symptoms and warning signs?",
    "chip_q_malaria":    "How to prevent malaria?",
    "chip_q_tb":         "How does TB spread and what are the symptoms?",
    "chip_q_flu":        "What are flu symptoms and when should I see a doctor?",
    "chip_q_food":       "Give me prevention tips for food poisoning.",
    "chip_q_diabetes":   "Explain diabetes in simple words.",
    "chip_q_emergency":  "What are emergency red-flag symptoms?",
    "chip_q_vaccine":    "Bust common vaccine myths.",
    "chip_q_videos":     "Show healthcare videos on dengue prevention.",
    "loading_news":      "Loading WHO news…",
    "no_news":           "Could not load WHO news.",
}

UI_CACHE: dict   = {"en": UI_STRINGS.copy()}
NEWS_CACHE: dict = {}
NEWS_EN: list    = []
_news_last_fetched: float = 0.0


# ── Helpers ─────────────────────────────────────────────
def clean_ai_text(text: str) -> str:
    t = str(text or "")
    t = _MD_BOLD.sub("", t)
    t = _MD_HEADING.sub("", t)
    t = _MD_BULLET.sub("• ", t)
    t = _MULTI_NL.sub("\n\n", t)
    return t.strip()


def translate_text(text: str, source: str, target: str, retries: int = 2) -> str:
    text = str(text or "").strip()
    if not text:
        return text
    if source == target:
        return text
    for attempt in range(retries):
        try:
            result = GoogleTranslator(source=source, target=target).translate(text)
            return result if result and result.strip() else text
        except Exception as e:
            wait = 1 + attempt
            logger.warning(
                "Translation attempt %d/%d failed (%s→%s): %s — retrying in %ds",
                attempt + 1, retries, source, target, str(e)[:80], wait
            )
            time.sleep(wait)
    logger.error("Translation failed after retries (%s→%s): '%s'", source, target, text[:40])
    return text


def translate_dict_sequential(data: dict, source: str, target: str) -> dict:
    if source == target:
        return data.copy()
    result = {}
    for key, val in data.items():
        result[key] = translate_text(val, source=source, target=target)
        time.sleep(0.2)
    return result


def fetch_who_news_english() -> list:
    try:
        req = urllib.request.Request(
            WHO_FEED_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; HealthBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        feed      = feedparser.parse(raw)
        news_list = []
        for entry in feed.entries[:6]:
            title   = entry.get("title", "No title")
            summary = _STRIP_TAGS.sub("", entry.get("summary", ""))
            news_list.append({
                "title": title,
                "desc":  summary[:250] + ("..." if len(summary) > 250 else ""),
                "link":  entry.get("link", "#")
            })
        logger.info("Fetched %d WHO news items.", len(news_list))
        return news_list
    except Exception as e:
        logger.error("WHO RSS error: %s", e)
        return []


def call_groq(messages: list) -> str:
    if not GROQ_API_KEY:
        raise EnvironmentError("GROQ_API_KEY is not set.")
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "temperature": 0.4,
        "max_tokens":  650
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json"
    }
    response = requests.post(GROQ_URL, json=payload, headers=headers, timeout=40)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


# ── Disk cache helpers ──────────────────────────────────
def ui_path(lang: str)   -> str: return os.path.join(TRANSLATION_DIR, f"ui_{lang}.json")
def news_path(lang: str) -> str: return os.path.join(TRANSLATION_DIR, f"news_{lang}.json")


def load_json_if_exists(path: str):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load %s: %s", path, e)
    return None


def save_json(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Saved translations to %s", path)
    except Exception as e:
        logger.warning("Failed to save %s: %s", path, e)


# ── Build/load caches ────────────────────────────────────
def build_or_load_caches():
    global NEWS_EN, _news_last_fetched
    logger.info("🔄 Initializing translation cache…")

    NEWS_EN = fetch_who_news_english()
    _news_last_fetched = time.time()
    NEWS_CACHE["en"] = NEWS_EN
    save_json(news_path("en"), NEWS_EN)
    save_json(ui_path("en"), UI_STRINGS)

    for lang in SUPPORTED_LANGS:
        if lang == "en":
            continue
        cached_ui = load_json_if_exists(ui_path(lang))
        if cached_ui is not None:
            UI_CACHE[lang] = cached_ui
            logger.info("Loaded UI translations from file for %s", lang)
        else:
            logger.info("Creating UI translations for %s…", lang)
            translated_ui = translate_dict_sequential(UI_STRINGS, source="en", target=lang)
            UI_CACHE[lang] = translated_ui
            save_json(ui_path(lang), translated_ui)

        cached_news = load_json_if_exists(news_path(lang))
        if cached_news is not None:
            NEWS_CACHE[lang] = cached_news
            logger.info("Loaded news translations from file for %s", lang)
        else:
            logger.info("Creating news translations for %s…", lang)
            translated_news = []
            for item in NEWS_EN:
                translated_news.append({
                    "title": translate_text(item["title"], source="en", target=lang),
                    "desc":  translate_text(item["desc"],  source="en", target=lang),
                    "link":  item["link"]
                })
                time.sleep(0.2)
            NEWS_CACHE[lang] = translated_news
            save_json(news_path(lang), translated_news)

    logger.info("✅ UI + news caches ready.")


def schedule_news_refresh():
    def _refresh_loop():
        while True:
            time.sleep(NEWS_TTL_SECS)
            logger.info("🔄 Refreshing WHO news…")
            global NEWS_EN, _news_last_fetched
            fresh = fetch_who_news_english()
            if fresh:
                NEWS_EN = fresh
                _news_last_fetched = time.time()
                NEWS_CACHE["en"] = fresh
                save_json(news_path("en"), fresh)
                for lang in SUPPORTED_LANGS:
                    if lang != "en":
                        NEWS_CACHE.pop(lang, None)
                logger.info("✅ WHO news refreshed.")
    threading.Thread(target=_refresh_loop, daemon=True).start()


# ── Routes ──────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data      = request.get_json(silent=True) or {}
    user_msg  = str(data.get("message") or "").strip()
    user_lang = str(data.get("lang") or "en").strip().lower()

    if user_lang not in SUPPORTED_LANGS:
        user_lang = "en"
    if not user_msg:
        return jsonify({"reply": "Please type a message."})
    if len(user_msg) > MAX_MSG_LEN:
        return jsonify({"reply": "Message too long. Please keep it under 800 characters."})

    try:
        history = session.get("history", [])

        english_input = translate_text(user_msg, source=user_lang, target="en")
        if not english_input or not english_input.strip():
            english_input = user_msg

        logger.info("english_input → '%s'", english_input)

        history.append({"role": "user", "content": english_input})
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]

        used_fallback = False
        try:
            english_reply = clean_ai_text(call_groq(history))
            history.append({"role": "assistant", "content": english_reply})
            if len(history) > MAX_HISTORY:
                history = history[-MAX_HISTORY:]
            session["history"] = history
        except Exception as api_err:
            logger.warning("Groq unavailable (%s), using built-in KB.", str(api_err)[:80])
            english_reply = get_fallback_response(english_input)
            used_fallback = True

        final_reply = translate_text(english_reply, source="en", target=user_lang)
        if not final_reply or not final_reply.strip():
            final_reply = english_reply

        return jsonify({"reply": final_reply, "fallback": used_fallback})

    except Exception as e:
        logger.exception("Unexpected /chat error: %s", e)
        return jsonify({"reply": "Server error. Please try again."}), 500


@app.route("/translate-ui", methods=["POST"])
def translate_ui():
    data = request.get_json(silent=True) or {}
    lang = str(data.get("lang") or "en").strip().lower()
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    return jsonify(UI_CACHE.get(lang, UI_STRINGS))


@app.route("/news", methods=["GET"])
def news():
    lang = request.args.get("lang", "en").strip().lower()
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    if lang in NEWS_CACHE and NEWS_CACHE[lang]:
        return jsonify(NEWS_CACHE[lang])
    return jsonify(NEWS_EN or [])


@app.route("/speak", methods=["POST"])
def speak():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    lang = str(data.get("lang") or "en").strip().lower()

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if len(text) > 500:
        text = text[:500] + "…"

    try:
        tts_lang_map = {
            "en": "en", "hi": "hi", "ta": "ta", "te": "te",
            "kn": "kn", "ml": "ml", "bn": "bn", "mr": "mr",
            "gu": "gu", "pa": "pa"
        }
        tts_lang     = tts_lang_map.get(lang, "en")
        tts          = gTTS(text=text, lang=tts_lang, slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        return send_file(audio_buffer, mimetype="audio/mpeg",
                         as_attachment=False, download_name="speak.mp3")
    except Exception as e:
        logger.error("TTS generation failed: %s", e)
        return jsonify({"error": "TTS generation failed"}), 500


@app.route("/clear-history", methods=["POST"])
def clear_history():
    session.pop("history", None)
    return jsonify({"status": "ok"})


@app.route("/cache-status", methods=["GET"])
def cache_status():
    return jsonify({
        "ui_cached":         list(UI_CACHE.keys()),
        "news_cached":       list(NEWS_CACHE.keys()),
        "news_last_fetched": _news_last_fetched,
        "groq_configured":   bool(GROQ_API_KEY)
    })


if __name__ == "__main__":
    threading.Thread(target=build_or_load_caches, daemon=True).start()
    schedule_news_refresh()
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
