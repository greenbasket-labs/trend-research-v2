import os
import sqlite3
import time
import requests
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

DB = Path("trend_research_v2.db")

POLL = 5

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


# ============================================================
# DATABASE
# ============================================================

def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # Create the sent-alert table if it does not exist.
    con.execute("""
        CREATE TABLE IF NOT EXISTS telegram_sent(
            id INTEGER PRIMARY KEY,
            address TEXT UNIQUE,
            event_id INTEGER,
            sent_at TEXT
        )
    """)

    con.commit()
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

    rank = row["rank"]
    event_time = row["t"]

    mc = row["mc"]
    price = row["price"]
    liquidity = row["liquidity"]
    vol5 = row["vol5"]
    buys = row["buys"]
    sells = row["sells"]

    return (
        "🔥 TREND MARK\n\n"
        f"CA:\n{address}\n\n"
        f"Rank: #{rank}\n"
        f"Time: {event_time}\n\n"
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
    print("Watching: trend_events")
    print("Alert: ENTER only")
    print("Duplicate CA: NEVER send again")
    print()

    # --------------------------------------------------------
    # CHECK ENVIRONMENT VARIABLES
    # --------------------------------------------------------

    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN environment variable is missing.")
        return

    if not CHAT_ID:
        print("ERROR: CHAT_ID environment variable is missing.")
        return

    con = get_db()

    # --------------------------------------------------------
    # START FROM CURRENT END
    #
    # Existing historical ENTER events will NOT be sent.
    # Only new ENTER events created after startup are watched.
    # --------------------------------------------------------

    row = con.execute(
        """
        SELECT COALESCE(MAX(id), 0) AS max_id
        FROM trend_events
        """
    ).fetchone()

    last_id = row["max_id"]

    print(f"Starting after existing event ID: {last_id}")
    print("Ready.\n")

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

                # ------------------------------------------------
                # DUPLICATE PROTECTION
                #
                # One CA can only ever produce one Telegram alert.
                # ------------------------------------------------

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
                        event_id,
                    )

                    continue

                # ------------------------------------------------
                # CREATE MESSAGE
                # ------------------------------------------------

                message = make_alert(row)

                print(
                    f"[NEW TREND] "
                    f"#{row['rank']} "
                    f"{address[:12]}..."
                )

                # ------------------------------------------------
                # SEND
                # ------------------------------------------------

                success = send_telegram(message)

                if success:

                    # ------------------------------------------------
                    # RECORD ONLY AFTER TELEGRAM SUCCESS
                    # ------------------------------------------------

                    try:

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

                    except sqlite3.IntegrityError:

                        # Another process/retry already recorded
                        # this CA. Never send it again.
                        con.rollback()

                        print(
                            f"[SKIP] Duplicate CA "
                            f"{address[:12]}..."
                        )

                    print(
                        f"[SENT] "
                        f"{address}"
                    )

                    last_id = max(
                        last_id,
                        event_id,
                    )

                else:

                    print(
                        "[NOT SENT] "
                        "Will retry."
                    )

                    # Do not advance last_id.
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