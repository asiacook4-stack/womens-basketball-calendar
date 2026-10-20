"""Official-source 2026–27 women's basketball feed. Fail closed on source errors."""
import base64
import concurrent.futures
import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from icalendar import Calendar, Event, Timezone

ROOT = Path(__file__).parent
PACIFIC = ZoneInfo('America/Los_Angeles')
SOURCES = json.loads((ROOT / 'sources.json').read_text())
UTC = timezone.utc
NOW = datetime.now(UTC)
STAMP = NOW.isoformat()
ALIASES = {'connecticut':'UConn','uconn':'UConn','southern cal':'USC','southern california':'USC','usc':'USC',
           'louisiana state':'LSU','lsu':'LSU','north carolina state':'NC State','n.c. state':'NC State',
           'nc state':'NC State','cal':'California','pitt':'Pittsburgh','texas am':'Texas A&M','southern methodist university':'SMU'}
for s in SOURCES: ALIASES[s['name'].lower()] = s['name']
NATIONAL = {s['name'] for s in SOURCES} | {'Kentucky'}

def session():
    s = requests.Session()
    s.headers['User-Agent'] = 'WomensBasketballCalendar/2.0 (public official schedule subscription)'
    s.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1,
        status_forcelist=[429,500,502,503,504], allowed_methods=['GET'])))
    return s

def get(url, **kw):
    r = session().get(url, timeout=(15,45), **kw)
    r.raise_for_status()
    return r

def clean(v):
    return BeautifulSoup(str(v or ''), 'html.parser').get_text(' ', strip=True)

def canonical(name):
    name = re.sub(r'\([^)]*(?:exh|scrimmage)[^)]*\)', '', clean(name), flags=re.I)
    name = re.sub(r'^(?:#?\d+(?:/\d+)?\s+)+', '', name).strip()
    return ALIASES.get(name.lower(), name)

def iso(v, zone=None):
    d = datetime.fromisoformat(v.replace('Z', '+00:00'))
    return d.replace(tzinfo=ZoneInfo(zone)) if d.tzinfo is None else d

def nuxt(s):
    node = BeautifulSoup(s,'html.parser').find('script',id='__NUXT_DATA__')
    if not node: raise ValueError('Official schedule JSON missing')
    a = json.loads(node.string)
    def dec(i, depth=0):
        if i < 0: return None
        if depth > 35: raise ValueError('Unexpected recursive schedule data')
        x = a[i]
        if isinstance(x,dict): return {k:dec(v,depth+1) for k,v in x.items()}
        if isinstance(x,list): return [dec(v,depth+1) if isinstance(v,int) else v for v in x]
        return x
    return next(dec(i) for i,x in enumerate(a) if isinstance(x,dict) and 'games' in x and 'season' in x)

TV = re.compile(r'ESPN|ABC|ACCN|ACC Network|SEC|SECN|Peacock|NBC|CBS|FOX|FS1|FS2|BTN|B1G|BIG.TEN|UConn|TNT|truTV|Flo|MEAC|CW|SNY',re.I)

def linklabel(x):
    icon = x.get('icon') or {}
    return clean(x.get('title') or icon.get('alt') or icon.get('title'))

def broadcast_link(label, url):
    return bool(TV.search(label) or re.search(r'espn|peacock|foxsports|bigtenplus|uconnplus|flosports|paramountplus|meacsports',url,re.I))

def game(src, gid, opponent, start, tba, location, network='', links=None, exhibition=False, status='', venue='', note=''):
    opp = canonical(opponent)
    if not opp: raise ValueError('Missing opponent')
    d = iso(start, src['zone'])
    localday = d.astimezone(ZoneInfo(src['zone'])).date().isoformat()
    if not ('2026-09-01' <= localday <= '2027-04-15'): return None
    return dict(source_ids=[src['name']+':'+str(gid)], teams=[src['name'],opp], date=localday,
        start=None if tba else d.astimezone(UTC).isoformat(), location=clean(location), network=clean(network),
        watch=links or [], exhibition=exhibition, status=status, venue=venue, note=clean(note),
        sources=[src['url']], coverage='Full team schedule' if src.get('required') else 'National spotlight')

