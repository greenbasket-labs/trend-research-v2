import re, json, time, random, requests
from config import USER_AGENT, TIMEOUT

class TrendFetchError(Exception): pass

class TrendCollector:
    def __init__(self):
        self.s=requests.Session()
        self.s.headers.update({'User-Agent':USER_AGENT,'Accept':'text/html,application/xhtml+xml,application/json','Accept-Language':'en-US,en;q=0.9','Referer':'https://dexscreener.com/','Cache-Control':'no-cache'})
    def fetch_page(self,url):
        last=None
        for attempt in range(1,4):
            try:
                if attempt>1: time.sleep((2**(attempt-1))+random.uniform(.5,1.5))
                r=self.s.get(url,timeout=TIMEOUT,allow_redirects=True)
                if r.status_code==200: return r.text
                last=f'HTTP {r.status_code}'
                if r.status_code in (403,429,500,502,503,504): continue
                r.raise_for_status()
            except requests.RequestException as e: last=str(e)
        raise TrendFetchError(f'Could not fetch Trending after 3 attempts: {last}')
    def _blobs(self,html):
        out=[]
        for p in [r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>']:
            for m in re.finditer(p,html,re.S|re.I):
                try: out.append(json.loads(m.group(1)))
                except: pass
        return out
    def _walk(self,o):
        if isinstance(o,dict):
            yield o
            for v in o.values(): yield from self._walk(v)
        elif isinstance(o,list):
            for v in o: yield from self._walk(v)
    def _num(self,d,*keys):
        for k in keys:
            v=d.get(k)
            if isinstance(v,dict): v=v.get('value') or v.get('amount') or v.get('usd')
            try:
                if v is not None:return float(v)
            except: pass
        return None
    def _normalize(self,d):
        a=d.get('address') or d.get('tokenAddress') or d.get('baseTokenAddress')
        if isinstance(d.get('token'),dict): a=a or d['token'].get('address')
        if isinstance(d.get('baseToken'),dict): a=a or d['baseToken'].get('address')
        if not a:return None
        chain=d.get('chainId') or d.get('chain')
        if isinstance(chain,dict): chain=chain.get('id')
        if chain and str(chain).lower() not in ('solana','sol'):return None
        return {'address':a,'rank':d.get('rank'),'mc':self._num(d,'marketCap','fdv'),'price':self._num(d,'priceUsd','price'),'liquidity':self._num(d,'liquidityUsd','liquidity'),'volume_5m':self._num(d,'volume5m','volume_5m'),'buys_5m':self._num(d,'buys5m','buys_5m'),'sells_5m':self._num(d,'sells5m','sells_5m')}
    def fetch_trending(self,url):
        html=self.fetch_page(url); found={}
        for blob in self._blobs(html):
            for d in self._walk(blob):
                if not isinstance(d,dict):continue
                if not any(k in d for k in ('address','tokenAddress','baseTokenAddress','baseToken','token')):continue
                x=self._normalize(d)
                if x:found[x['address']]=x
        if not found:
            for m in re.finditer(r'/solana/([A-Za-z0-9]{20,50})',html):
                a=m.group(1);found[a]={'address':a,'rank':None,'mc':None,'price':None,'liquidity':None,'volume_5m':None,'buys_5m':None,'sells_5m':None}
        if not found:raise TrendFetchError('HTTP 200 received, but no Trending tokens were parsed.')
        items=list(found.values())
        for i,x in enumerate(items,1): x['rank']=x['rank'] or i
        return items
