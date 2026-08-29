# Trend Research

Small research collector for this hypothesis:

EARLY 🔥 TREND
→ trend disappears
→ 20–50% pullback
→ second pump >= 80% from pullback low
→ 🔥 Trending returns

## Install

PowerShell:

```powershell
cd C:\Users\DTL\Documents
mkdir trend_research
cd trend_research

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Put the files from this project into the folder.

## Run

```powershell
.\.venv\Scripts\python.exe main.py
```

Leave it running.

## Report

In another PowerShell window:

```powershell
cd C:\Users\DTL\Documents\trend_research
.\.venv\Scripts\python.exe report.py
```

## Important

This deliberately does NOT trade or alert.

It records Trending observations and tries to determine whether the observed
sequence happens frequently enough to justify further research.

DEX Screener can change its website structure. If the collector starts showing
zero tokens, the parser needs to be updated rather than silently treating zero
as "no trending tokens".
