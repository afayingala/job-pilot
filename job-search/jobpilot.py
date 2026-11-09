"""JobPilot: local, scheduled job discovery and truthful application delivery."""
from __future__ import annotations
import argparse, base64, ctypes, hashlib, html, ipaddress, json, logging, os, re
import secrets, smtplib, socket, sqlite3, ssl, sys, threading, time, unicodedata, subprocess
import urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=1))
LOCK = threading.Lock()
TOKEN = secrets.token_urlsafe(32)
PORT = 8765
DEFAULT = {"auto_apply": True, "paused": False, "max_applications": 10,
           "min_score": 55, "browser_enabled": True,
           "smtp_host": "smtp.gmail.com", "smtp_port": 465,
           "smtp_user": "afayingala67@gmail.com", "smtp_tls": "ssl",
           "sources": [
               {"type": "himalayas", "url": "https://himalayas.app/jobs/api/search"},
               {"type": "remotive", "url": "https://remotive.com/api/remote-jobs?category=software-dev"},
               {"type": "greenhouse", "company": "Canonical", "url": "https://boards-api.greenhouse.io/v1/boards/canonical/jobs?content=true"},
               {"type": "careers", "url": "https://www.camsoltechnology.com/careers"},
               {"type": "careers", "url": "https://sabmadigital.com/cm/carrieres/"},
               {"type": "careers", "url": "https://pembo.cm/recrutement"}]}

def now(): return datetime.now(TZ).isoformat(timespec="seconds")
def read_json(path, default):
    try: return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError: return default
def write_json(path, data):
    path = Path(path); temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)
def config(): return DEFAULT | read_json(ROOT / "settings.json", {})
def profile(): return read_json(ROOT / "profile.json", {})
def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s)).lower() if not unicodedata.combining(c))

def identity(company,title):
    return (re.sub(r'[^a-z0-9]','',normalize(company)),re.sub(r'[^a-z0-9]','',re.sub(r'\bremote\b','',normalize(title))))

class Page(HTMLParser):
    def __init__(self, raw):
        super().__init__(); self.texts=[]; self.links=[]; self.scripts=[]
        self.skip=0; self.ld=False; self.buf=[]; self.anchor=None; self.h1=False; self.heading=[]
        self.feed(raw)
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag in ('script','style'):
            self.skip += 1
            if tag=='script' and a.get('type')=='application/ld+json': self.ld=True; self.buf=[]
        if tag=='a': self.anchor=[a.get('href',''), '']
        if tag=='h1': self.h1=True
    def handle_endtag(self, tag):
        if tag=='script' and self.ld:
            try: self.scripts.append(json.loads(''.join(self.buf)))
            except (ValueError,TypeError): pass
            self.ld=False
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag=='a' and self.anchor: self.links.append(tuple(self.anchor)); self.anchor=None
        if tag=='h1': self.h1=False
    def handle_data(self, data):
        if self.ld: self.buf.append(data)
        if not self.skip: self.texts.append(data)
        if self.anchor: self.anchor[1] += data
        if self.h1: self.heading.append(data)
    @property
    def text(self): return re.sub(r'\s+', ' ', ' '.join(self.texts)).strip()

def validate_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
        raise ValueError('A public HTTP(S) URL is required')
    for a in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80)):
        if not ipaddress.ip_address(a[4][0]).is_global: raise ValueError('Private network URLs are not allowed')
    return url

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url):
    validate_url(url)
    req=urllib.request.Request(url,headers={"User-Agent":"JobPilot/1.0 (personal job search)","Accept":"application/json,text/html"})
    with urllib.request.build_opener(SafeRedirect()).open(req,timeout=20) as r:
        data=r.read(4_000_001)
        if len(data)>4_000_000: raise ValueError('Source response too large')
        return data.decode('utf-8',errors='replace'),r.geturl()

class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try: return super().__exit__(*args)
        finally: self.close()

def db():
    c=sqlite3.connect(ROOT/'jobpilot.db',timeout=30,factory=ClosingConnection)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c

