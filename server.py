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

# ---------------------------------------------------------
# Refined Streamlit Styling
# ---------------------------------------------------------
st.markdown(
    """
<style>
    /* Clean up the main block container padding */
    .block-container {
        padding-top: 3.5rem !important;
        padding-bottom: 6rem !important;
    }

    /* Style the main expander/digest card */
    div[data-testid="stExpander"] {
        border-radius: 12px;
        border: 1px solid rgba(15, 23, 42, 0.1);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        margin-bottom: 1.5rem;
    }

    /* Polish the expander header */
    div[data-testid="stExpander"] summary {
        font-weight: 600;
        padding: 0.75rem 1rem;
    }

    /* Button enhancements */
    div.stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    div.stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
    }

    /* Chat input styling */
    .stChatInputContainer {
        border-radius: 12px;
        box-shadow: 0 -4px 12px rgba(0,0,0,0.05);
    }
    
    /* Make chat messages look polished */
    div[data-testid="stChatMessage"] {
        padding: 1rem;
        border-radius: 12px;
        border: 1px solid rgba(15, 23, 42, 0.05);
    }
</style>
""",
    unsafe_allow_html=True,
)
# ---------------------------------------------------------
# Page Header
# ---------------------------------------------------------
st.title("🚴 Training Coach")
st.caption("Your AI-powered endurance training companion.")

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
    st.error("⚠️ Missing API Keys in Streamlit Secrets.")
    st.stop()

BASE_URL = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ATHLETE_ID}"
AUTH = ("API_KEY", INTERVALS_API_KEY)

# ---------------------------------------------------------
# 3. Intervals.icu API Tools
# ---------------------------------------------------------


def get_athlete_profile() -> str:
    """Fetches athlete profile: weight, cycling FTP, running thresholds, max HR, and zones."""
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
            f"### Thresholds:\n" + "\n".join(sport_lines)
        )
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_recent_activities(days: int = 7) -> str:
    """Fetches completed activities over the last N days with summary metrics."""
    oldest = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    newest = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/activities?oldest={oldest}&newest={newest}"

    try:
        res = httpx.get(url, auth=AUTH, timeout=10.0)
        if res.status_code != 200:
            return f"Error: {res.text}"
        activities = res.json()
        if not activities:
            return f"No activities recorded in the last {days} days."

        summary = []
        for a in activities:
            act_id = a.get("id")
            summary.append(
                f"- **ID: `{act_id}`** | **{a.get('start_date_local', '')[:10]}** [{a.get('type')}] **{a.get('name')}**\n"
                f"  Duration: {round(a.get('moving_time', 0)/60, 1)}m | TSS/Load: {a.get('icu_training_load', 'N/A')} | "
                f"Avg Watts: {a.get('icu_weighted_avg_watts', 'N/A')}W | HR: {a.get('average_heartrate', 'N/A')} bpm | RPE: {a.get('perceived_exertion', 'N/A')}"
            )
        return "\n\n".join(summary)
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_activity_details(activity_id: str) -> str:
    """Fetches interval breakdown, cardiac drift (decoupling), and efficiency factor for an activity."""
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

        intervals_summary = []
        for idx, i in enumerate(data.get("icu_intervals", [])):
            if i.get("type") in ["WORK", "RECOVERY", "WARMUP", "COOLDOWN"]:
                dur = round(i.get("elapsed_time", 0) / 60, 1)
                watts = round(i.get("average_watts", 0))
                hr = round(i.get("average_heartrate", 0))
                intervals_summary.append(
                    f"  - Set {idx+1} ({i.get('type')}): {dur}m @ {watts}W, {hr} bpm"
                )

        intervals_str = (
            "\n".join(intervals_summary)
            if intervals_summary
            else "  No discrete intervals extracted."
        )

        return (
            f"### Diagnostics: {name} ({date})\n"
            f"- **NP**: {np_watts}W | **Avg HR**: {avg_hr} bpm | **Cadence**: {cadence} rpm\n"
            f"- **Aerobic Decoupling**: {decoupling}% | **EF**: {ef}\n"
            f"### Interval Breakdown:\n{intervals_str}"
        )
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_wellness_and_load(days: int = 7) -> str:
    """Fetches daily wellness logs: CTL (Fitness), ATL (Fatigue), TSB (Form), HRV, RHR, Sleep."""
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
                f"- **{day.get('id')}**: CTL: {day.get('ctl', 'N/A')} | ATL: {day.get('atl', 'N/A')} | "
                f"Form: {day.get('rampRate', 'N/A')} | RHR: {day.get('restingHR', 'N/A')} bpm | HRV: {day.get('hrv', 'N/A')} | Sleep: {day.get('sleepQuality', 'N/A')}/5"
            )
        return "### Wellness & Load History:\n" + "\n".join(report)
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_power_curve(days: int = 42) -> str:
    """Retrieves athlete peak power curve durations over a rolling window."""
    url = f"{BASE_URL}/power-curves?days={days}"
    try:
        res = httpx.get(url, auth=AUTH, timeout=10.0)
        if res.status_code != 200:
            return f"Error: {res.text}"
        curves = res.json()
        if not curves:
            return "No power curve found."

        best_efforts = curves[0].get("curves", [{}])[0]
        peaks = []
        for sec, label in [
            (5, "5s Peak"),
            (60, "1m Peak"),
            (300, "5m (VO2max)"),
            (1200, "20m (Threshold)"),
            (3600, "60m (Hour)"),
        ]:
            peaks.append(f"- **{label}**: {best_efforts.get(str(sec), 'N/A')}W")

        return f"### Power Duration Curve (Last {days} Days):\n" + "\n".join(
            peaks
        )
    except Exception as e:
        return f"Request failed: {str(e)}"