def parse_sidearm(src, text):
    d = nuxt(text)
    if d['season']['title'] != '2026-27': raise ValueError('Wrong season')
    out=[]
    for x in d['games']:
        media=x.get('media') or {}; video=media.get('video') or {}; u=video.get('url') or ''
        links=[{'label':media.get('tv') or 'Official watch link','url':urljoin(src['url'],u)}] if u else []
        tba=x.get('tbd') or bool(re.search('TBA|TBD', x.get('time') or '',re.I)) or not (x.get('time') or '').strip()
        out.append(game(src,x['id'],x['opponent']['title'],x['date'],tba,x.get('location'),media.get('tv'),links,
            bool(re.search('exh|scrimmage',str(x.get('promotion'))+' '+x['opponent']['title'],re.I)),
            ' '.join(filter(None,[x.get('game_state_display'),x.get('noplay_text')])),x.get('location_indicator') or '',
            (x.get('tournament') or {}).get('title') or ''))
    return [x for x in out if x]

def parse_wmt(src):
    host='https://'+urlparse(src['url']).netloc
    data=get(host+'/website-api/schedule-events',params={'filter[schedule_id]':src['schedule'],
        'per_page':100,'include[]':['scheduleEventLinks.icon','schedule.sport','tournament']}).json()
    if data.get('meta',{}).get('last_page',1)!=1: raise ValueError('Unexpected pagination; refusing incomplete schedule')
    out=[]
    for x in data['data']:
        if x['schedule_id'] != src['schedule'] or '2026-27' not in x['schedule']['name']: raise ValueError('Wrong sport or season')
        links=[]; networks=[]
        for l in x.get('schedule_event_links') or []:
            label=linklabel(l); u=l.get('link') or ''
            if l.get('is_tv_translation') or broadcast_link(label,u):
                if label: networks.append(label.replace('_',' ').replace('.png','').replace(' logo',''))
                if u and not u.startswith('javascript:'): links.append({'label':label or 'Official watch link','url':urljoin(host,u)})
        out.append(game(src,x['id'],x.get('opponent_name') or x.get('opponent_school_name'),x['datetime'],
            x.get('tba') or x.get('is_all_day'),(x.get('location') or '')+(' / '+x['venue'] if x.get('venue') else ''),
            ' / '.join(dict.fromkeys(networks)),links,x.get('is_exhibition'),x.get('status') or '',x.get('venue_type') or '',
            (x.get('tournament') or {}).get('name') or ''))
    return [x for x in out if x]

def parse_wp(src,text):
    soup=BeautifulSoup(text,'html.parser'); out=[]
    nodes=soup.select('.schedule-list.active > .event') or soup.select('.schedule-list > .event')
    for x in nodes:
        opponent=x.select_one('.schedule-list__opponent strong')
        if not opponent: continue
        date=x.select_one('.schedule-list__top > time'); label=date.get_text(' ',strip=True)
        day=re.search(r'(Sep|Oct|Nov|Dec|Jan|Feb|Mar|Apr)\s+(\d+)',label)
        if not day: raise ValueError('Missing official date')
        year=2026 if day[1] in ['Sep','Oct','Nov','Dec'] else 2027
        base=datetime.strptime(f'{year} {day[1]} {day[2]}','%Y %b %d')
        clock=re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)',label,re.I)
        if clock:
            base=base.replace(hour=int(clock[1])%12+(12 if clock[3].lower()=='pm' else 0),minute=int(clock[2]))
        networks=[]; links=[]
        for a in x.select('.schedule-list__bottom a'):
            u=a.get('href') or ''; label=a.get_text(' ',strip=True); img=a.find('img')
            if img:
                im=img.get('src',''); m=re.search(r'/([A-Za-z0-9_-]+)\.\w+$',im)
                if m:
                    try: label+=' '+base64.urlsafe_b64decode(m[1]+'='*(-len(m[1])%4)).decode().split('/')[-1]
                    except (ValueError,UnicodeDecodeError): pass
            if broadcast_link(label,u):
                for token,pattern in [('ESPN+','espn_plus'),('ESPN2','espn2'),('ESPNU','espnu'),('Peacock','peacock'),('ESPN','espn_clr'),('ABC','abc'),('SEC Network+','sec.*(?:plus|network_plus)'),('SEC Network','sec_?network'),('FS1','fs1'),('FOX','fox'),('CBS','cbs')]:
                    if re.search(pattern,label,re.I): networks.append(token);break
                else:
                    if TV.search(label):networks.append(clean(label))
                if u.startswith('http'):links.append({'label':networks[-1] if networks else 'Official watch link','url':u})
        out.append(game(src,canonical(opponent.text)+'-'+ '-'.join(c for c in x.get('class',[]) if c in ['home','away','neutral']),opponent.text,base.isoformat(),not clock,
            x.select_one('.schedule-list__location strong').text,' / '.join(dict.fromkeys(networks)),links,
            'EXH' in x.get_text(),'', 'N' if 'neutral' in x.get('class',[]) else '',
            clean(x.select_one('.schedule-list__opponent > span'))))
    return [x for x in out if x]

