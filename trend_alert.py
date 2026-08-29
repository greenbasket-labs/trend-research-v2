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

# Telegram credentials come from Render Environment Variables.
#
# Render:
# BOT_TOKEN = your Telegram bot token
# CHAT_ID   = your Telegram chat ID
#
# DO NOT put the real token directly into this file.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()


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

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=20,
        )

        if response.status_code != 200:

            print(
                f"[TELEGRAM ERROR] "
                f"HTTP {response.status_code}: "
                f"{response.text}",
                flush=True,
            )

            return False

        data = response.json()

        if not data.get("ok"):

            print(
                f"[TELEGRAM ERROR] {data}",
                flush=True,
            )

            return False

        return True

    except Exception as e:

        print(
            f"[TELEGRAM ERROR] {e}",
            flush=True,
        )

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
    print("TRIGGER: FIRST TREND MARK ONLY")
    print("FILTERS: NONE")
    print("WAIT: NONE")
    print("DUPLICATE CA: NEVER SEND AGAIN")
    print()

    # --------------------------------------------------------
    # TELEGRAM CONFIG CHECK
    # --------------------------------------------------------

    if not BOT_TOKEN:

        print(
            "ERROR: BOT_TOKEN environment variable "
            "is missing.",
            flush=True,
        )

        return

    if not CHAT_ID:

        print(
            "ERROR: CHAT_ID environment variable "
            "is missing.",
            flush=True,
        )

        return

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    con = get_db()

    try:

        # ----------------------------------------------------
        # Check required table
        # ----------------------------------------------------

        table = con.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name='trend_events'
        """).fetchone()

        if not table:

            print(
                "ERROR: trend_events table does not exist.",
                flush=True,
            )

            return

        # ----------------------------------------------------
        # Create Telegram history table if missing
        # ----------------------------------------------------

        ensure_telegram_sent_table(con)

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Start at the CURRENT end of the database.
        #
        # Old ENTER events are NOT sent.
        #
        # Only ENTER events created after this worker starts
        # are considered for Telegram.
        # ----------------------------------------------------

        row = con.execute("""
            SELECT COALESCE(MAX(id), 0) AS max_id
            FROM trend_events
        """).fetchone()

        last_id = row["max_id"]

        print(
            f"Starting after existing event ID: "
            f"{last_id}",
            flush=True,
        )

        print(
            "Ready.",
            flush=True,
        )

        print()

        # ====================================================
        # WATCH LOOP
        # ====================================================

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
                # ONE CA = ONE ALERT
                # ------------------------------------------------

                already_sent = con.execute("""
                    SELECT 1
                    FROM telegram_sent
                    WHERE address = ?
                    LIMIT 1
                """, (address,)).fetchone()

                if already_sent:

                    print(
                        f"[SKIP] Already alerted "
                        f"{address[:12]}...",
                        flush=True,
                    )

                    last_id = max(
                        last_id,
                        event_id,
                    )

                    continue

                # ------------------------------------------------
                # FIRST TREND MARK
                #
                # NO MC FILTER
                # NO LIQUIDITY FILTER
                # NO AGE FILTER
                # NO SCORE
                # NO RANK FILTER
                # NO WAIT
                #
                # ENTER = ALERT
                # ------------------------------------------------

                message = make_alert(row)

                print(
                    f"[NEW TREND] "
                    f"#{row['rank']} "
                    f"{address}",
                    flush=True,
                )

                # ------------------------------------------------
                # SEND IMMEDIATELY
                # ------------------------------------------------

                success = send_telegram(message)

                if success:

                    # --------------------------------------------
                    # Save only after successful Telegram send.
                    # --------------------------------------------

                    con.execute("""
                        INSERT OR IGNORE INTO telegram_sent
                        (
                            address,
                            event_id,
                            sent_at
                        )
                        VALUES
                        (
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
                        f"[SENT] {address}",
                        flush=True,
                    )

                    last_id = max(
                        last_id,
                        event_id,
                    )

                else:

                    print(
                        "[NOT SENT] "
                        "Telegram failed. Retrying.",
                        flush=True,
                    )

                    # Do not advance last_id.
                    #
                    # The same ENTER will be retried
                    # on the next polling cycle.

                    break

            time.sleep(POLL)

    except KeyboardInterrupt:

        print()
        print(
            "Stopped.",
            flush=True,
        )

    except Exception as e:

        print(
            f"[WORKER ERROR] {e}",
            flush=True,
        )

        raise

    finally:

        con.close()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()