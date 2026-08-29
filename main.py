import sqlite3
import time
import re
import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta


# ============================================================
# CONFIG
# ============================================================

DB = Path("trend_research_v2.db")

POLL = 120                 # 2 minutes
TRACK_HOURS = 3            # track each CA for 3 hours
TREND_URL = "https://dexscreener.com/5m"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0 Safari/537.36"
)


# ============================================================
# DATABASE
# ============================================================

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

con.executescript("""
CREATE TABLE IF NOT EXISTS tokens(
    address TEXT PRIMARY KEY,

    first_trend TEXT,
    first_rank INTEGER,
    first_mc REAL,
    first_price REAL,

    disappeared TEXT,

    peak_mc REAL,
    peak_price REAL,

    low_after REAL,

    second_peak REAL,

    trend_returned INTEGER DEFAULT 0,

    track_until TEXT
);


CREATE TABLE IF NOT EXISTS snapshots(
    id INTEGER PRIMARY KEY,
    address TEXT,
    t TEXT,
    source TEXT,

    trending INTEGER,
    rank INTEGER,

    mc REAL,
    price REAL,
    liquidity REAL,
    vol5 REAL,
    buys INTEGER,
    sells INTEGER
);


CREATE TABLE IF NOT EXISTS fetch_log(
    id INTEGER PRIMARY KEY,
    t TEXT,
    ok INTEGER,
    count INTEGER,
    error TEXT
);


/*
    Every valid Trend observation.

    This is deliberately separate from snapshots so we can
    study exactly how Trend behavior changes over time.
*/
CREATE TABLE IF NOT EXISTS trend_events(
    id INTEGER PRIMARY KEY,

    address TEXT,
    t TEXT,

    event_type TEXT,

    rank INTEGER,

    mc REAL,
    price REAL,

    liquidity REAL,
    vol5 REAL,

    buys INTEGER,
    sells INTEGER
);


/*
    One row for every time we successfully observe a token
    during its 3-hour research window.
*/
CREATE TABLE IF NOT EXISTS research_events(
    id INTEGER PRIMARY KEY,

    address TEXT,
    t TEXT,

    minutes_from_first REAL,

    trending INTEGER,
    rank INTEGER,

    mc REAL,
    price REAL,
    liquidity REAL,
    vol5 REAL,

    buys INTEGER,
    sells INTEGER
);
""")


# ============================================================
# DATABASE MIGRATION
# ============================================================

def add_column_if_missing(table, column, definition):
    cols = {
        row["name"]
        for row in con.execute(f"PRAGMA table_info({table})")
    }

    if column not in cols:
        con.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )
        con.commit()


# Existing DBs already have the original columns.
# Add only the new field needed by the 3-hour system.
add_column_if_missing(
    "tokens",
    "track_until",
    "TEXT"
)

con.commit()


# ============================================================
# HTTP SESSION
# ============================================================

s = requests.Session()

s.headers.update({
    "User-Agent": UA,
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://dexscreener.com/",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
})


# ============================================================
# HELPERS
# ============================================================

def now():
    return datetime.now(timezone.utc).isoformat()