def get_calendar_events(days_ahead: int = 7, days_past: int = 1) -> str:
    """Checks the athlete's calendar for upcoming planned workouts or races."""
    oldest = (datetime.now() - timedelta(days=days_past)).strftime("%Y-%m-%d")
    newest = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    url = f"{BASE_URL}/events?oldest={oldest}&newest={newest}"

    try:
        res = httpx.get(url, auth=AUTH, timeout=10.0)
        if res.status_code != 200:
            return f"Error: {res.text}"
        events = res.json()
        if not events:
            return "No calendar events found."

        summary = []
        for ev in events:
            date = ev.get("start_date_local", "")[:10]
            summary.append(
                f"- **{date}** [{ev.get('category', 'WORKOUT')}]: **{ev.get('name', 'Workout')}**"
            )
        return "### Calendar Schedule:\n" + "\n".join(summary)
    except Exception as e:
        return f"Request failed: {str(e)}"


def schedule_structured_workout(
    date: str, name: str, workout_description: str, workout_type: str = "Ride"
) -> str:
    """Schedules a structured workout to the Intervals calendar."""
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
# 4. Configurable Weekly / Daily Digest Exporter
# ---------------------------------------------------------
with st.expander("📥 Export Training Digest (Sync to Notebook)", expanded=False):
    st.write(
        "Generate a structured Markdown summary to upload/paste into your Gemini Notebook."
    )

    days_choice = st.radio(
        "Select Timeframe Window:",
        options=[1, 3, 7],
        format_func=lambda x: (
            f"Last 1 Day (Today)" if x == 1 else f"Last {x} Days"
        ),
        horizontal=True,
    )

    if st.button(
        f"⚡ Generate {days_choice}-Day Digest",
        use_container_width=True,
        type="primary",
    ):
        with st.spinner("Compiling training digest..."):
            client = genai.Client(api_key=GEMINI_API_KEY)

            # Fetch fresh data for the exact window
            raw_activities = get_recent_activities(days=days_choice)
            raw_wellness = get_wellness_and_load(days=days_choice)
            raw_profile = get_athlete_profile()

            digest_prompt = f"""
            You are a master endurance sports coach. Synthesize the following athlete data into a clean, executive Markdown Training Digest.
            This document will be saved as context in the athlete's long-term training notebook.
            
            Timeframe: Last {days_choice} day(s).
            
            Data Provided:
            {raw_profile}
            
            Completed Activities:
            {raw_activities}
            
            Wellness, Fatigue & Form:
            {raw_wellness}
            
            Formatting Structure:
            # 📊 Training & Recovery Digest ({datetime.now().strftime('%Y-%m-%d')})
            **Window**: Last {days_choice} Day(s)
            
            ## 1. Executive Summary & Training Load
            - CTL (Fitness), ATL (Fatigue), TSB (Form/Freshness)
            - Total volume/TSS completed in this window
            
            ## 2. Key Completed Workouts & Quality
            - Breakdown of rides/runs with Normalized Power, HR decoupling/drift, and interval execution quality
            
            ## 3. Physiological Readiness & Recovery
            - Sleep, HRV trends, resting HR, and perceived fatigue status
            
            ## 4. Coach's Tactical Directives
            - 2-3 bullet points on what to prioritize next based on these numbers (e.g. carb fueling, durability, intensity targets).
            """

            try:
                summary_resp = client.models.generate_content(
                    model="gemini-3.5-flash-lite", contents=digest_prompt
                )
                st.session_state["digest_md"] = summary_resp.text
                st.session_state["digest_days"] = days_choice
            except Exception as e:
                st.error(f"Failed to generate digest: {str(e)}")

    if "digest_md" in st.session_state:
        st.markdown("---")
        st.markdown(st.session_state["digest_md"])

        # Download Button for the Notebook
        filename = f"Training_Digest_{datetime.now().strftime('%Y-%m-%d')}_{st.session_state.get('digest_days', 7)}d.md"
        st.download_button(
            label="⬇️ Download Markdown File",
            data=st.session_state["digest_md"],
            file_name=filename,
            mime="text/markdown",
            use_container_width=True,
        )

# ---------------------------------------------------------
# 5. Coach System Prompt & Persona
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
# 6. Mobile Chat Interface
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

    client = genai.Client(api_key=GEMINI_API_KEY)

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
                    model="gemini-3.5-flash-lite", contents=prompt, config=config
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