def fetch_source(src):
    if src.get('kind')=='wmt': out=parse_wmt(src)
    else:
        text=get(src['url']).text
        if '2026-27' not in text: raise ValueError('Season marker missing')
        out=parse_wp(src,text) if src.get('kind')=='wordpress' else parse_sidearm(src,text)
    if len(out)<25: raise ValueError(f'Only {len(out)} games; likely incomplete or changed source')
    return out

def service(network):
    n=network.lower()
    parts=[]
    if re.search(r'espn|abc|accn|acc network|sec network|secn',n):parts.append('ESPN app — included with your ESPN Unlimited (ESPN+, SECN+ and ACCNX included).')
    if 'peacock' in n:parts.append('Peacock — included with your Peacock Premium.')
    if re.search(r'big.ten.plus|b1g\+|big\+|btn\+',n):parts.append('B1G+ — separate paid subscription; not included with ESPN Unlimited or Peacock.')
    if re.search(r'fox|fs1|fs2|big ten network|\bbtn\b',n):parts.append('FOX Sports / FOX One or a qualifying TV provider — additional access required; verify channel availability.')
    if re.search(r'cbs',n):parts.append('CBS / CBS Sports Network — additional access may be required. Paramount+ does not automatically include CBS Sports Network.')
    if 'uconn' in n:parts.append('UConn+ — separate service; check event access requirements.')
    if re.search(r'tnt|trutv|hbo|max',n):parts.append('TNT / truTV / HBO Max — separate qualifying TV or streaming subscription; check the official event listing.')
    if 'ion' == n.strip():parts.append('ION — free over-the-air where available; verify the official streaming listing.')
    if n.strip()=='cw':parts.append('The CW — local broadcast or qualifying TV provider; online live availability varies.')
    if 'bdg' in n:parts.append('BDG Live — separate event platform; confirm price and access on the official listing.')
    if 'flo' in n:parts.append('FloSports — separate paid subscription.')
    if 'meac' in n:parts.append('MEAC Network — check the official watch link for access requirements.')
    return ' '.join(parts) or 'Streaming access not confirmed; see official schedule. Your ESPN Unlimited and Peacock subscriptions do not cover every network.'

def fingerprint(x):
    return hashlib.sha256(json.dumps({k:v for k,v in x.items() if k not in ['uid','sequence','modified','observed']},sort_keys=True).encode()).hexdigest()