def parse_time(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def num(d, *keys):

    if not isinstance(d, dict):
        return None

    for k in keys:

        v = d.get(k)

        if isinstance(v, dict):
            v = (
                v.get("value")
                or v.get("usd")
                or v.get("amount")
            )

        try:
            if v is not None:
                return float(v)
        except Exception:
            pass

    return None


def walk(x):

    if isinstance(x, dict):

        yield x

        for v in x.values():
            yield from walk(v)

    elif isinstance(x, list):

        for v in x:
            yield from walk(v)


# ============================================================
# TREND FETCH
# ============================================================

def trending():

    last_error = ""

    for attempt in range(4):

        try:

            if attempt:
                time.sleep(2 ** attempt)

            r = s.get(
                TREND_URL,
                timeout=20
            )

            if r.status_code != 200:

                last_error = f"HTTP {r.status_code}"

                continue

            html = r.text

            found = {}

            # ------------------------------------------------
            # JSON embedded inside DexScreener page
            # ------------------------------------------------

            patterns = [
                r'<script[^>]*type="application/json"[^>]*>'
                r'(.*?)</script>',

                r'<script[^>]*id="__NEXT_DATA__"[^>]*>'
                r'(.*?)</script>'
            ]

            for pat in patterns:

                for m in re.finditer(
                    pat,
                    html,
                    re.S | re.I
                ):

                    try:
                        blob = json.loads(m.group(1))
                    except Exception:
                        continue

                    for d in walk(blob):

                        if not isinstance(d, dict):
                            continue

                        address = (
                            d.get("address")
                            or d.get("tokenAddress")
                            or d.get("baseTokenAddress")
                        )

                        for k in (
                            "token",
                            "baseToken"
                        ):

                            if isinstance(
                                d.get(k),
                                dict
                            ):

                                address = (
                                    address
                                    or d[k].get("address")
                                )

                        if not address:
                            continue

                        chain = (
                            d.get("chainId")
                            or d.get("chain")
                        )

                        if isinstance(chain, dict):
                            chain = chain.get("id")

                        if chain:

                            if str(chain).lower() not in (
                                "solana",
                                "sol"
                            ):
                                continue

                        found[address] = {
                            "rank": d.get("rank"),

                            "mc": num(
                                d,
                                "marketCap",
                                "fdv"
                            ),

                            "price": num(
                                d,
                                "priceUsd",
                                "price"
                            ),

                            "liq": num(
                                d,
                                "liquidityUsd"
                            ),

                            "vol": num(
                                d,
                                "volume5m",
                                "volume_5m"
                            ),

                            "buys": num(
                                d,
                                "buys5m",
                                "buys_5m"
                            ),

                            "sells": num(
                                d,
                                "sells5m",
                                "sells_5m"
                            )
                        }

            # ------------------------------------------------
            # Fallback: find Solana addresses in HTML
            # ------------------------------------------------

            if not found:

                for m in re.finditer(
                    r'/solana/([A-Za-z0-9]{20,50})',
                    html
                ):

                    found[m.group(1)] = {
                        "rank": None,
                        "mc": None,
                        "price": None,
                        "liq": None,
                        "vol": None,
                        "buys": None,
                        "sells": None
                    }

            if not found:
                raise RuntimeError(
                    "HTTP 200 but no tokens parsed"
                )

            # ------------------------------------------------
            # Ensure every token has a rank
            # ------------------------------------------------

            for i, x in enumerate(
                found.values(),
                1
            ):

                if not x["rank"]:
                    x["rank"] = i

            return found

        except Exception as e:

            last_error = str(e)

    raise RuntimeError(last_error)


# ============================================================
# DEX PAIR DATA
# ============================================================

def pair(address):

    r = s.get(
        f"https://api.dexscreener.com/latest/dex/tokens/{address}",
        timeout=20
    )

    r.raise_for_status()

    ps = [
        p
        for p in (r.json().get("pairs") or [])
        if str(
            p.get("chainId", "")
        ).lower() == "solana"
    ]

    if not ps:
        return None

    # Use highest-liquidity Solana pair
    ps.sort(
        key=lambda p: float(
            (p.get("liquidity") or {}).get("usd")
            or 0
        ),
        reverse=True
    )

    p = ps[0]

    tx = p.get("txns") or {}
    m = tx.get("m5") or {}

    return {

        "mc": num(
            p,
            "marketCap",
            "fdv"
        ),

        "price": num(
            p,
            "priceUsd"
        ),

        "liq": num(
            p.get("liquidity") or {},
            "usd"
        ),

        "vol": num(
            p.get("volume") or {},
            "m5"
        ),

        "buys": m.get("buys") or 0,

        "sells": m.get("sells") or 0
    }


# ============================================================
# SNAPSHOT
# ============================================================

def save_snapshot(
    address,
    source,
    trending_flag,
    x,
    rank=None
):

    con.execute(
        """
        INSERT INTO snapshots
        (
            address,
            t,
            source,
            trending,
            rank,
            mc,
            price,
            liquidity,
            vol5,
            buys,
            sells
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            address,
            now(),
            source,
            int(trending_flag),
            rank,
            x.get("mc"),
            x.get("price"),
            x.get("liq"),
            x.get("vol"),
            x.get("buys"),
            x.get("sells")
        )
    )


# ============================================================
# RESEARCH EVENT
# ============================================================

def save_research_event(
    address,
    t,
    trending_flag,
    rank,
    x
):

    row = con.execute(
        """
        SELECT first_trend
        FROM tokens
        WHERE address=?
        """,
        (address,)
    ).fetchone()

    if not row:
        return

    first = parse_time(
        row["first_trend"]
    )

    current = parse_time(t)

    if not first or not current:
        return

    minutes = (
        current - first
    ).total_seconds() / 60.0

    con.execute(
        """
        INSERT INTO research_events
        (
            address,
            t,
            minutes_from_first,
            trending,
            rank,
            mc,
            price,
            liquidity,
            vol5,
            buys,
            sells
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            address,
            t,
            minutes,
            int(trending_flag),
            rank,
            x.get("mc"),
            x.get("price"),
            x.get("liq"),
            x.get("vol"),
            x.get("buys"),
            x.get("sells")
        )
    )


# ============================================================
# TREND EVENT
# ============================================================

def save_trend_event(
    address,
    t,
    rank,
    x,
    event_type
):

    con.execute(
        """
        INSERT INTO trend_events
        (
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
        )
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            address,
            t,
            event_type,
            rank,
            x.get("mc"),
            x.get("price"),
            x.get("liq"),
            x.get("vol"),
            x.get("buys"),
            x.get("sells")
        )
    )


# ============================================================
# CREATE NEW TOKEN
# ============================================================

def create_token(address, x):

    t = now()

    track_until = (
        datetime.now(timezone.utc)
        + timedelta(hours=TRACK_HOURS)
    ).isoformat()

    con.execute(
        """
        INSERT INTO tokens
        (
            address,
            first_trend,
            first_rank,
            first_mc,
            first_price,
            peak_mc,
            peak_price,
            track_until
        )
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            address,
            t,
            x.get("rank"),
            x.get("mc"),
            x.get("price"),
            x.get("mc"),
            x.get("price"),
            track_until
        )
    )

    return t


