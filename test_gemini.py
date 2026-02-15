"""Quick test to verify Gemini API key — with model fallback."""
import os, time, asyncio, logging
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)

key = os.getenv("GOOGLE_API_KEY")
print(f"API Key loaded: {key[:10]}...{key[-4:]}")
print(f"Key length: {len(key)}")

from google import genai
client = genai.Client(api_key=key)

# Try multiple models
MODELS = ["gemma-3-27b-it", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
print("\n=== Model Availability Check ===")
for m in MODELS:
    try:
        r = client.models.generate_content(model=m, contents="Say hi")
        print(f"  ✅ {m}: {r.text.strip()[:30]}")
    except Exception as e:
        err = str(e)[:80]
        print(f"  ❌ {m}: {err}")

# Full pipeline test via ml_engine (with fallback)
print("\n=== Full ML Pipeline Test (with fallback) ===")

async def test_pipeline():
    from ml_engine import extract_tasks, predict_cognitive_load
    from config import CogConfig
    cfg = CogConfig()

    print("\n--- NLP Task Extraction ---")
    tasks = await extract_tasks("Study Graph Theory for 2 hours and finish ML assignment")
    print(f"  ✅ Extracted {len(tasks)} tasks:")
    for t in tasks:
        print(f"     {t.title} | cat={t.category} | diff={t.difficulty} | dur={t.duration_minutes}min")

    time.sleep(1)

    print("\n--- Cognitive Load Prediction ---")
    for t in tasks:
        load = await predict_cognitive_load(t, sleep_hours=6, stress_level=3, lectures_today=4, cfg=cfg)
        print(f"  ✅ {t.title}: cognitive_load = {load}")

    print("\n🎉 Full pipeline works! The scheduler is ready.")

asyncio.run(test_pipeline())
