import sqlite3
import time
import requests
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

DB = Path("trend_research_v2.db")

POLL = 5                 # check database every 5 seconds

BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"


# ============================================================
# DATABASE
# ============================================================

def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(
            url,
            json=payload,
            timeout=20,
        )

        if r.status_code != 200:
            print(
                f"[TELEGRAM ERROR] "
                f"HTTP {r.status_code}: {r.text}"
            )
            return False

        data = r.json()

        if not data.get("ok"):
            print(
                f"[TELEGRAM ERROR] "
                f"{data}"
            )
            return False

        return True

    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False


# ============================================================
# FORMAT ALERT
# ============================================================

def make_alert(row):

    address = row["address"]
    event_time = row["t"]
    rank = row["rank"]

    mc = row["mc"]
    price = row["price"]
    liquidity = row["liquidity"]
    vol5 = row["vol5"]
    buys = row["buys"]
    sells = row["sells"]

    text = (
        "🔥 TREND MARK\n"
        "\n"
        f"CA:\n{address}\n"
        "\n"
        f"Rank: #{rank}\n"
        f"Time: {event_time}\n"
        "\n"
        f"MC: {mc}\n"
        f"Price: {price}\n"
        f"Liq: {liquidity}\n"
        f"Vol 5m: {vol5}\n"
        f"Buys: {buys}\n"
        f"Sells: {sells}"
    )

    return text


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("==========================================")
    print("       TREND TELEGRAM ALERT")
    print("==========================================")
    print(f"Database: {DB.resolve()}")
    print(f"Poll: {POLL}s")
    print()
    print("Watching: trend_events")
    print("Alert: ENTER only")
    print("Duplicate CA: NEVER send again")
    print()

    if BOT_TOKEN == "8446728614:AAHs6p7q4so3PE9ws4r58dlt0QtX4owr2R8":
        print("ERROR: Put your Telegram bot token in the file.")
        return

    if CHAT_ID == "6771666410":
        print("ERROR: Put your Telegram chat ID in the file.")
        return

    con = get_db()

    # ========================================================
    # CREATE SENT-ALERT TABLE IF IT DOES NOT EXIST
    # ========================================================

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_sent(
            address TEXT PRIMARY KEY,
            event_id INTEGER,
            sent_at TEXT
        )
        """
    )

    con.commit()

    # ========================================================
    # START FROM CURRENT DATABASE POSITION
    #
    # Old ENTER events will NOT be sent.
    #
    # Only new ENTER events appearing after this program
    # starts will be considered.
    # ========================================================

    row = con.execute(
        """
        SELECT COALESCE(MAX(id), 0) AS max_id
        FROM trend_events
        """
    ).fetchone()

    last_id = row["max_id"]

    print(
        f"Starting after existing event ID: {last_id}"
    )

    print("Ready.\n")

    # ========================================================
    # LOOP
    # ========================================================

    try:

        while True:

            rows = con.execute(
                """
                SELECT
                    id,
                    address,
                    t,
                    event_type,
                    rank,
                    mc,
                    price,
                    liquidity,
                    vol5,
                    buys,
                    sells
                FROM trend_events
                WHERE id > ?
                  AND event_type = 'ENTER'
                ORDER BY id ASC
                """,
                (last_id,),
            ).fetchall()

            for row in rows:

                event_id = row["id"]
                address = row["address"]

                # =================================================
                # NEVER SEND THE SAME CA TWICE
                # =================================================

                already_sent = con.execute(
                    """
                    SELECT 1
                    FROM telegram_sent
                    WHERE address = ?
                    LIMIT 1
                    """,
                    (address,),
                ).fetchone()

                if already_sent:

                    print(
                        f"[SKIP] Already sent "
                        f"{address[:12]}..."
                    )

                    last_id = max(
                        last_id,
                        event_id
                    )

                    continue

                # =================================================
                # CREATE MESSAGE
                # =================================================

                message = make_alert(row)

                print(
                    f"[NEW TREND] "
                    f"#{row['rank']} "
                    f"{address[:12]}..."
                )

                # =================================================
                # SEND TELEGRAM
                # =================================================

                success = send_telegram(message)

                if success:

                    # =============================================
                    # RECORD SUCCESS
                    # =============================================

                    con.execute(
                        """
                        INSERT INTO telegram_sent
                        (
                            address,
                            event_id,
                            sent_at
                        )
                        VALUES(
                            ?,
                            ?,
                            datetime('now')
                        )
                        """,
                        (
                            address,
                            event_id,
                        ),
                    )

                    con.commit()

                    print(
                        f"[SENT] {address}"
                    )

                    last_id = max(
                        last_id,
                        event_id
                    )

                else:

                    # =============================================
                    # TELEGRAM FAILED
                    #
                    # Do not mark as sent.
                    # It will retry on the next cycle.
                    # =============================================

                    print(
                        "[NOT SENT] "
                        "Will retry."
                    )

                    break

            time.sleep(POLL)

    except KeyboardInterrupt:

        print()
        print("Stopped.")

    finally:

        con.close()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()