def reconcile(rows,old):
    # Identify on canonical teams + calendar day, then preserve UID using official source IDs across reschedules.
    groups={}
    priority={s['url']:i for i,s in enumerate(SOURCES)}
    for x in sorted(rows,key=lambda x:(priority[x['sources'][0]], x['source_ids'][0])):
        pair=sorted(x['teams']); key='|'.join(pair+[x['date']])
        if not (any(s['required'] and s['name'] in pair for s in SOURCES if s.get('required')) or all(t in NATIONAL for t in pair)):continue
        if re.search(r'\bTBA\b|\bTBD\b|winner|semifinal|quarterfinal|championship|scrimmage|tournament', ' '.join(pair),re.I):continue
        if key not in groups:groups[key]=x
        else:
            y=groups[key]
            if x['start'] and y['start'] and x['start']!=y['start']:raise ValueError('Official schedules disagree on tipoff: '+key)
            if not y['start']:y['start']=x['start']
            for k in ['source_ids','sources','watch']:y[k]=list({json.dumps(v,sort_keys=True):v for v in y[k]+x[k]}.values())
            if x['network'] and x['network'] not in y['network']:y['network']=' / '.join(filter(None,[y['network'],x['network']]))
            y['exhibition']=y['exhibition'] or x['exhibition']
    previous=old.get('games',{}); idmap={sid:uid for uid,x in previous.items() for sid in x['source_ids']}
    result={}; pending={}; changes=0
    for key,x in groups.items():
        uids={idmap[i] for i in x['source_ids'] if i in idmap}
        if len(uids)>1:raise ValueError('Conflicting stable game IDs')
        uid=next(iter(uids),hashlib.sha256(key.encode()).hexdigest()[:24]+'@wbb.asiacook4-stack.github.io')
        before=previous.get(uid); x['uid']=uid;x['sequence']=before['sequence'] if before else 0;x['modified']=before['modified'] if before else STAMP
        if before and fingerprint(x)!=fingerprint(before):
            changes+=1; fp=fingerprint(x); p=old.get('pending',{}).get(uid,{})
            # Require two matching observations at least 30 minutes apart before changing an existing event.
            if p.get('hash')!=fp or (NOW-iso(p['first_seen'])).total_seconds()<1800:
                pending[uid]={'hash':fp,'first_seen':p.get('first_seen',STAMP) if p.get('hash')==fp else STAMP,'candidate':x}
                x=before
            else:x['sequence']+=1;x['modified']=STAMP
        result[uid]=x
    missing=set(previous)-set(result)
    if len(missing)>max(3,len(previous)*.05):raise ValueError('Unexpected disappearance of games; retaining last good feed')
    # Never delete games because a row disappears; explicit cancellation is required.
    for uid in missing:result[uid]=previous[uid]
    if previous and changes>max(12,len(previous)*.15):raise ValueError('Mass schedule changes require review')
    return {'games':result,'pending':pending,'updated':STAMP,'missing_retained':sorted(missing)}

def verify_url(url):
    if urlparse(url).scheme!='https':return {'ok':False,'reason':'Non-HTTPS official link; not promoted as a verified watch URL','checked':STAMP}
    try:
        r=session().get(url,timeout=(10,20),stream=True); code=r.status_code; final=r.url;r.close()
        return {'ok':200<=code<400 and final.startswith('https://'),'http':code,'final':final,'checked':STAMP}
    except requests.RequestException as e:return {'ok':False,'reason':type(e).__name__,'checked':STAMP}

