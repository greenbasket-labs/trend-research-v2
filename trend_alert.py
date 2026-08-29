import sqlite3
import time
import requests
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

DB = Path("trend_research_v2.db")

POLL = 5

BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"


# ============================================================
# DATABASE
# ============================================================

def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def ensure_telegram_sent_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS telegram_sent(
            address TEXT PRIMARY KEY,
            event_id INTEGER,
            sent_at TEXT
        )
    """)
    con.commit()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(text):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
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
                f"[TELEGRAM ERROR] {data}"
            )
            return False

        return True

    except Exception as e:
        print(
            f"[TELEGRAM ERROR] {e}"
        )
        return False


# ============================================================
# ALERT FORMAT
# ============================================================

def make_alert(row):

    address = row["address"]

    rank = row["rank"]
    event_time = row["t"]

    mc = row["mc"]
    price = row["price"]
    liquidity = row["liquidity"]
    vol5 = row["vol5"]

    buys = row["buys"]
    sells = row["sells"]

    return (
        "🔥 <b>TREND MARK</b>\n"
        "\n"
        "<b>CA:</b>\n"
        f"<code>{address}</code>\n"
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
    print("TRIGGER: FIRST TREND MARK ONLY")
    print("FILTERS: NONE")
    print("WAIT: NONE")
    print("DUPLICATE CA: NEVER SEND AGAIN")
    print()

    # --------------------------------------------------------
    # CONFIG CHECK
    # --------------------------------------------------------

    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print("ERROR: Put your Telegram bot token in the file.")
        return

    if CHAT_ID == "PUT_YOUR_CHAT_ID_HERE":
        print("ERROR: Put your Telegram chat ID in the file.")
        return

    con = get_db()

    # --------------------------------------------------------
    # CHECK DATABASE
    # --------------------------------------------------------

    tables = {
        r["name"]
        for r in con.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
        """).fetchall()
    }

    if "trend_events" not in tables:
        print("[ERROR] trend_events table does not exist.")
        con.close()
        return

    # Create protection table if needed.
    ensure_telegram_sent_table(con)

    # --------------------------------------------------------
    # IMPORTANT
    #
    # Do NOT send old ENTER events when this worker starts.
    #
    # We start watching from the current end of trend_events.
    # Only NEW ENTER events created after startup are alerted.
    # --------------------------------------------------------

    row = con.execute("""
        SELECT COALESCE(MAX(id), 0) AS max_id
        FROM trend_events
    """).fetchone()

    last_id = row["max_id"]

    print(
        f"Starting after existing event ID: {last_id}"
    )

    print("Ready.\n")

    # ========================================================
    # WATCH LOOP
    # ========================================================

    try:

        while True:

            rows = con.execute("""
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
            """, (last_id,)).fetchall()

            for row in rows:

                event_id = row["id"]
                address = row["address"]

                # ------------------------------------------------
                # ONE CA = ONE TELEGRAM ALERT
                # ------------------------------------------------

                already_sent = con.execute("""
                    SELECT 1
                    FROM telegram_sent
                    WHERE address = ?
                    LIMIT 1
                """, (address,)).fetchone()

                if already_sent:

                    print(
                        f"[SKIP] Already alerted: "
                        f"{address}"
                    )

                    last_id = max(
                        last_id,
                        event_id
                    )

                    continue

                # ------------------------------------------------
                # FIRST TREND MARK
                #
                # NO FILTER
                # NO SCORE
                # NO MC CHECK
                # NO LIQUIDITY CHECK
                # NO AGE CHECK
                # NO WAIT
                # ------------------------------------------------

                message = make_alert(row)

                print()
                print(
                    f"[NEW TREND] "
                    f"#{row['rank']} "
                    f"{address}"
                )

                # ------------------------------------------------
                # SEND IMMEDIATELY
                # ------------------------------------------------

                success = send_telegram(message)

                if success:

                    # --------------------------------------------
                    # SAVE AFTER SUCCESS
                    # --------------------------------------------

                    con.execute("""
                        INSERT OR IGNORE INTO telegram_sent
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
                    """, (
                        address,
                        event_id,
                    ))

                    con.commit()

                    print(
                        f"[SENT] {address}"
                    )

                    last_id = max(
                        last_id,
                        event_id
                    )

                else:

                    print(
                        "[NOT SENT] "
                        "Telegram failed."
                    )

                    # Do not advance.
                    # It will retry.

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