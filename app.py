from datetime import datetime, timedelta
import os
# pyrefly: ignore [missing-import]
from google import genai
# pyrefly: ignore [missing-import]
from google.genai import types
# pyrefly: ignore [missing-import]
import httpx
# pyrefly: ignore [missing-import]
import streamlit as st

# ---------------------------------------------------------
# 1. Page Configuration & Title
# ---------------------------------------------------------
st.set_page_config(
    page_title="Training Coach",
    page_icon="🚴",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("🚴 Training Coach")

# ---------------------------------------------------------
# 2. Credentials & Setup (From Streamlit Secrets)
# ---------------------------------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
INTERVALS_API_KEY = st.secrets.get(
    "INTERVALS_API_KEY", os.getenv("INTERVALS_API_KEY", "")
)
INTERVALS_ATHLETE_ID = st.secrets.get(
    "INTERVALS_ATHLETE_ID", os.getenv("INTERVALS_ATHLETE_ID", "")
)

if not GEMINI_API_KEY or not INTERVALS_API_KEY or not INTERVALS_ATHLETE_ID:
    st.error(
        "⚠️ Missing API Keys! Please configure GEMINI_API_KEY, INTERVALS_API_KEY, and INTERVALS_ATHLETE_ID in Streamlit Secrets."
    )
    st.stop()

BASE_URL = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ATHLETE_ID}"
AUTH = ("API_KEY", INTERVALS_API_KEY)

# ---------------------------------------------------------
# 3. Intervals.icu Live Tools
# ---------------------------------------------------------
def get_recent_activities(days: int = 7) -> str:
    """Fetches completed activities (cycling, running, etc.) for the last N days with key metrics."""
    oldest = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    newest = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/activities?oldest={oldest}&newest={newest}"

    try:
        res = httpx.get(url, auth=AUTH, timeout=10.0)
        if res.status_code != 200:
            return f"Intervals.icu Error: {res.text}"
        activities = res.json()
        if not activities:
            return f"No activities recorded in the last {days} days."

        summary = []
        for a in activities:
            summary.append(
                f"- **{a.get('start_date_local', 'N/A')[:10]}** | [{a.get('type')}] **{a.get('name')}**\n"
                f"  Duration: {round(a.get('moving_time', 0)/60, 1)} min | Load/TSS: {a.get('icu_training_load', 'N/A')} | "
                f"Avg Power: {a.get('icu_weighted_avg_watts', 'N/A')}W | HR: {a.get('average_heartrate', 'N/A')} bpm\n"
                f"  RPE: {a.get('perceived_exertion', 'N/A')} | Feel: {a.get('feel', 'N/A')}"
            )
        return "\n\n".join(summary)
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_fitness_and_wellness() -> str:
    """Fetches today's Fitness (CTL), Fatigue (ATL), Form (TSB), Resting HR, HRV, and sleep."""
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/wellness/{today}"

    try:
        res = httpx.get(url, auth=AUTH, timeout=10.0)
        if res.status_code != 200:
            return f"Intervals.icu Error: {res.text}"
        data = res.json()
        return (
            f"### Athlete Status for {today}:\n"
            f"- **Fitness (CTL)**: {data.get('ctl', 'N/A')}\n"
            f"- **Fatigue (ATL)**: {data.get('atl', 'N/A')}\n"
            f"- **Form (TSB / Ramp Rate)**: {data.get('rampRate', 'N/A')}\n"
            f"- **Resting Heart Rate**: {data.get('restingHR', 'N/A')} bpm\n"
            f"- **HRV**: {data.get('hrv', 'N/A')}\n"
            f"- **Sleep Quality**: {data.get('sleepQuality', 'N/A')}/5"
        )
    except Exception as e:
        return f"Request failed: {str(e)}"


def schedule_structured_workout(date: str, name: str, workout_description: str) -> str:
    """Schedules a structured workout to the Intervals calendar (syncs to COROS). date format: YYYY-MM-DD."""
    url = f"{BASE_URL}/events"
    payload = {
        "start_date_local": f"{date}T08:00:00",
        "name": name,
        "type": "Ride",
        "description": workout_description,
    }
    try:
        res = httpx.post(url, auth=AUTH, json=payload, timeout=10.0)
        if res.status_code in [200, 201]:
            return f"✅ Workout '{name}' scheduled for {date}!"
        return f"Failed to schedule: {res.text}"
    except Exception as e:
        return f"Request failed: {str(e)}"


# ---------------------------------------------------------
# 4. Coaching Brain & Persona
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = """
You are "Training Coach" with extensive experience coaching cyclists and triathletes, with a deep background in exercise science and sports nutrition.
You specialize in helping time-crunched athletes who train 4-5 hours per week balance performance gains against life and family stress.

Key coaching traits:
1. Empathetic and understanding, but not afraid to push back when a workout plan or progression is unrealistic.
2. Provide science-backed rationales for your recommendations.
3. You have direct tool access to the athlete's live Intervals.icu account. Always call your tools to inspect recent activities, power numbers, HR data, or fatigue metrics before giving feedback on their workouts.
4. Keep your responses actionable, concise, and structured for quick mobile reading.
"""

# ---------------------------------------------------------
# 5. Mobile Chat Interface
# ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User Input
if prompt := st.chat_input("Ask your coach..."):
    # Append user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Initialize Gemini Client
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Configure Gemini with tools & system instruction
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=[get_recent_activities, get_fitness_and_wellness, schedule_structured_workout],
        temperature=0.7,
    )

    with st.chat_message("assistant"):
        with st.spinner("Analyzing training data..."):
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config=config,
                )
                response_text = response.text or "I've reviewed your request and updated your logs."
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            except Exception as e:
                err_msg = f"Coach error: {str(e)}"
                st.error(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})