def write_feed(state,checks,counts):
    cal=Calendar();cal.add('prodid','-//Official WBB Subscription//2026-27//EN');cal.add('version','2.0');cal.add('calscale','GREGORIAN');cal.add('method','PUBLISH')
    cal.add('x-wr-calname','Women’s Basketball 2026–27');cal.add('x-wr-timezone','America/Los_Angeles');cal.add('refresh-interval',timedelta(hours=6));cal.add('x-published-ttl','PT6H')
    cal.add_component(Timezone.from_tzinfo(PACIFIC, first_date=date(2026,9,1), last_date=date(2027,5,1)))
    for x in sorted(state['games'].values(),key=lambda x:(x['date'],x['teams'])):
        e=Event();e.add('uid',x['uid']);e.add('dtstamp',iso(x['modified']));e.add('last-modified',iso(x['modified']));e.add('sequence',x['sequence'])
        teams=x['teams']; title=' vs '.join(teams)+(' [Exhibition]' if x['exhibition'] else '')
        desc=['Network: '+(x['network'] or 'TBA — not yet announced'), 'Streaming: '+service(x['network'])]
        if x['start']:
            d=iso(x['start']).astimezone(PACIFIC);e.add('dtstart',d);e.add('dtend',d+timedelta(hours=2,minutes=15));desc+=['Tipoff (Pacific): '+d.strftime('%a %b %d, %Y %I:%M %p %Z'),'End time is an estimate (2h 15m).']
        else:
            d=datetime.fromisoformat(x['date']).date();e.add('dtstart',d);e.add('dtend',d+timedelta(days=1));title+=' [Time TBA]';desc+=['All-day placeholder: tipoff time has not been announced. Date is the official schedule date.']
        preferred=None
        watches=list(x['watch'])
        if not watches:
            n=x['network'].lower()
            for pattern,label,url in [(r'espn|abc|accn|acc network|sec network|secn','ESPN watch directory','https://www.espn.com/watch/'),(r'peacock','Peacock college basketball directory','https://www.peacocktv.com/sports/college-basketball'),(r'big.ten.plus|b1g\+|big\+','B1G+ service page','https://www.bigtenplus.com/'),(r'fox|fs1|fs2|big ten network|\bbtn\b','FOX Sports live directory','https://www.foxsports.com/live')]:
                if re.search(pattern,n):watches.append({'label':label,'url':url})
        for w in sorted(watches,key=lambda w:0 if re.search('/player/|/event/|Live=',w['url']) else 1):
            c=checks.get(w['url'],{});kind='Game link' if re.search('/player/|/event/|Live=',w['url']) else 'Service / channel page (not a game deep link)'
            desc.append(f"{kind} — {w['label']}: {w['url']}\nLink check: "+('reachable; playback requires the appropriate login' if c.get('ok') else 'published by the official team; automated verification unavailable, HTTP '+str(c.get('http','unknown'))))
            if c.get('ok') and preferred is None:preferred=w['url']
        if not watches:desc.append('Watch URL TBA — no official streaming link has been published.')
        desc+=['Official schedule: '+u for u in x['sources']]
        if x['note']:desc.append(x['note'])
        if x['coverage']=='National spotlight':desc.append('National spotlight: matchup between teams in the published contender pool.')
        status=x['status'].lower()
        if 'cancel' in status:e.add('status','CANCELLED');title='CANCELLED: '+title
        if 'postpon' in status: title='POSTPONED: '+title;desc.append('Officially postponed; see source for the replacement date.')
        e.add('summary',title);e.add('location',x['location']);e.add('description','\n\n'.join(desc));e.add('url',preferred or x['sources'][0]);e.add('transp','TRANSPARENT');cal.add_component(e)
    data=cal.to_ical(); parsed=Calendar.from_ical(data)
    assert len(parsed.walk('VEVENT'))==len(state['games'])
    for ev in parsed.walk('VEVENT'):
        assert ev.decoded('dtend')>ev.decoded('dtstart')
    out=ROOT/'docs';out.mkdir(exist_ok=True)
    (out/'calendar.ics').write_bytes(data)
    (out/'index.html').write_text((ROOT/'index.html').read_text())
    (out/'status.json').write_text(json.dumps({'updated':STAMP,'games':len(state['games']),'source_counts':counts,'pending_changes':len(state['pending']),'missing_retained':len(state['missing_retained']),'watch_urls_reachable':sum(c['ok'] for c in checks.values()),'watch_urls_total':len(checks)},indent=2))
    (ROOT/'state.json').write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n')
    (ROOT/'link-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    print((out/'status.json').read_text())

def main():
    rows=[];counts={};errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(fetch_source,s):s for s in SOURCES}
        for f in concurrent.futures.as_completed(futures):
            s=futures[f]
            try:
                games=f.result();rows+=games;counts[s['name']]=len(games)
            except Exception as e:errors.append(s['name']+': '+str(e))
    if errors:raise RuntimeError('Source validation failed; existing calendar untouched: '+'; '.join(errors))
    oldpath=ROOT/'state.json';old=json.loads(oldpath.read_text()) if oldpath.exists() else {}
    state=reconcile(rows,old)
    cachepath=ROOT/'link-checks.json';checks=json.loads(cachepath.read_text()) if cachepath.exists() else {}
    urls={w['url'] for x in state['games'].values() for w in x['watch']}
    urls.update(['https://www.espn.com/watch/','https://www.peacocktv.com/sports/college-basketball','https://www.bigtenplus.com/','https://www.foxsports.com/live'])
    due=[u for u in urls if u not in checks or (NOW-iso(checks[u]['checked'])).total_seconds()>86400]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        checks.update(zip(due,pool.map(verify_url,due)))
    write_feed(state,{u:checks[u] for u in urls},counts)

if __name__=='__main__':main()
