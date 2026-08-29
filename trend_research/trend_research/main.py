import time
from config import POLL_SECONDS,TREND_URLS
from db import DB
from collector import TrendCollector,TrendFetchError

def run():
    db=DB(); c=TrendCollector()
    print('=== TREND RESEARCH COLLECTOR ===')
    print(f'Poll interval: {POLL_SECONDS}s')
    print('Request errors NEVER count as disappearance.\n')
    while True:
        start=time.time(); current=None
        for window,url in TREND_URLS.items():
            try:
                items=c.fetch_trending(url); current={x['address']:x for x in items}
                print(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {window}: {len(current)} tokens')
            except TrendFetchError as e: print(f'[ERROR] {window}: {e}')
            except Exception as e: print(f'[ERROR] {window}: unexpected error: {e}')
        if current is None:
            print('    VALID SNAPSHOT: NO | keeping previous state; NO disappearances recorded')
        else:
            for a,x in current.items():
                db.upsert_token(a,x['rank'],x['mc'],x['price'])
                db.add_observation(a,x['rank'],x['mc'],x['price'],x['liquidity'],x['volume_5m'],x['buys_5m'],x['sells_5m'],True)
            n=0
            for a in db.active_addresses():
                if a not in current:
                    db.add_observation(a,None,None,None,None,None,None,None,False);db.mark_disappeared(a);n+=1
            print(f'    VALID SNAPSHOT: YES | currently trending={len(current)} | tracked={len(db.rows())} | newly disappeared={n}')
        time.sleep(max(1,POLL_SECONDS-(time.time()-start)))
if __name__=='__main__':
    try:run()
    except KeyboardInterrupt:print('\nStopped.')
