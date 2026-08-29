import time
from config import POLL_SECONDS, TREND_URL
from db import DB
from collector import Collector

def main():
    db=DB(); c=Collector()
    print('=== TREND RESEARCH V2 ===')
    print('PRE-TREND -> TREND -> DISAPPEAR -> LIFECYCLE -> SECOND PUMP / DIE')
    print(f'Poll: {POLL_SECONDS}s')
    print('Clean database: data/trend_research_v2.db')
    while True:
        start=time.time(); current=None
        try:
            items=c.trending(TREND_URL); current={x['address']:x for x in items}
            db.log_fetch(True,len(current)); print(f'[TREND] valid={len(current)} tracked={len(db.tracked_addresses())}')
        except Exception as e:
            db.log_fetch(False,error=str(e)); print(f'[TREND ERROR] {e}'); print('  No disappearance decisions made.')
        if current is not None:
            known=set(db.tracked_addresses())
            for a,x in current.items():
                if a not in known:
                    db.add_token(a,x['rank'],x['mc'],x['price']); print(f"  NEW TREND #{x['rank']} {a[:8]}... MC={x['mc']}")
                db.add_snapshot(a,'trending',True,x['rank'],x['mc'],x['price'],x['liquidity'],x['volume_5m'],x['buys_5m'],x['sells_5m'])
            for a in known:
                if a not in current and db.get_token(a)['trend_disappeared'] is None:
                    db.mark_disappeared(a); print(f'  TREND GONE {a[:8]}...')
        for a in db.tracked_addresses():
            try:
                x=c.pair_snapshot(a)
                if x: db.add_snapshot(a,'lifecycle',a in (current or {}),None,x['mc'],x['price'],x['liquidity'],x['volume_5m'],x['buys_5m'],x['sells_5m'])
            except Exception as e: print(f'  [PAIR ERROR] {a[:8]}... {e}')
        time.sleep(max(1,POLL_SECONDS-(time.time()-start)))
if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: print('\nStopped.')
