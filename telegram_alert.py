import os
import requests


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_alert(address, rank, trend_time):
    if not BOT_TOKEN or not CHAT_ID:
        print("  TELEGRAM: credentials not configured")
        return False

    text = (
        "🔥 TREND ALERT\n\n"
        f"Rank: #{rank}\n"
        f"Time: {trend_time}\n\n"
        "CA:\n"
        f"{address}"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": text,
            },
            timeout=15,
        )

        response.raise_for_status()

        result = response.json()

        if result.get("ok"):
            print("  TELEGRAM 🔔 SENT")
            return True

        print(f"  TELEGRAM ERROR: {result}")
        return False

    except Exception as e:
        print(f"  TELEGRAM ERROR: {e}")
        return False