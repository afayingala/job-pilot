"""Desktop Google OAuth with PKCE, account verification, and Gmail send-only access."""
import base64, hashlib, json, secrets, threading, time, urllib.parse, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

SCOPES='openid email https://www.googleapis.com/auth/gmail.send'
AUTH='https://accounts.google.com/o/oauth2/v2/auth'
TOKEN='https://oauth2.googleapis.com/token'
USERINFO='https://openidconnect.googleapis.com/v1/userinfo'
SEND='https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
LOCK=threading.Lock()
FLOW={'status':'idle'}

def read_secret(root,name):
    from jobpilot import dpapi
    path=root/name
    return json.loads(dpapi(path.read_bytes(),True)) if path.exists() else None

def write_secret(root,name,value):
    from jobpilot import dpapi
    path=root/name; temp=path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
    temp.write_bytes(dpapi(json.dumps(value).encode())); temp.replace(path)

def save_client(root,data):
    client=data.get('installed') if isinstance(data,dict) else None
    if not isinstance(client,dict) or not str(client.get('client_id','')).endswith('.apps.googleusercontent.com'):
        raise ValueError('Upload Google OAuth credentials for a Desktop app (the JSON must contain an installed section).')
    if not client.get('client_secret'): raise ValueError('Desktop OAuth client secret is missing.')
    write_secret(root,'google-client.secret',{'client_id':client['client_id'],'client_secret':client['client_secret']})

def request_json(url,form=None,payload=None,access=None):
    headers={'Accept':'application/json'}; body=None
    if form is not None: body=urllib.parse.urlencode(form).encode(); headers['Content-Type']='application/x-www-form-urlencoded'
    if payload is not None: body=json.dumps(payload).encode(); headers['Content-Type']='application/json'
    if access: headers['Authorization']='Bearer '+access
    req=urllib.request.Request(url,data=body,headers=headers)
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs): return None
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=25) as response: return json.load(response)
    except Exception as exc:
        # Never expose authorization codes, credentials, or response bodies in app errors.
        raise RuntimeError('Google request failed. Check the Google app setup or reconnect your account.') from None

def status(root,email):
    token=read_secret(root,'google-token.secret')
    with LOCK: flow={k:v for k,v in FLOW.items() if k in ('status','message')}
    return {'configured':bool(read_secret(root,'google-client.secret')),
            'connected':bool(token and token.get('refresh_token') and token.get('email','').lower()==email.lower()),
            'email':token.get('email') if token else None,'flow':flow}

def start(root,email):
    client=read_secret(root,'google-client.secret')
    if not client: raise ValueError('Set up the Google Desktop OAuth credentials first.')
    with LOCK:
        if FLOW.get('status')=='waiting' and time.time()-FLOW.get('started',0)<600:
            raise ValueError('Google sign-in is already waiting in your browser. Finish or wait ten minutes before trying again.')
        FLOW.clear(); FLOW.update(status='waiting',message='Finish Google sign-in in your system browser.',started=time.time())
    state=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(64)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            params=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            supplied=params.get('state',[''])[0]
            if urllib.parse.urlsplit(self.path).path!='/callback' or not secrets.compare_digest(supplied,state):
                self.send_response(400); self.end_headers(); self.wfile.write(b'Invalid sign-in callback. Return to JobPilot.'); return
            try:
                if time.time()-FLOW.get('started',0)>600: raise ValueError('Sign-in expired. Try again.')
                if 'error' in params: raise ValueError('Google sign-in was cancelled or denied.')
                code=params.get('code',[''])[0]
                if not code: raise ValueError('Google did not return an authorization code.')
                token=request_json(TOKEN,form={'client_id':client['client_id'],'client_secret':client['client_secret'],
                    'code':code,'code_verifier':verifier,'redirect_uri':redirect,'grant_type':'authorization_code'})
                if not token.get('access_token'): raise ValueError('Google did not return an access token.')
                if 'https://www.googleapis.com/auth/gmail.send' not in token.get('scope','').split():
                    raise ValueError('Permission to send mail was not granted. Reconnect and allow sending.')
                who=request_json(USERINFO,access=token['access_token'])
                if who.get('email','').lower()!=email.lower() or not who.get('email_verified'):
                    raise ValueError('Sign in with '+email+' so applications use the intended account.')
                if not token.get('refresh_token'): raise ValueError('Offline access was not granted. Reconnect and allow the requested access.')
                token['email']=who['email']; token['expires_at']=time.time()+int(token.get('expires_in',3600))
                write_secret(root,'google-token.secret',token)
                with LOCK: FLOW.update(status='connected',message='Google account connected: '+email)
                message='Google account connected. You can close this tab and return to JobPilot.'
            except Exception as exc:
                message=str(exc)
                with LOCK: FLOW.update(status='error',message=message)
            server.completed=True
            self.send_response(200); self.send_header('Content-Type','text/plain; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(message.encode())
    server=HTTPServer(('127.0.0.1',0),Callback); server.timeout=1; server.completed=False
    redirect=f'http://127.0.0.1:{server.server_port}/callback'
    url=AUTH+'?'+urllib.parse.urlencode({'client_id':client['client_id'],'redirect_uri':redirect,'response_type':'code',
        'scope':SCOPES,'state':state,'code_challenge':challenge,'code_challenge_method':'S256',
        'access_type':'offline','prompt':'consent','login_hint':email})
    def listen():
        try:
            deadline=time.time()+600
            while not server.completed and time.time()<deadline: server.handle_request()
            if not server.completed:
                with LOCK: FLOW.update(status='error',message='Sign-in expired. Try again.')
        finally: server.server_close()
    threading.Thread(target=listen,daemon=True).start()
    webbrowser.open(url)
    return {'started':True,'message':'Finish the Google permission screen in your system browser.'}

def access_token(root,email):
    token=read_secret(root,'google-token.secret'); client=read_secret(root,'google-client.secret')
    if not token or not client or token.get('email','').lower()!=email.lower(): raise ValueError('Connect '+email+' with Sign in with Google first.')
    if float(token.get('expires_at',0))<=time.time()+60:
        result=request_json(TOKEN,form={'client_id':client['client_id'],'client_secret':client['client_secret'],
            'refresh_token':token['refresh_token'],'grant_type':'refresh_token'})
        if not result.get('access_token'): raise ValueError('Reconnect Google: token renewal failed.')
        token.update(result); token['expires_at']=time.time()+int(result.get('expires_in',3600))
        write_secret(root,'google-token.secret',token)
    return token['access_token']

def test_connection(root,email):
    who=request_json(USERINFO,access=access_token(root,email))
    if who.get('email','').lower()!=email.lower(): raise ValueError('Connected Google account does not match the sending address.')
    return {'ok':True,'message':'Google sign-in verified for '+email+'. No email sent.'}

def send(root,email,message):
    raw=base64.urlsafe_b64encode(message.as_bytes()).decode()
    receipt=request_json(SEND,payload={'raw':raw},access=access_token(root,email))
    if not receipt.get('id'): raise RuntimeError('Google returned no message ID; verify Sent mail before retrying.')
    return 'Gmail API accepted message '+str(receipt['id'])+'; employer receipt not independently confirmed'
