# public-health-chatbot

# 🏥 Public Health Chatbot

A multilingual public health awareness chatbot built with **Flask**, powered by **Groq AI (LLaMA 3.3)** with a built-in offline knowledge base as fallback. Designed to educate users about common diseases, symptoms, prevention, and when to seek emergency care — in **10 Indian languages**.

> ⚠️ **Disclaimer:** This chatbot is for educational purposes only. It does not diagnose, prescribe, or replace professional medical advice. Always consult a certified doctor for any medical condition.

---

## 🌟 Features

- 🤖 **AI-Powered Chat** — Uses Groq's LLaMA 3.3 70B model for intelligent health responses
- 📚 **Offline Fallback KB** — Built-in knowledge base for 16 health topics when AI is unavailable
- 🌍 **10 Indian Languages** — English, Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi
- 📰 **Live WHO News** — Fetches and displays latest WHO health news (auto-refreshes every 6 hours)
- 🔊 **Text-to-Speech** — Listen to any response in your selected language
- ⚡ **Translation Cache** — All UI and news translations saved to disk for instant loading
- 🚨 **Emergency Awareness** — Immediately flags life-threatening symptoms with emergency numbers

---

## 🦠 Health Topics Covered

| Topic | Topic | Topic | Topic |
|-------|-------|-------|-------|
| Dengue | Malaria | Tuberculosis (TB) | Influenza (Flu) |
| COVID-19 | Cholera | Typhoid | Diabetes |
| Hypertension | Asthma | Fever | Headache |
| Diarrhoea | Food Poisoning | Vaccine Myths | Emergency Signs |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python, Flask |
| AI Model | Groq API — LLaMA 3.3 70B Versatile |
| Translation | deep-translator (Google Translate) |
| Text-to-Speech | gTTS (Google Text-to-Speech) |
| News Feed | WHO RSS Feed + feedparser |
| Frontend | HTML, CSS, JavaScript |
| Session | Flask server-side sessions |

---

## 📁 Project Structure

public-health-chatbot/
│
├── app.py # Main Flask application
├── requirements.txt # Python dependencies
├── .env # Environment variables (not committed)
├── .env.example # Example env file
│
├── templates/
│ └── index.html # Main UI template
│
├── static/
│ ├── style.css # Stylesheet
│ └── app.js # Frontend JavaScript
│
└── translations/ # Auto-generated translation cache
├── ui_en.json
├── ui_hi.json
├── news_en.json
└── ...


---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/YourUsername/public-health-chatbot.git
cd public-health-chatbot


python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

### Install Dependancies
pip install -r requirements.txt

### Set Up Environment Variables
FLASK_SECRET_KEY=your-secret-key-here
GROQ_API_KEY=your-groq-api-key-here
FLASK_DEBUG=false

### Run the App
python app.py
