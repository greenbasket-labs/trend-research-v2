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
                f"[TELEGRAM ERROR] "
                f"{data}"
            )

            return False

        return True

    except Exception as e:

        print(
            f"[TELEGRAM ERROR] {e}"
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

    # --------------------------------------------------------
    # CA IS IN A CODE BLOCK.
    #
    # On Telegram mobile this makes the CA very easy
    # to select/copy.
    # --------------------------------------------------------

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

    print(
        f"Database: {DB.resolve()}"
    )

    print(
        f"Poll: {POLL}s"
    )

    print()

    print(
        "Watching: trend_events"
    )

    print(
        "Alert: ENTER only"
    )

    print(
        "Duplicate CA: NEVER send again"
    )

    print()

    # --------------------------------------------------------
    # CHECK CONFIG
    # --------------------------------------------------------

    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":

        print(
            "ERROR: Put your Telegram bot token in the file."
        )

        return

    if CHAT_ID == "PUT_YOUR_CHAT_ID_HERE":

        print(
            "ERROR: Put your Telegram chat ID in the file."
        )

        return

    # --------------------------------------------------------
    # CONNECT DATABASE
    # --------------------------------------------------------

    con = get_db()

    # --------------------------------------------------------
    # VERIFY TABLES
    # --------------------------------------------------------

    tables = {
        r["name"]
        for r in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """
        ).fetchall()
    }

    if "trend_events" not in tables:

        print(
            "[ERROR] trend_events table does not exist."
        )

        con.close()

        return

    if "telegram_sent" not in tables:

        print(
            "[ERROR] telegram_sent table does not exist."
        )

        con.close()

        return

    # --------------------------------------------------------
    # START FROM CURRENT END
    #
    # Existing old ENTER events will NOT be sent.
    # Only future ENTER events are processed.
    # --------------------------------------------------------

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

    print(
        "Ready.\n"
    )

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

                # ------------------------------------------------
                # DUPLICATE PROTECTION
                #
                # If this CA was EVER successfully sent,
                # never send it again.
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
                        event_id
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

                success = send_telegram(
                    message
                )

                if success:

                    # --------------------------------------------
                    # RECORD SUCCESS BEFORE MOVING ON
                    # --------------------------------------------

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

                    print(
                        "[NOT SENT] "
                        "Will retry."
                    )

                    # --------------------------------------------
                    # DO NOT advance last_id.
                    #
                    # Telegram failed, so retry next loop.
                    # --------------------------------------------

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