def init():
    for name in ('drafts','evidence','logs','cache'): (ROOT/name).mkdir(exist_ok=True)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,title TEXT,company TEXT,url TEXT,
        source TEXT,source_url TEXT,location TEXT,description TEXT,deadline TEXT,score INTEGER,
        skills TEXT,status TEXT,reason TEXT,email TEXT,created TEXT,updated TEXT,draft TEXT,
        confirmation TEXT,attempts INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,started TEXT,finished TEXT,
        discovered INTEGER DEFAULT 0,matched INTEGER DEFAULT 0,sent INTEGER DEFAULT 0,errors TEXT);
        CREATE TABLE IF NOT EXISTS slots(slot TEXT PRIMARY KEY,started TEXT);
        ''')
        # Never repeat a potentially successful attempt inherited from the earlier workflow.
        for j in read_json(ROOT/'applications.json',{}).get('applications',[]):
            status=j.get('status','prospect_not_submitted')
            if j.get('employer')=='SABMA Digital': status='submission_uncertain'
            jid=hashlib.sha256(j['url'].rstrip('/').encode()).hexdigest()[:20]
            c.execute('INSERT OR IGNORE INTO jobs(id,title,company,url,source,source_url,location,description,score,skills,status,reason,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (jid,j['role'],j['employer'],j['url'],'Previous research',j['url'],'Douala',j.get('notes',''),0,'[]',status,j.get('notes',''),now(),now()))
    if not (ROOT/'settings.json').exists(): write_json(ROOT/'settings.json',DEFAULT)

def expired(value):
    if not value: return False
    try:
        dt=datetime.fromtimestamp(float(value),timezone.utc) if str(value).replace('.','',1).isdigit() else datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=TZ)
        return dt < datetime.now(TZ)
    except (ValueError,OverflowError): return True

def page_deadline(text):
    m=re.search(r'(?:apply by|application deadline|deadline)\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',text,re.I)
    if m:
        try: return datetime.strptime(m.group(1).replace(',',''),'%B %d %Y').isoformat()
        except ValueError: pass
    months={'janvier':1,'fevrier':2,'mars':3,'avril':4,'mai':5,'juin':6,'juillet':7,'aout':8,'septembre':9,'octobre':10,'novembre':11,'decembre':12}
    m=re.search(r'(?:jusqu.au|date limite\s*:?|cloture\s*:?)(?:\s+le)?\s+(\d{1,2})\s+([a-z]+)\s+(\d{4})',normalize(text))
    if m and m.group(2) in months:
        try: return datetime(int(m.group(3)),months[m.group(2)],int(m.group(1)),23,59).isoformat()
        except ValueError: pass
    return None

def match(j,p):
    title=normalize(j['title']); text=normalize(j.get('description','')); loc=normalize(j.get('location',''))
    if expired(j.get('deadline')): return 0,[],'Expired posting'
    if re.search(r'\b(senior|sr\.?|lead|principal|staff|manager|director|head of|architect|expert)\b',title): return 0,[],'Seniority exceeds resume'
    if re.search(r'\b(sales|commercial|recruit|account executive)\b',title): return 0,[],'Commercial experience is not supported by resume'
    if re.search(r'\b(golang|rust|ruby|php|laravel|\.net|c\+\+)\b',title): return 0,[],'Core role technology is not supported by resume'
    if not re.search(r'develop|engineer|ingenieur|software|programmeur|qa|test|computer vision',title): return 0,[],'Role does not match software resume'
    if re.search(r'\b(unpaid|unremunerated|non remunere|benevole|volunteer)\b',title+' '+text): return 0,[],'Unpaid role'
    if re.search(r'\b(?:[3-9]|\d{2})\+?\s*(?:years|ans)\s*(?:of\s*)?(?:professional\s*)?(?:experience|d.experience)',text): return 0,[],'Experience requirement exceeds evidence'
    if re.search(r'\b(fluent french|french fluency|francais courant|bilingue)\b',text): return 0,[],'French fluency is not supported'
    if re.search(r'(?:must|required|minimum).{0,35}(?:completed|earned).{0,20}(?:degree|bachelor)',text) and not p['degree']['completed_confirmed']:
        return 0,[],'Completed degree required; status unconfirmed'
    if not j.get('eligible') and not ('douala' in loc): return 0,[],'Cameroon eligibility not established'
    # Word boundaries prevent Java being counted as JavaScript.
    skills=[s for s in p['skills'] if re.search(r'(?<!\w)'+re.escape(normalize(s))+r'(?!\w)',title+' '+text)]
    score=min(95,35+len(skills)*8+(15 if re.search(r'junior|entry|graduate|intern|stagiaire',title) else 0))
    return score,skills,'Matched resume skills: '+', '.join(skills)

def structured_jobs(value):
    if isinstance(value,list):
        for v in value: yield from structured_jobs(v)
    elif isinstance(value,dict):
        typ=value.get('@type',[])
        if typ=='JobPosting' or isinstance(typ,list) and 'JobPosting' in typ: yield value
        if '@graph' in value: yield from structured_jobs(value['@graph'])

def job_from_ld(v,url):
    org=v.get('hiringOrganization',{})
    loc=json.dumps(v.get('jobLocation',{}),ensure_ascii=False)
    restrictions=json.dumps(v.get('applicantLocationRequirements',{}))
    remote=str(v.get('jobLocationType','')).upper()=='TELECOMMUTE'
    eligible='cameroon' in normalize(restrictions) or (remote and bool(re.search(r'worldwide|anywhere',normalize(restrictions))))
    return {'title':v.get('title',''),'company':org.get('name','') if isinstance(org,dict) else str(org),
            'url':v.get('url') or url,'location':loc,'description':Page(v.get('description','')).text,
            'deadline':v.get('validThrough'),'eligible':eligible,'source':'Employer','source_url':url}

def cached_json(url,max_age=21600):
    path=ROOT/'cache'/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    if path.exists() and time.time()-path.stat().st_mtime<max_age: return read_json(path,{})
    raw,_=fetch(url); data=json.loads(raw); write_json(path,data); return data

def discover(cfg):
    jobs=[]; errors=[]
    for source in cfg['sources']:
        try:
            if source['type']=='himalayas':
                for query in ('frontend','full stack','python','react native','QA'):
                    for page in range(1,4):
                        url=source['url']+'?'+urllib.parse.urlencode({'q':query,'country':'CM','seniority':'Entry-level','timezone':'UTC+1','page':page})
                        data=cached_json(url); batch=data.get('jobs',[])
                        for v in batch:
                            restrictions=v.get('locationRestrictions',[])
                            eligible=not restrictions or 'cameroon' in normalize(json.dumps(restrictions)) or 'cm' in [normalize(x) for x in restrictions]
                            jobs.append({'title':v['title'],'company':v['companyName'],'url':v.get('applicationLink') or v['guid'],
                                'description':Page(v.get('description') or v.get('excerpt','')).text,'location':('Remote - Cameroon eligible' if restrictions and eligible else ', '.join(restrictions)) or 'Worldwide',
                                'deadline':v.get('expiryDate'),'eligible':eligible,'source':'Himalayas','source_url':v.get('guid','https://himalayas.app')})
                        if len(batch)<20: break
            elif source['type']=='remotive':
                for v in cached_json(source['url']).get('jobs',[]):
                    loc=v.get('candidate_required_location','')
                    jobs.append({'title':v['title'],'company':v['company_name'],'url':v['url'],'description':Page(v.get('description','')).text,
                        'location':loc,'eligible':bool(re.fullmatch(r'worldwide|anywhere|africa|cameroon',loc.strip(),re.I)),
                        'deadline':None,'source':'Remotive','source_url':v['url']})
            elif source['type']=='greenhouse':
                for v in cached_json(source['url']).get('jobs',[]):
                    loc=v.get('location',{}).get('name','')
                    eligible=bool(re.search(r'worldwide|cameroon|africa|emea',loc,re.I) and re.search(r'home.?based|remote',loc,re.I))
                    jobs.append({'title':v['title'],'company':source.get('company','Employer'),'url':v['absolute_url'],
                        'description':Page(html.unescape(v.get('content',''))).text,'location':loc,'eligible':eligible,
                        'deadline':None,'source':'Employer','source_url':v['absolute_url']})
            elif source['type']=='careers':
                raw,url=fetch(source['url']); doc=Page(raw)
                for v in doc.scripts:
                    jobs.extend(job_from_ld(x,url) for x in structured_jobs(v))
                urls=[]
                for href,title in doc.links:
                    target=urllib.parse.urljoin(url,href)
                    if urllib.parse.urlsplit(target).hostname!=urllib.parse.urlsplit(url).hostname: continue
                    prefix=urllib.parse.urlsplit(url).path.rstrip('/')+'/'
                    if not urllib.parse.urlsplit(target).path.startswith(prefix): continue
                    if target.rstrip('/')==url.rstrip('/'): continue
                    if re.search(r'develop|engineer|ingenieur|frontend|full.?stack|mobile|qa|testeur',normalize(title)) and target not in urls: urls.append(target)
                for target in urls[:15]:
                    try:
                        raw,final=fetch(target); d=Page(raw)
                        found=[job_from_ld(x,final) for v in d.scripts for x in structured_jobs(v)]
                        if found: jobs.extend(found)
                        else:
                            # Unstructured employer pages are reviewable leads, not auto-approved vacancies.
                            title=' '.join(d.heading).strip() or next((t for h,t in doc.links if urllib.parse.urljoin(url,h)==target),target)
                            deadline=page_deadline(d.text)
                            jobs.append({'title':title,'company':urllib.parse.urlsplit(final).hostname,'url':final,'description':d.text,
                                'location':'Douala' if 'douala' in normalize(d.text) else '', 'eligible':False,
                                'deadline':deadline,'unstructured':not bool(deadline),'source':'Employer','source_url':final})
                    except Exception as e: errors.append(f'{target}: {type(e).__name__}: {e}')
            else: errors.append('Unknown source type: '+source['type'])
        except Exception as e: errors.append(f"{source['url']}: {type(e).__name__}: {e}")
    return jobs,errors

def draft(j,p):
    hits=json.loads(j['skills']) if isinstance(j['skills'],str) else j['skills']
    degree='completed' if p['degree']['completed_confirmed'] else 'expected in December 2026'
    return (f"Dear {j['company']} hiring team,\n\nI am applying for the {j['title']} role. "
        f"I am a Cameroon-based software developer with hands-on experience in {', '.join(hits[:6]) or 'full-stack development'}. "
        "During my August 2025-February 2026 internship at Zinger Systems Ltd, I built production Vue.js and TypeScript frontend modules "
        "and backend business logic using Parse Server and MongoDB.\n\n"
        "My projects include a React-based video object-tracking platform, a React/Node.js network monitoring portal, "
        "and a React Native productivity application. I enjoy building useful interfaces and reliable backend services. "
        f"My University of Buea Computer Engineering degree is {degree}. I speak native English and basic French.\n\n"
        f"Portfolio: {p['portfolio']}\nGitHub: {p['github']}\n\n"
        f"I would welcome a conversation about this opportunity. My resume is attached.\n\n{p['name']}\n{p['email']}\n{p['phone']}\n")

def dpapi(data,decode=False):
    if os.name!='nt': raise RuntimeError('Secure credential storage requires Windows')
    from ctypes import wintypes
    class Blob(ctypes.Structure): _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]
    buf=ctypes.create_string_buffer(data); src=Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_byte))); out=Blob()
    if decode: ok=ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src),None,None,None,None,1,ctypes.byref(out))
    else: ok=ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src),'JobPilot',None,None,None,1,ctypes.byref(out))
    if not ok: raise ctypes.WinError()
    try: return ctypes.string_at(out.data,out.size)
    finally: ctypes.windll.kernel32.LocalFree(out.data)
def password():
    env=os.environ.get('JOBPILOT_SMTP_PASSWORD')
    if env: return env
    path=ROOT/'smtp.secret'
    return dpapi(path.read_bytes(),True).decode() if path.exists() else ''

def connect_smtp(cfg):
    pw=password()
    if not pw: raise RuntimeError('Connect your sending email in Settings first')
    context=ssl.create_default_context()
    if cfg['smtp_tls']=='ssl': client=smtplib.SMTP_SSL(cfg['smtp_host'],int(cfg['smtp_port']),timeout=30,context=context)
    else:
        client=smtplib.SMTP(cfg['smtp_host'],int(cfg['smtp_port']),timeout=30); client.ehlo(); client.starttls(context=context); client.ehlo()
    try: client.login(cfg['smtp_user'],pw)
    except Exception: client.close(); raise
    return client

def application_email(doc):
    # Only use an explicitly instructed application address, never generic contact footers.
    text=html.unescape(doc.text)
    candidates=[]
    for m in re.finditer(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}',text,re.I):
        context=text[max(0,m.start()-220):m.end()+80]
        if re.search(r'(send|email|envoy|ecriv|transmett|postul|candidatur|apply)',normalize(context)) and re.search(r'cv|resume|application|candidatur',normalize(context)):
            candidates.append(m.group())
    return candidates[0] if len(set(candidates))==1 else None

def deliver_email(j,cfg,p):
    msg=EmailMessage(); msg['From']=formataddr((p['name'],cfg['smtp_user'])); msg['To']=j['email']
    msg['Reply-To']=p['email']; msg['Subject']=f"Application - {j['title']} - {p['name']}"
    msg['Message-ID']=make_msgid(domain=cfg['smtp_user'].split('@')[-1]); msg.set_content(j['draft'])
    msg.add_attachment((ROOT/'RESUME.pdf').read_bytes(),maintype='application',subtype='pdf',filename='Afayi_Ngala_Resume.pdf')
    with connect_smtp(cfg) as smtp:
        rejected=smtp.send_message(msg)
        if rejected: raise RuntimeError('Mail server rejected recipient')
    return 'SMTP accepted message '+str(msg['Message-ID'])+'; employer receipt not independently confirmed'

def update(jid,**fields):
    fields['updated']=now()
    with db() as c: c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',list(fields.values())+[jid])

def run(dry=False):
    if not LOCK.acquire(blocking=False): return {'error':'A run is already active'}
    # SQLite lease also prevents overlap across scheduler and dashboard processes.
    lease='running'
    try:
        with db() as c:
            c.execute("DELETE FROM slots WHERE slot=? AND started<?",(lease,(datetime.now(TZ)-timedelta(hours=2)).isoformat(timespec='seconds')))
            try: c.execute('INSERT INTO slots VALUES(?,?)',(lease,now()))
            except sqlite3.IntegrityError: return {'error':'Another process is running'}
        return _run(dry)
    finally:
        if 'lease' in locals():
            # Only the holder deletes its lease, set by _run ownership flag below.
            if getattr(threading.current_thread(),'jobpilot_owner',False):
                with db() as c: c.execute('DELETE FROM slots WHERE slot=?',(lease,))
                threading.current_thread().jobpilot_owner=False
        LOCK.release()

def _run(dry):
    threading.current_thread().jobpilot_owner=True
    cfg=config(); p=profile()
    if cfg['paused']: return {'paused':True}
    with db() as c: rid=c.execute('INSERT INTO runs(started) VALUES(?)',(now(),)).lastrowid
    jobs,errors=discover(cfg); matched=0; sent=0; attempted=0
    seen=set()
    for j in jobs:
        try:
            score,skills,reason=match(j,p)
            jid=hashlib.sha256(j['url'].rstrip('/').encode()).hexdigest()[:20]
            if jid in seen: continue
            seen.add(jid)
            status='matched' if score>=cfg['min_score'] else 'excluded'
            if j.get('unstructured') and status=='matched': status='needs_review'; reason='Employer page lacks structured vacancy/deadline; verify before applying'
            with db() as c:
                previous=c.execute("SELECT company,title FROM jobs WHERE status IN ('submitted','submission_uncertain','submitting')").fetchall()
                if any(identity(x['company'],x['title'])==identity(j['company'],j['title']) for x in previous): continue
                existing=c.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()
                if existing:
                    if existing['status'] in ('submitted','submission_uncertain','submitting'): continue
                    old_status=existing['status']
                    next_status=status if old_status in ('matched','excluded') else old_status
                    c.execute('UPDATE jobs SET score=?,skills=?,description=?,location=?,status=?,reason=CASE WHEN status IN (\'matched\',\'excluded\') THEN ? ELSE reason END,updated=? WHERE id=?',(score,json.dumps(skills),j['description'],j.get('location',''),next_status,reason,now(),jid))
                else:
                    c.execute('INSERT INTO jobs(id,title,company,url,source,source_url,location,description,deadline,score,skills,status,reason,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (jid,j['title'],j['company'],j['url'],j['source'],j['source_url'],j.get('location',''),j['description'],j.get('deadline'),score,json.dumps(skills),status,reason,now(),now()))
            if score<cfg['min_score']: continue
            matched+=1
            with db() as c: row=dict(c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
            body=draft(row,p); update(jid,draft=body)
            (ROOT/'drafts'/(jid+'.txt')).write_text(body,encoding='utf-8')
            if dry or not cfg['auto_apply'] or status=='needs_review': continue
            if sent>=int(cfg['max_applications']): continue
            if attempted>=int(cfg['max_applications'])*2: continue
            if row['status'] in ('needs_review','blocked','failed'): continue
            # Refresh original application page immediately before attempting delivery.
            doc=None
            try:
                raw,final=fetch(j['url']); doc=Page(raw)
            except Exception as source_error:
                if not cfg['browser_enabled']:
                    update(jid,status='blocked',reason=f'Application page inaccessible: {type(source_error).__name__}'); continue
                errors.append(f"Browser fallback for {j['url']}: {type(source_error).__name__}")
            if doc and re.search(r'position (?:is |has been )?closed|no longer accepting|job (?:has )?expired|offre expiree',normalize(doc.text)):
                update(jid,status='excluded',reason='Posting is closed'); continue
            # Aggregator page is a lead; browser may follow its Apply link.
            recipient=application_email(doc) if doc and j['source']=='Employer' else None
            if recipient:
                if not password(): update(jid,status='blocked',reason='Email account not connected'); continue
                update(jid,email=recipient,status='submitting',attempts=row['attempts']+1)
                row.update(email=recipient,draft=body)
                try: receipt=deliver_email(row,cfg,p)
                except smtplib.SMTPRecipientsRefused:
                    update(jid,status='failed',reason='Recipient rejected by mail server'); continue
                except Exception as e:
                    update(jid,status='submission_uncertain',reason=f'Email attempt: {type(e).__name__}; verify before retry'); continue
                update(jid,status='submitted',confirmation=receipt,reason='Application email accepted by SMTP server'); sent+=1
            elif cfg['browser_enabled']:
                from browser_apply import apply
                attempted+=1
                update(jid,status='submitting',attempts=row['attempts']+1)
                result=apply(row|{'draft':body},p,ROOT,headless=True)
                update(jid,**result)
                if result['status']=='submitted': sent+=1
            else: update(jid,status='blocked',reason='Online form requires browser adapter')
        except Exception as e:
            errors.append(f"{j.get('url','')}: {type(e).__name__}: {e}")
            if 'jid' in locals():
                with db() as c:
                    r=c.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()
                if r:
                    if r['status']=='submitting': update(jid,status='submission_uncertain',reason='Attempt interrupted; verify before retry')
                    elif r['status']=='matched': update(jid,status='blocked',reason=f'Application attempt failed: {type(e).__name__}: {str(e)[:160]}')
    result={'discovered':len(jobs),'matched':matched,'submitted':sent,'errors':errors,'dry_run':dry,'finished':now()}
    with db() as c: c.execute('UPDATE runs SET finished=?,discovered=?,matched=?,sent=?,errors=? WHERE id=?',(now(),len(jobs),matched,sent,json.dumps(errors),rid))
    write_json(ROOT/'last-run.json',result)
    return result

def state():
    cfg=config()
    with db() as c:
        jobs=[dict(x) for x in c.execute('SELECT * FROM jobs ORDER BY score DESC,updated DESC LIMIT 500')]
        runs=[dict(x) for x in c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 15')]
    return {'settings':cfg,'profile':profile(),'jobs':jobs,'runs':runs,'email_connected':bool(password()),'running':LOCK.locked(),
            'schedule':['12:00','17:00'],'timezone':'Cameroon UTC+1','token':TOKEN}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def respond(self,data,status=200,kind='application/json'):
        raw=json.dumps(data,ensure_ascii=False).encode() if kind=='application/json' else data.encode()
        self.send_response(status); self.send_header('Content-Type',kind+'; charset=utf-8'); self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
    def valid_host(self): return self.headers.get('Host') in (f'127.0.0.1:{PORT}',f'localhost:{PORT}')
    def do_GET(self):
        if not self.valid_host(): return self.respond({'error':'Invalid host'},403)
        if self.path=='/': return self.respond((ROOT/'dashboard.html').read_text(encoding='utf-8'),kind='text/html')
        if self.path=='/api/state': return self.respond(state())
        return self.respond({'error':'Not found'},404)
    def do_POST(self):
        if not self.valid_host() or self.headers.get('X-JobPilot-Token')!=TOKEN: return self.respond({'error':'Invalid local request token'},403)
        try:
            size=int(self.headers.get('Content-Length',0))
            if size>100000: raise ValueError('Request too large')
            data=json.loads(self.rfile.read(size) or '{}')
            if self.path=='/api/run':
                threading.Thread(target=run,kwargs={'dry':bool(data.get('dry'))},daemon=True).start(); return self.respond({'started':True})
            if self.path=='/api/settings':
                cfg=config()
                for k in ('auto_apply','paused','browser_enabled'):
                    if k in data: cfg[k]=bool(data[k])
                for k in ('smtp_host','smtp_user','smtp_tls'):
                    if k in data:
                        if '\n' in str(data[k]) or '\r' in str(data[k]): raise ValueError('Invalid setting')
                        cfg[k]=str(data[k])
                if 'smtp_port' in data: cfg['smtp_port']=int(data['smtp_port'])
                if 'max_applications' in data: cfg['max_applications']=max(1,min(50,int(data['max_applications'])))
                if 'smtp_password' in data and data['smtp_password']:
                    (ROOT/'smtp.secret').write_bytes(dpapi(data['smtp_password'].replace(' ','').encode()))
                write_json(ROOT/'settings.json',cfg)
                if data.get('smtp_password'):
                    with db() as c: c.execute("UPDATE jobs SET status='matched',reason='Email connected; queued for next run' WHERE status='blocked' AND reason='Email account not connected'")
                return self.respond({'saved':True})
            if self.path=='/api/email-test':
                with connect_smtp(config()) as smtp: smtp.noop()
                return self.respond({'ok':True,'message':'Email login verified. No message sent.'})
            if self.path=='/api/profile':
                p=profile()
                for k in ('availability','citizenship','work_authorization','expected_hourly_rate','salary_expectation'):
                    if k in data:
                        value=str(data[k]).strip()
                        if len(value)>500 or '\r' in value or '\n' in value: raise ValueError('Profile answer is too long')
                        p[k]=value or None
                if 'completed_confirmed' in data: p['degree']['completed_confirmed']=bool(data['completed_confirmed'])
                write_json(ROOT/'profile.json',p)
                return self.respond({'saved':True})
            if self.path=='/api/browser-login':
                subprocess.Popen([sys.executable,str(ROOT/'jobpilot.py'),'--browser-login'],cwd=str(ROOT),
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                return self.respond({'opened':True})
            if self.path=='/api/source':
                cfg=config(); url=validate_url(data['url']); typ=data.get('type','careers')
                if urllib.parse.urlsplit(url).hostname=='boards-api.greenhouse.io': typ='greenhouse'
                if typ not in ('careers','himalayas','remotive','greenhouse'): raise ValueError('Unsupported source')
                if not any(s['url']==url for s in cfg['sources']): cfg['sources'].append({'type':typ,'url':url})
                write_json(ROOT/'settings.json',cfg); return self.respond({'saved':True})
            if self.path=='/api/job':
                if data['status'] not in ('matched','excluded','submitted','needs_review'): raise ValueError('Invalid status')
                if data['status']=='matched':
                    with db() as c: r=c.execute('SELECT status FROM jobs WHERE id=?',(data['id'],)).fetchone()
                    if r and r['status'] in ('submission_uncertain','submitted','submitting'): raise ValueError('Verify the previous attempt before retrying; mark submitted or excluded')
                update(data['id'],status=data['status'],reason='Status updated by user'); return self.respond({'saved':True})
            return self.respond({'error':'Not found'},404)
        except Exception as e: return self.respond({'error':str(e)},400)

def main():
    a=argparse.ArgumentParser(); a.add_argument('--run-once',action='store_true'); a.add_argument('--dry-run',action='store_true')
    a.add_argument('--serve',action='store_true'); a.add_argument('--browser-login',action='store_true'); a.add_argument('--port',type=int,default=8765)
    args=a.parse_args(); init()
    if args.browser_login:
        from browser_apply import login
        login(ROOT); return
    if args.run_once: print(json.dumps(run(args.dry_run),indent=2)); return
    global PORT; PORT=args.port
    print(f'JobPilot dashboard: http://127.0.0.1:{PORT}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()

if __name__=='__main__': main()
