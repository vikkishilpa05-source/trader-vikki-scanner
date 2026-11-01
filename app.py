import os, secrets, hashlib, time, threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
import requests
from flask import Flask, redirect, request, session, jsonify, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', PREFERRED_URL_SCHEME='https')
AUTH_URL='https://api-t1.fyers.in/api/v3/generate-authcode'
TOKEN_URL='https://api-t1.fyers.in/api/v3/validate-authcode'
DATA_URL='https://api-t1.fyers.in/data'
MASTER_URL='https://public.fyers.in/sym_details/NSE_FO_sym_master.json'
IST=ZoneInfo('Asia/Kolkata')
access_token=None
master_cache={'at':0,'data':None}
last_scan={'at':0,'data':None}
scan_lock=threading.Lock()
HTTP=requests.Session()

# Sector map is intentionally explicit: unknown mappings are not silently assigned.
SECTOR_MAP={
 'AARTIIND':'NIFTY PHARMA','ALKEM':'NIFTY PHARMA','APOLLOHOSP':'NIFTY HEALTHCARE','AUROPHARMA':'NIFTY PHARMA','BIOCON':'NIFTY PHARMA','CIPLA':'NIFTY PHARMA','DIVISLAB':'NIFTY PHARMA','DRREDDY':'NIFTY PHARMA','GLENMARK':'NIFTY PHARMA','LUPIN':'NIFTY PHARMA','MANKIND':'NIFTY PHARMA','SUNPHARMA':'NIFTY PHARMA','TORNTPHARM':'NIFTY PHARMA',
 'ASIANPAINT':'NIFTY CONSUMER DURABLES','BERGEPAINT':'NIFTY CONSUMER DURABLES','DIXON':'NIFTY CONSUMER DURABLES','HAVELLS':'NIFTY CONSUMER DURABLES','VOLTAS':'NIFTY CONSUMER DURABLES','TITAN':'NIFTY CONSUMER DURABLES',
 'BAJFINANCE':'NIFTY FIN SERVICE','BAJAJFINSV':'NIFTY FIN SERVICE','HDFCBANK':'NIFTY BANK','ICICIBANK':'NIFTY BANK','KOTAKBANK':'NIFTY BANK','AXISBANK':'NIFTY BANK','SBIN':'NIFTY BANK','INDUSINDBK':'NIFTY BANK','BANKBARODA':'NIFTY PSU BANK','PNB':'NIFTY PSU BANK','CANBK':'NIFTY PSU BANK','IDFCFIRSTB':'NIFTY BANK','FEDERALBNK':'NIFTY BANK',
 'INFY':'NIFTY IT','TCS':'NIFTY IT','WIPRO':'NIFTY IT','HCLTECH':'NIFTY IT','TECHM':'NIFTY IT','LTIM':'NIFTY IT','PERSISTENT':'NIFTY IT','COFORGE':'NIFTY IT','MPHASIS':'NIFTY IT',
 'MARUTI':'NIFTY AUTO','TATAMOTORS':'NIFTY AUTO','M&M':'NIFTY AUTO','HEROMOTOCO':'NIFTY AUTO','EICHERMOT':'NIFTY AUTO','BAJAJ-AUTO':'NIFTY AUTO','TVSMOTOR':'NIFTY AUTO','ASHOKLEY':'NIFTY AUTO',
 'TATASTEEL':'NIFTY METAL','JSWSTEEL':'NIFTY METAL','HINDALCO':'NIFTY METAL','VEDL':'NIFTY METAL','JINDALSTEL':'NIFTY METAL','SAIL':'NIFTY METAL','NMDC':'NIFTY METAL',
 'RELIANCE':'NIFTY ENERGY','ONGC':'NIFTY ENERGY','NTPC':'NIFTY ENERGY','POWERGRID':'NIFTY ENERGY','BPCL':'NIFTY ENERGY','IOC':'NIFTY ENERGY','GAIL':'NIFTY ENERGY','COALINDIA':'NIFTY ENERGY',
 'ITC':'NIFTY FMCG','HINDUNILVR':'NIFTY FMCG','BRITANNIA':'NIFTY FMCG','DABUR':'NIFTY FMCG','GODREJCP':'NIFTY FMCG','MARICO':'NIFTY FMCG','TATACONSUM':'NIFTY FMCG','UNITDSPR':'NIFTY FMCG',
 'DLF':'NIFTY REALTY','GODREJPROP':'NIFTY REALTY','OBEROIRLTY':'NIFTY REALTY','PRESTIGE':'NIFTY REALTY','PHOENIXLTD':'NIFTY REALTY',
 'LT':'NIFTY INFRA','ADANIPORTS':'NIFTY INFRA','ULTRACEMCO':'NIFTY INFRA','GRASIM':'NIFTY INFRA','ACC':'NIFTY INFRA','AMBUJACEM':'NIFTY INFRA'
}
SECTOR_TICKERS={'NIFTY BANK':'NSE:NIFTYBANK-INDEX','NIFTY IT':'NSE:NIFTYIT-INDEX','NIFTY AUTO':'NSE:NIFTYAUTO-INDEX','NIFTY PHARMA':'NSE:NIFTYPHARMA-INDEX','NIFTY METAL':'NSE:NIFTYMETAL-INDEX','NIFTY ENERGY':'NSE:NIFTYENERGY-INDEX','NIFTY FMCG':'NSE:NIFTYFMCG-INDEX','NIFTY REALTY':'NSE:NIFTYREALTY-INDEX','NIFTY FIN SERVICE':'NSE:FINNIFTY-INDEX'}

