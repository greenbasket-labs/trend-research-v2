import subprocess
import sys
import time


print("==========================================")
print("       TREND RESEARCH V2 - RENDER")
print("==========================================")
print()
print("Starting main.py...")
print("Starting Telegram alert worker...")
print()


# ============================================================
# START RESEARCH ENGINE
# ============================================================

research = subprocess.Popen(
    [
        sys.executable,
        "main.py",
    ]
)


# Give main.py a moment to create the database/tables.

time.sleep(5)


# ============================================================
# START TELEGRAM ALERT WORKER
# ============================================================

alert = subprocess.Popen(
    [
        sys.executable,
        "trend_alert.py",
    ]
)


print()
print("==========================================")
print("BOTH WORKERS STARTED")
print("==========================================")
print()


# ============================================================
# KEEP RENDER SERVICE ALIVE
# ============================================================

try:

    while True:

        research_code = research.poll()

        alert_code = alert.poll()

        # --------------------------------------------
        # If research engine dies, restart it.
        # --------------------------------------------

        if research_code is not None:

            print(
                f"[RESEARCH STOPPED] "
                f"exit={research_code}"
            )

            print(
                "[RESEARCH] Restarting..."
            )

            research = subprocess.Popen(
                [
                    sys.executable,
                    "main.py",
                ]
            )

        # --------------------------------------------
        # If Telegram worker dies, restart it.
        # --------------------------------------------

        if alert_code is not None:

            print(
                f"[ALERT STOPPED] "
                f"exit={alert_code}"
            )

            print(
                "[ALERT] Restarting..."
            )

            alert = subprocess.Popen(
                [
                    sys.executable,
                    "trend_alert.py",
                ]
            )

        time.sleep(5)

except KeyboardInterrupt:

    print()
    print("Stopping workers...")

    research.terminate()
    alert.terminate()

    research.wait()
    alert.wait()

    print("Stopped.")