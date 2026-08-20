from datetime import datetime, timedelta
import json
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
# 1. UI & Page Configuration
# ---------------------------------------------------------
st.set_page_config(
    page_title="Training Coach",
    page_icon="🚴",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("🚴 Training Coach & Intervals Lab")

# ---------------------------------------------------------
# 2. Secrets & API Setup
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
# 3. Complete Intervals.icu API Tools
# ---------------------------------------------------------


def get_athlete_profile() -> str:
    """Fetches athlete baseline info including weight, cycling FTP, running thresholds (LTHR), max heart rate, and configured zones."""
    try:
        res = httpx.get(f"{BASE_URL}", auth=AUTH, timeout=10.0)
        if res.status_code != 200:
            return f"Error: {res.text}"
        data = res.json()
        name = data.get("name", "Athlete")
        weight_kg = data.get("weight")
        weight_str = (
            f"{weight_kg} kg ({round(float(weight_kg) * 2.20462, 1)} lbs)"
            if weight_kg
            else "Not set"
        )

        sport_lines = []
        for sport in data.get("sportSettings", []):
            types_list = ", ".join(sport.get("types", []))
            ftp = sport.get("ftp", "N/A")
            lthr = sport.get("lthr", "N/A")
            max_hr = sport.get("max_hr", "N/A")
            sport_lines.append(
                f"- **{types_list}**: FTP: {ftp}W | LTHR: {lthr} bpm | Max HR: {max_hr} bpm"
            )

        return (
            f"### Athlete Profile: {name}\n"
            f"- **Weight**: {weight_str}\n"
            f"### Sport Thresholds:\n" + "\n".join(sport_lines)
        )
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_recent_activities(days: int = 7) -> str:
    """Fetches a list of completed activities (rides, runs, swims) over the last N days with summary metrics."""
    oldest = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    newest = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/activities?oldest={oldest}&newest={newest}"

    try:
        res = httpx.get(url, auth=AUTH, timeout=10.0)
        if res.status_code != 200:
            return f"Error: {res.text}"
        activities = res.json()
        if not activities:
            return f"No activities found in the last {days} days."

        summary = []
        for a in activities:
            act_id = a.get("id")
            summary.append(
                f"- **ID: `{act_id}`** | **{a.get('start_date_local', '')[:10]}** [{a.get('type')}] **{a.get('name')}**\n"
                f"  Duration: {round(a.get('moving_time', 0)/60, 1)}m | Load/TSS: {a.get('icu_training_load', 'N/A')} | "
                f"Avg Watts: {a.get('icu_weighted_avg_watts', 'N/A')}W | HR: {a.get('average_heartrate', 'N/A')} bpm | RPE: {a.get('perceived_exertion', 'N/A')}"
            )
        return "\n\n".join(summary)
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_activity_details(activity_id: str) -> str:
    """Fetches deep interval data, aerobic decoupling (cardiac drift), efficiency factor (EF), and interval compliance for a specific activity ID."""
    url = f"https://intervals.icu/api/v1/activity/{activity_id}"
    try:
        res = httpx.get(url, auth=AUTH, timeout=12.0)
        if res.status_code != 200:
            return f"Error: {res.text}"
        data = res.json()

        name = data.get("name", "Workout")
        date = data.get("start_date_local", "")[:10]
        decoupling = data.get("icu_decoupling", "N/A")
        ef = data.get("icu_efficiency_factor", "N/A")
        np_watts = data.get("icu_weighted_avg_watts", "N/A")
        avg_hr = data.get("average_heartrate", "N/A")
        cadence = data.get("average_cadence", "N/A")

        # Extract interval breakdown
        intervals_summary = []
        for idx, i in enumerate(data.get("icu_intervals", [])):
            if i.get("type") in ["WORK", "RECOVERY", "WARMUP", "COOLDOWN"]:
                dur = round(i.get("elapsed_time", 0) / 60, 1)
                watts = round(i.get("average_watts", 0))
                hr = round(i.get("average_heartrate", 0))
                intervals_summary.append(
                    f"  - Interval {idx+1} ({i.get('type')}): {dur}m @ {watts}W, {hr} bpm"
                )

        intervals_str = (
            "\n".join(intervals_summary)
            if intervals_summary
            else "  No discrete intervals extracted."
        )

        return (
            f"### Activity Diagnostics: {name} ({date})\n"
            f"- **Normalized Power**: {np_watts}W | **Avg HR**: {avg_hr} bpm | **Avg Cadence**: {cadence} rpm\n"
            f"- **Aerobic Decoupling (Drift)**: {decoupling}% (Ideal is < 5%)\n"
            f"- **Efficiency Factor (EF)**: {ef}\n"
            f"### Key Interval Sets:\n{intervals_str}"
        )
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_wellness_and_load(days: int = 7) -> str:
    """Fetches daily wellness logs including CTL (Fitness), ATL (Fatigue), TSB (Form/Freshness), HRV, Resting Heart Rate, and Sleep Quality."""
    oldest = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    newest = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/wellness?oldest={oldest}&newest={newest}"

    try:
        res = httpx.get(url, auth=AUTH, timeout=10.0)
        if res.status_code != 200:
            return f"Error: {res.text}"
        data = res.json()
        if not data:
            return f"No wellness data found for the last {days} days."

        report = []
        for day in data:
            report.append(
                f"- **{day.get('id')}**: Fitness (CTL): {day.get('ctl', 'N/A')} | Fatigue (ATL): {day.get('atl', 'N/A')} | "
                f"Form (Ramp): {day.get('rampRate', 'N/A')} | RHR: {day.get('restingHR', 'N/A')} bpm | HRV: {day.get('hrv', 'N/A')} | Sleep: {day.get('sleepQuality', 'N/A')}/5"
            )
        return "### Wellness & Load History:\n" + "\n".join(report)
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_power_curve(days: int = 42) -> str:
    """Retrieves athlete peak power curve durations (5s, 1m, 5m, 20m, 60m) over a rolling window (e.g. 42 or 84 days)."""
    url = f"{BASE_URL}/power-curves?days={days}"
    try:
        res = httpx.get(url, auth=AUTH, timeout=10.0)
        if res.status_code != 200:
            return f"Error: {res.text}"
        curves = res.json()
        if not curves:
            return "No power duration curve found for this period."

        # Parse key durations
        best_efforts = curves[0].get("curves", [{}])[0]
        peaks = []
        for sec, label in [
            (5, "5s Peak"),
            (60, "1m Peak"),
            (300, "5m (VO2max)"),
            (1200, "20m (Threshold)"),
            (3600, "60m (Hour)"),
        ]:
            val = best_efforts.get(str(sec), "N/A")
            peaks.append(f"- **{label}**: {val}W")

        return f"### Power Duration Best Efforts (Last {days} Days):\n" + "\n".join(
            peaks
        )
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_calendar_events(days_ahead: int = 7, days_past: int = 1) -> str:
    """Checks the athlete's calendar for upcoming planned workouts, rest days, or scheduled race events."""
    oldest = (datetime.now() - timedelta(days=days_past)).strftime("%Y-%m-%d")
    newest = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    url = f"{BASE_URL}/events?oldest={oldest}&newest={newest}"

    try:
        res = httpx.get(url, auth=AUTH, timeout=10.0)
        if res.status_code != 200:
            return f"Error: {res.text}"
        events = res.json()
        if not events:
            return "No calendar events or planned workouts found in this timeframe."

        summary = []
        for ev in events:
            date = ev.get("start_date_local", "")[:10]
            name = ev.get("name", "Workout")
            category = ev.get("category", "WORKOUT")
            summary.append(f"- **{date}** [{category}]: **{name}**")
        return "### Calendar Schedule:\n" + "\n".join(summary)
    except Exception as e:
        return f"Request failed: {str(e)}"


def schedule_structured_workout(
    date: str, name: str, workout_description: str, workout_type: str = "Ride"
) -> str:
    """
    Schedules a structured workout to the Intervals calendar (syncs automatically to COROS/Wahoo/Garmin).
    'date' format: YYYY-MM-DD
    'workout_type': 'Ride' or 'Run'
    'workout_description': Intervals.icu format (e.g. 'Warmup\\n- 10m 60%\\nMain Set\\n- 2x 15m 90% 5m 55%\\nCooldown\\n- 5m 50%')
    """
    url = f"{BASE_URL}/events"
    payload = {
        "start_date_local": f"{date}T07:00:00",
        "name": name,
        "type": workout_type,
        "description": workout_description,
    }
    try:
        res = httpx.post(url, auth=AUTH, json=payload, timeout=10.0)
        if res.status_code in [200, 201]:
            return f"✅ Successfully scheduled '{name}' ({workout_type}) on {date}!"
        return f"Failed to schedule: {res.text}"
    except Exception as e:
        return f"Request failed: {str(e)}"


# ---------------------------------------------------------
# 4. Coach System Prompt & Persona
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = """
You are "Training Coach" — a seasoned endurance coach with deep expertise in exercise physiology, sports nutrition, and low-volume training optimization.
You coach a time-crunched athlete who trains 4 to 5 hours per week while balancing family, work, and recovery.

Your principles:
1. Always base feedback on the athlete's real data. Call your Intervals.icu tools to check recent workouts, intervals, cardiac drift, or wellness before answering.
2. Be empathetic to schedule constraints, but don't hesitate to push back against overtraining or unproductive junk volume.
3. Keep responses structured, concise, and scannable for quick reading on a phone screen.
4. When prescribing workouts, write them in standard Intervals.icu text syntax so they sync smoothly to their watch/bike computer.
"""

# ---------------------------------------------------------
# 5. Mobile Chat Interface
# ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat Input
if prompt := st.chat_input("Ask your coach anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Initialize Client
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Tool List
    tool_belt = [
        get_athlete_profile,
        get_recent_activities,
        get_activity_details,
        get_wellness_and_load,
        get_power_curve,
        get_calendar_events,
        schedule_structured_workout,
    ]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=tool_belt,
        temperature=0.6,
    )

    with st.chat_message("assistant"):
        with st.spinner("Analyzing Intervals.icu data..."):
            try:
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt,
                    config=config,
                )
                output = (
                    response.text
                    or "I've processed your training request and updated your data."
                )
                st.markdown(output)
                st.session_state.messages.append(
                    {"role": "assistant", "content": output}
                )
            except Exception as e:
                err = f"Coach Error: {str(e)}"
                st.error(err)
                st.session_state.messages.append(
                    {"role": "assistant", "content": err}
                )