PAGE='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trader Vikki Scanner</title><style>
*{box-sizing:border-box}body{margin:0;background:#fffbea;color:#172554;font-family:Arial,sans-serif}.wrap{max-width:1050px;margin:auto;padding:16px}.head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.brand{font-size:26px;font-weight:800;color:#1746a2}.sub{color:#64748b;font-size:13px;margin-top:4px}.btn{border:0;border-radius:9px;background:#1746a2;color:white;padding:12px 16px;font-weight:700;font-size:15px}.btn:disabled{opacity:.55}.status{background:#fff;border-radius:12px;padding:12px;margin:14px 0;box-shadow:0 2px 10px #0001}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.panel{background:white;border-radius:14px;padding:14px;box-shadow:0 2px 10px #0001;min-width:0}.panel h2{font-size:19px;margin:0 0 10px}.bull{color:#087443}.bear{color:#b42318}.row{border-top:1px solid #e2e8f0;padding:10px 0;font-size:13px}.muted{color:#64748b}.pill{display:inline-block;padding:3px 7px;border-radius:20px;background:#eef2ff;margin:2px}.error{color:#b42318}.small{font-size:12px;color:#64748b}@media(max-width:650px){.grid{grid-template-columns:1fr}.brand{font-size:23px}}
</style></head><body><div class="wrap"><div class="head"><div><div class="brand">Trader Vikki Scanner</div><div class="sub">NSE F&O • 3-minute strategy • Market-data only</div></div><div>{% if connected %}<button class="btn" id="scanBtn" onclick="runScan()">Scan now</button>{% else %}<a href="/login"><button class="btn">Connect FYERS</button></a>{% endif %}</div></div>
<div class="status" id="status">{% if connected %}FYERS connected for this server session. Press Scan now to run a limited first-pass scan.{% else %}Connect your FYERS account to begin.{% endif %}</div>
<div class="small">Strategy: positive futures OI change; completed 3-minute close beyond previous-day high/low; 1%–2% move; volume ranking; sector confirmation. No orders are placed.</div>
<div class="grid" style="margin-top:14px"><section class="panel"><h2 class="bull">🟢 Live bullish stocks</h2><div id="bull"><span class="muted">Not scanned yet.</span></div></section><section class="panel"><h2 class="bear">🔴 Live bearish stocks</h2><div id="bear"><span class="muted">Not scanned yet.</span></div></section></div>
<div class="status small" id="meta">Scanner status will appear here.</div></div><script>
async function runScan(){let b=document.getElementById('scanBtn'),s=document.getElementById('status');b.disabled=true;b.textContent='Scanning…';s.textContent='Fetching F&O symbols and market data. This first pass may take a little time.';try{let r=await fetch('/api/scan');let d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Scan failed');render('bull',d.bullish);render('bear',d.bearish);s.textContent=d.message;document.getElementById('meta').textContent=`Universe: ${d.universe_count} F&O stocks • Quote-qualified: ${d.movers_checked} • Detailed checks: ${d.detailed_checked} • Updated: ${d.updated_at} • ${d.coverage_note}`;}catch(e){s.textContent='Scan error: '+e.message;}finally{b.disabled=false;b.textContent='Scan now';}}
function render(id,rows){let el=document.getElementById(id);if(!rows||!rows.length){el.innerHTML='<span class="muted">No stocks matched all conditions in this scan.</span>';return;}el.innerHTML=rows.map(x=>`<div class="row"><b>${x.symbol}</b> <span class="pill">${x.change_pct.toFixed(2)}%</span><br><span class="muted">LTP ₹${x.ltp} • Vol ${Number(x.volume).toLocaleString('en-IN')} • OI Δ ${Number(x.oi_change_pct).toFixed(2)}%</span><br><span class="small">${x.sector} (${Number(x.sector_index_change_pct||0).toFixed(2)}%) • ${x.signal}</span></div>`).join('');}
</script></body></html>'''

def settings():
 return {k:os.environ.get(k,'').strip() for k in ('FYERS_APP_ID','FYERS_APP_SECRET','FYERS_REDIRECT_URI')}
def missing(): return [k for k,v in settings().items() if not v]
def auth_headers(): return {'Authorization':f"{settings()['FYERS_APP_ID']}:{access_token}"}
def fyers_get(path,params=None):
 r=HTTP.get(DATA_URL+path,params=params,headers=auth_headers(),timeout=20)
 try: d=r.json()
 except Exception: d={'message':'Non-JSON response from FYERS'}
 if r.status_code!=200 or d.get('s')!='ok':
  msg=d.get('message') or f'FYERS HTTP {r.status_code}'
  raise RuntimeError(f'{msg} (HTTP {r.status_code})')
 return d

def load_futures():
 now=time.time()
 if master_cache['data'] is not None and now-master_cache['at']<21600: return master_cache['data']
 r=HTTP.get(MASTER_URL,timeout=25); r.raise_for_status(); raw=r.json(); today=datetime.now(IST).date()
 by_underlying={}
 for ticker,v in raw.items():
  if v.get('exInstType')!=13 or v.get('optType')!='XX' or v.get('tradeStatus',1)!=1: continue
  under=(v.get('underSym') or '').strip().upper()
  if not under: continue
  try: exp=datetime.fromtimestamp(int(v.get('expiryDate',0)),IST).date()
  except Exception: continue
  if exp<today: continue
  rec={'symbol':v.get('symTicker') or ticker,'expiry':exp,'underlying':under}
  if under not in by_underlying or exp<by_underlying[under]['expiry']: by_underlying[under]=rec
 master_cache.update(at=now,data=by_underlying)
 return by_underlying

def quote_chunks(symbols):
 out={}
 for i in range(0,len(symbols),50):
  d=fyers_get('/quotes',{'symbols':','.join(symbols[i:i+50])})
  for item in d.get('d',[]):
   if item.get('s')=='ok': out[item.get('n')]=item.get('v',{})
  if i+50<len(symbols): time.sleep(.25)
 return out

def history(symbol,resolution,days=7,oi=False):
 end=datetime.now(IST).date(); start=end-timedelta(days=days)
 p={'symbol':symbol,'resolution':resolution,'date_format':'1','range_from':start.isoformat(),'range_to':end.isoformat(),'cont_flag':'1'}
 if oi:p['oi_flag']='1'
 return fyers_get('/history',p).get('candles',[])

def ist_day(epoch): return datetime.fromtimestamp(int(epoch),IST).date()
def daily_levels(candles):
 rows=[c for c in candles if len(c)>=6]
 if len(rows)<2:return None
 today=datetime.now(IST).date()
 prev=[c for c in rows if ist_day(c[0])<today]
 if not prev: prev=rows[:-1]
 if not prev:return None
 p=prev[-1]
 return {'high':float(p[2]),'low':float(p[3]),'close':float(p[4])}
def oi_change(candles):
 rows=[c for c in candles if len(c)>=7 and c[6] is not None]
 if not rows:return None
 today=datetime.now(IST).date()
 todays=[c for c in rows if ist_day(c[0])==today]
 prev=[c for c in rows if ist_day(c[0])<today]
 if not todays or not prev:return None
 old=float(prev[-1][6]); cur=float(todays[-1][6])
 if old<=0:return None
 return (cur-old)/old*100

def last_completed_3m(candles):
 rows=[c for c in candles if len(c)>=6]
 if not rows:return None
 now=datetime.now(IST)
 # Exclude the currently forming 3-minute candle using its start timestamp.
 completed=[c for c in rows if datetime.fromtimestamp(int(c[0]),IST)+timedelta(minutes=3)<=now]
 return completed[-1] if completed else None

def scan_now():
 futures=load_futures()
 if not futures: raise RuntimeError('FYERS NSE F&O symbol master returned no active stock futures.')
 underlyings=sorted(futures)
 eq_symbols=[f'NSE:{s}-EQ' for s in underlyings]
 quotes=quote_chunks(eq_symbols)
 movers=[]
 for u in underlyings:
  q=quotes.get(f'NSE:{u}-EQ')
  if not q: continue
  try: ch=float(q.get('chp')); ltp=float(q.get('lp')); vol=int(q.get('volume') or 0)
  except Exception: continue
  if 1.0<=ch<=2.0 or -2.0<=ch<=-1.0:
   if u in SECTOR_MAP: movers.append({'underlying':u,'change_pct':ch,'ltp':ltp,'volume':vol,'sector':SECTOR_MAP[u]})
 # Determine the leading sector from live sector-index quotes before selecting stocks.
 sector_quote_map=quote_chunks(list(SECTOR_TICKERS.values()))
 sector_moves={}
 for sector,ticker in SECTOR_TICKERS.items():
  q=sector_quote_map.get(ticker)
  if q is not None:
   try: sector_moves[sector]=float(q.get('chp'))
   except Exception: pass
 leading_bull=max(sector_moves,key=sector_moves.get) if sector_moves else None
 leading_bear=min(sector_moves,key=sector_moves.get) if sector_moves else None
 movers.sort(key=lambda x:x['volume'],reverse=True)
 # API budget protection: detailed 3m/OI/PDH checks on the highest-volume 8 movers in the leading sectors.
 cap=max(1,min(int(os.environ.get('MAX_DETAIL_SCAN','8')),15))
 eligible=[x for x in movers if (x['change_pct']>0 and x['sector']==leading_bull and sector_moves.get(x['sector'],0)>0) or (x['change_pct']<0 and x['sector']==leading_bear and sector_moves.get(x['sector'],0)<0)]
 candidates=eligible[:cap]
 bullish=[];bearish=[];checked=0;errors=[]
 for x in candidates:
  u=x['underlying']; fut=futures[u]['symbol']; eq=f'NSE:{u}-EQ'
  try:
   pd=history(eq,'D',days=10,oi=False); levels=daily_levels(pd)
   spot3=history(eq,'3',days=5,oi=False); candle=last_completed_3m(spot3)
   fut3=history(fut,'3',days=5,oi=True); oi_pct=oi_change(fut3)
   if not levels or not candle or oi_pct is None: continue
   checked+=1; close=float(candle[4])
   base={'symbol':u,'change_pct':x['change_pct'],'ltp':round(x['ltp'],2),'volume':x['volume'],'oi_change_pct':oi_pct,'sector':x['sector']}
   # Futures price direction distinguishes long buildup from short buildup while OI must rise in both.
   futc=last_completed_3m(fut3)
   if not futc: continue
   f_open=float(futc[1]); f_close=float(futc[4])
   if x['change_pct']>=1 and close>levels['high'] and oi_pct>0 and f_close>f_open and x['sector']==leading_bull:
    base['sector_index_change_pct']=sector_moves.get(x['sector']);base['signal']='PDH breakout + long buildup';bullish.append(base)
   elif x['change_pct']<=-1 and close<levels['low'] and oi_pct>0 and f_close<f_open and x['sector']==leading_bear:
    base['sector_index_change_pct']=sector_moves.get(x['sector']);base['signal']='PDL breakdown + short buildup';bearish.append(base)
  except Exception as e:
   errors.append(f'{u}: {str(e)[:90]}')
  time.sleep(0.35)
 bullish.sort(key=lambda z:z['volume'],reverse=True);bearish.sort(key=lambda z:z['volume'],reverse=True)
 return {'ok':True,'message':'Scan completed. Results include only stocks passing the available checks.','universe_count':len(futures),'movers_checked':len(movers),'detailed_checked':checked,'bullish':bullish,'bearish':bearish,'updated_at':datetime.now(IST).strftime('%d-%m-%Y %H:%M:%S IST'),'coverage_note':f'Detailed checks limited to top {cap} movers in the leading sector(s) per scan to protect FYERS API limits. Sector membership is mapped for supported symbols.','leading_bullish_sector':leading_bull,'leading_bearish_sector':leading_bear,'sector_index_changes':sector_moves,'warnings':errors[:5]}

@app.get('/')
def home(): return render_template_string(PAGE,connected=bool(access_token))
@app.get('/health')
def health(): return jsonify({'status':'ok','app':'Trader Vikki Scanner','version':'3.0'})
@app.get('/config-status')
def config_status():
 s=settings(); miss=missing();return jsonify({'app':'Trader Vikki Scanner','configured':not miss,**{k+'_present':bool(v) for k,v in s.items()},'missing':miss})
@app.get('/login')
def login():
 s=settings();miss=missing()
 if miss:return jsonify({'error':'Backend is not configured','missing':miss}),503
 state=secrets.token_urlsafe(24);session['oauth_state']=state
 p={'client_id':s['FYERS_APP_ID'],'redirect_uri':s['FYERS_REDIRECT_URI'],'response_type':'code','state':state}
 return redirect(AUTH_URL+'?'+urlencode(p))
@app.get('/login/callback')
def callback():
 global access_token
 s=settings();state=request.args.get('state','');expected=session.pop('oauth_state','');code=request.args.get('auth_code','')
 if not expected or not secrets.compare_digest(state,expected):return 'Login state verification failed. Start again from the scanner home page.',400
 if not code:return 'FYERS did not return an authorization code.',400
 digest=hashlib.sha256(f"{s['FYERS_APP_ID']}:{s['FYERS_APP_SECRET']}".encode()).hexdigest()
 try:r=HTTP.post(TOKEN_URL,json={'grant_type':'authorization_code','appIdHash':digest,'code':code},timeout=20);d=r.json()
 except Exception:return 'Could not contact FYERS to complete login.',502
 if d.get('s')!='ok' or not d.get('access_token'):return 'FYERS login failed. Check API app permissions and redirect URI.',400
 access_token=d['access_token'];return '<h2>FYERS connected successfully.</h2><p>Return to scanner dashboard.</p><a href="/">Open Scanner</a>'
@app.get('/connection-status')
def connection_status():return jsonify({'connected':bool(access_token)})
@app.get('/market-test')
def market_test():
 if not access_token:return jsonify({'ok':False,'error':'FYERS is not connected in this server session'}),401
 try:
  d=fyers_get('/quotes',{'symbols':'NSE:SBIN-EQ'});v=d.get('d',[{}])[0].get('v',{})
  return jsonify({'ok':True,'symbol':'NSE:SBIN-EQ','ltp':v.get('lp'),'change_percent':v.get('chp'),'volume':v.get('volume'),'message':'FYERS market-data API responded successfully.'})
 except Exception as e:return jsonify({'ok':False,'error':str(e)}),502
@app.get('/api/scan')
def api_scan():
 global last_scan
 if not access_token:return jsonify({'ok':False,'error':'FYERS is not connected. Return home and connect FYERS.'}),401
 if last_scan['data'] and time.time()-last_scan['at']<60:return jsonify(last_scan['data'])
 if not scan_lock.acquire(blocking=False):return jsonify({'ok':False,'error':'A scan is already running. Wait 30 seconds and refresh.'}),429
 try:
  data=scan_now();last_scan={'at':time.time(),'data':data};return jsonify(data)
 except Exception as e:return jsonify({'ok':False,'error':str(e)}),502
 finally:scan_lock.release()

if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','10000')))
