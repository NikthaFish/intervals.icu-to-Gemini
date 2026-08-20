import os
from datetime import datetime, timedelta
import httpx
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
import uvicorn

# 1. Initialize FastMCP Server
mcp = FastMCP("IntervalsICU-Coach")

ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID", "")
API_KEY = os.getenv("INTERVALS_API_KEY", "")
BASE_URL = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
AUTH = ("API_KEY", API_KEY)


@mcp.tool()
async def get_recent_activities(days: int = 7) -> str:
    """Fetches completed activities for the last N days with key metrics (Power, HR, Load, RPE)."""
    if not ATHLETE_ID or not API_KEY:
        return "Error: INTERVALS_ATHLETE_ID or INTERVALS_API_KEY is not set."

    oldest = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    newest = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/activities?oldest={oldest}&newest={newest}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, auth=AUTH)
        if response.status_code != 200:
            return f"Error fetching activities: {response.text}"

        activities = response.json()
        if not activities:
            return "No activities found in the selected date range."

        summary = []
        for act in activities:
            summary.append(
                f"- **Date**: {act.get('start_date_local', 'N/A')[:10]} | **Type**: {act.get('type')} | **Name**: {act.get('name')}\n"
                f"  Duration: {round(act.get('moving_time', 0)/60, 1)}m | Load/TSS: {act.get('icu_training_load', 'N/A')} | "
                f"Avg Power: {act.get('icu_weighted_avg_watts', 'N/A')}W | Avg HR: {act.get('average_heartrate', 'N/A')} bpm\n"
                f"  RPE: {act.get('perceived_exertion', 'N/A')} | Feel: {act.get('feel', 'N/A')}"
            )
        return "\n\n".join(summary)


@mcp.tool()
async def get_fitness_and_load() -> str:
    """Retrieves current fitness (CTL), fatigue (ATL), and form/freshness (TSB) metrics."""
    if not ATHLETE_ID or not API_KEY:
        return "Error: INTERVALS_ATHLETE_ID or INTERVALS_API_KEY is not set."

    today = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/wellness/{today}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, auth=AUTH)
        if response.status_code != 200:
            return f"Error fetching wellness data: {response.text}"

        data = response.json()
        return (
            f"### Athlete Status for {today}:\n"
            f"- **Fitness (CTL)**: {data.get('ctl', 'N/A')}\n"
            f"- **Fatigue (ATL)**: {data.get('atl', 'N/A')}\n"
            f"- **Form (TSB / Ramp)**: {data.get('rampRate', 'N/A')}\n"
            f"- **Resting HR**: {data.get('restingHR', 'N/A')} bpm\n"
            f"- **HRV**: {data.get('hrv', 'N/A')}\n"
            f"- **Sleep Quality**: {data.get('sleepQuality', 'N/A')}/5"
        )


@mcp.tool()
async def schedule_workout(date: str, name: str, workout_description: str) -> str:
    """Schedules a structured workout to the Intervals.icu calendar."""
    if not ATHLETE_ID or not API_KEY:
        return "Error: INTERVALS_ATHLETE_ID or INTERVALS_API_KEY is not set."

    url = f"{BASE_URL}/events"
    payload = {
        "start_date_local": f"{date}T08:00:00",
        "name": name,
        "type": "Ride",
        "description": workout_description,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, auth=AUTH, json=payload)
        if response.status_code in [200, 201]:
            return f"Successfully scheduled '{name}' on {date}!"
        return f"Failed to schedule workout: {response.text}"


# 2. Health check route for Railway
async def health_check(request):
    return JSONResponse({"status": "healthy", "service": "Intervals.icu MCP"})


# 3. Mount Starlette with both the healthcheck and the MCP SSE app
app = Starlette(
    routes=[
        Route("/", health_check),
        Mount("/", app=mcp.sse_app()),
    ]
)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)