# ============================================================
# UPDATE TOKEN FROM LIFECYCLE DATA
# ============================================================

def update_token_metrics(address):

    row = con.execute(
        """
        SELECT *
        FROM tokens
        WHERE address=?
        """,
        (address,)
    ).fetchone()

    if not row:
        return

    rows = con.execute(
        """
        SELECT *
        FROM snapshots
        WHERE address=?
          AND mc IS NOT NULL
        ORDER BY t
        """,
        (address,)
    ).fetchall()

    if not rows:
        return

    vals = [
        r["mc"]
        for r in rows
        if r["mc"] is not None
    ]

    if not vals:
        return

    peak = max(vals)

    # --------------------------------------------------------
    # First valid MC/price
    # --------------------------------------------------------

    first_valid = rows[0]

    first_mc = row["first_mc"]
    first_price = row["first_price"]

    if first_mc is None:
        first_mc = first_valid["mc"]

    if first_price is None:
        first_price = first_valid["price"]

    # --------------------------------------------------------
    # Peak price
    # --------------------------------------------------------

    peak_row = max(
        rows,
        key=lambda r: (
            r["mc"]
            if r["mc"] is not None
            else 0
        )
    )

    peak_price = peak_row["price"]

    # --------------------------------------------------------
    # After disappearance
    # --------------------------------------------------------

    low_after = None
    second_peak = None

    if row["disappeared"]:

        after = [
            r
            for r in rows
            if r["t"] >= row["disappeared"]
        ]

        if after:

            after_vals = [
                r["mc"]
                for r in after
                if r["mc"] is not None
            ]

            if after_vals:

                low_after = min(
                    after_vals
                )

                # Find the first occurrence of the low
                low_index = None

                for i, r in enumerate(after):

                    if (
                        r["mc"] is not None
                        and r["mc"] == low_after
                    ):

                        low_index = i
                        break

                if low_index is not None:

                    recovery = [
                        r["mc"]
                        for r in after[low_index:]
                        if r["mc"] is not None
                    ]

                    if recovery:
                        second_peak = max(
                            recovery
                        )

    con.execute(
        """
        UPDATE tokens
        SET
            first_mc=?,
            first_price=?,
            peak_mc=?,
            peak_price=?,
            low_after=?,
            second_peak=?
        WHERE address=?
        """,
        (
            first_mc,
            first_price,
            peak,
            peak_price,
            low_after,
            second_peak,
            address
        )
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=== TREND RESEARCH V2 — 3H EVIDENCE MODE ===")
    print(
        "FIRST 🔥 → EVERY TREND MARK → RANK CHANGE → "
        "GONE → 3H FOLLOW → PULLBACK → SECOND PUMP"
    )
    print(
        f"Database: {DB.resolve()}"
    )
    print(
        f"Poll: {POLL}s"
    )
    print(
        f"Tracking window: {TRACK_HOURS} hours per CA"
    )
    print(
        "403/timeouts = INVALID SNAPSHOT"
    )
    print(
        "403/timeouts NEVER create disappearance."
    )
    print()

    while True:

        start = time.time()

        current_time = datetime.now(
            timezone.utc
        )

        # ====================================================
        # 1. GET CURRENT TREND
        # ====================================================

        try:

            cur = trending()

            t = now()

            old_rows = con.execute(
                """
                SELECT *
                FROM tokens
                """
            ).fetchall()

            old = {
                r["address"]
                for r in old_rows
            }

            previous_trend = {}

            for r in con.execute(
                """
                SELECT address, rank
                FROM trend_events
                WHERE id IN (
                    SELECT MAX(id)
                    FROM trend_events
                    GROUP BY address
                )
                """
            ).fetchall():

                previous_trend[
                    r["address"]
                ] = r["rank"]

            # ------------------------------------------------
            # Log successful fetch
            # ------------------------------------------------

            con.execute(
                """
                INSERT INTO fetch_log
                (
                    t,
                    ok,
                    count,
                    error
                )
                VALUES(?,?,?,?)
                """,
                (
                    t,
                    1,
                    len(cur),
                    None
                )
            )

            print(
                f"[{t}] TREND OK: "
                f"{len(cur)} | "
                f"tracked={len(old)}"
            )

            # =================================================
            # 2. PROCESS EVERY TOKEN CURRENTLY IN TREND
            # =================================================

            for address, x in cur.items():

                is_new = address not in old

                if is_new:

                    create_token(
                        address,
                        x
                    )

                    print(
                        f"  NEW 🔥 "
                        f"#{x['rank']} "
                        f"{address[:10]}..."
                    )

                    event_type = "ENTER"

                else:

                    old_rank = previous_trend.get(
                        address
                    )

                    if old_rank is None:

                        event_type = "ENTER"

                    elif old_rank != x["rank"]:

                        event_type = "RANK_CHANGE"

                        print(
                            f"  RANK 🔥 "
                            f"{address[:10]}... "
                            f"#{old_rank} → #{x['rank']}"
                        )

                    else:

                        event_type = "STILL"

                # ------------------------------------------------
                # Every valid Trend observation gets recorded.
                # ------------------------------------------------

                save_snapshot(
                    address,
                    "trending",
                    True,
                    x,
                    x["rank"]
                )

                save_trend_event(
                    address,
                    t,
                    x["rank"],
                    x,
                    event_type
                )

                save_research_event(
                    address,
                    t,
                    True,
                    x["rank"],
                    x
                )

            # =================================================
            # 3. DISAPPEARANCE
            # =================================================

            for r in old_rows:

                address = r["address"]

                if address not in cur:

                    if r["disappeared"] is None:

                        con.execute(
                            """
                            UPDATE tokens
                            SET disappeared=?
                            WHERE address=?
                            """,
                            (
                                t,
                                address
                            )
                        )

                        print(
                            f"  GONE 🔥 "
                            f"{address[:10]}..."
                        )

                        # Record explicit EXIT event.
                        save_trend_event(
                            address,
                            t,
                            None,
                            {
                                "mc": None,
                                "price": None,
                                "liq": None,
                                "vol": None,
                                "buys": None,
                                "sells": None
                            },
                            "EXIT"
                        )

            con.commit()

        except Exception as e:

            # =================================================
            # INVALID FETCH
            # =================================================

            con.execute(
                """
                INSERT INTO fetch_log
                (
                    t,
                    ok,
                    count,
                    error
                )
                VALUES(?,?,?,?)
                """,
                (
                    now(),
                    0,
                    0,
                    str(e)
                )
            )

            con.commit()

            cur = None

            print(
                f"[TREND ERROR] {e}"
            )

            print(
                "  VALID SNAPSHOT: NO — "
                "no disappearance recorded."
            )

        # ====================================================
        # 4. LIFECYCLE TRACKING
        # ====================================================

        rows = con.execute(
            """
            SELECT *
            FROM tokens
            ORDER BY first_trend
            """
        ).fetchall()

        for row in rows:

            address = row["address"]

            first = parse_time(
                row["first_trend"]
            )

            if not first:
                continue

            # ------------------------------------------------
            # Track exactly 3 hours from first Trend.
            # ------------------------------------------------

            track_until = parse_time(
                row["track_until"]
            )

            if track_until is None:

                track_until = (
                    first
                    + timedelta(
                        hours=TRACK_HOURS
                    )
                )

                con.execute(
                    """
                    UPDATE tokens
                    SET track_until=?
                    WHERE address=?
                    """,
                    (
                        track_until.isoformat(),
                        address
                    )
                )

            # ------------------------------------------------
            # Only fetch lifecycle data while inside
            # the token's 3-hour research window.
            # ------------------------------------------------

            if current_time > track_until:
                continue

            try:

                x = pair(address)

                if not x:
                    continue

                t = now()

                is_trending = (
                    address in (cur or {})
                )

                current_rank = None

                if is_trending:
                    current_rank = (
                        cur[address]["rank"]
                    )

                save_snapshot(
                    address,
                    "lifecycle",
                    is_trending,
                    x,
                    current_rank
                )

                save_research_event(
                    address,
                    t,
                    is_trending,
                    current_rank,
                    x
                )

                # ------------------------------------------------
                # If first MC was unavailable from Trend page,
                # lifecycle API can fill it.
                # ------------------------------------------------

                if row["first_mc"] is None:

                    con.execute(
                        """
                        UPDATE tokens
                        SET
                            first_mc=?,
                            first_price=?
                        WHERE address=?
                        AND first_mc IS NULL
                        """,
                        (
                            x.get("mc"),
                            x.get("price"),
                            address
                        )
                    )

            except Exception:
                # One bad token must never stop research.
                pass

        con.commit()

        # ====================================================
        # 5. UPDATE RESEARCH METRICS
        # ====================================================

        for row in con.execute(
            """
            SELECT address
            FROM tokens
            """
        ).fetchall():

            update_token_metrics(
                row["address"]
            )

        con.commit()

        # ====================================================
        # 6. STATUS
        # ====================================================

        total = con.execute(
            """
            SELECT COUNT(*)
            FROM tokens
            """
        ).fetchone()[0]

        gone = con.execute(
            """
            SELECT COUNT(*)
            FROM tokens
            WHERE disappeared IS NOT NULL
            """
        ).fetchone()[0]

        active_3h = con.execute(
            """
            SELECT COUNT(*)
            FROM tokens
            WHERE track_until IS NOT NULL
              AND track_until > ?
            """,
            (
                current_time.isoformat(),
            )
        ).fetchone()[0]

        trend_events = con.execute(
            """
            SELECT COUNT(*)
            FROM trend_events
            """
        ).fetchone()[0]

        research_events = con.execute(
            """
            SELECT COUNT(*)
            FROM research_events
            """
        ).fetchone()[0]

        print(
            f"  STATUS | "
            f"tokens={total} | "
            f"gone={gone} | "
            f"3h_active={active_3h} | "
            f"trend_events={trend_events} | "
            f"research_events={research_events}"
        )

        # ====================================================
        # 7. WAIT
        # ====================================================

        elapsed = (
            time.time() - start
        )

        time.sleep(
            max(
                1,
                POLL - elapsed
            )
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print("Stopped.")