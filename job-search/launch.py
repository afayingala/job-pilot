"""Open the dashboard, reusing an existing server when it is already running."""
import json, subprocess, sys, time, urllib.request, webbrowser
from pathlib import Path
root=Path(__file__).resolve().parent
url='http://127.0.0.1:8765'
def ready():
    try:
        with urllib.request.urlopen(url+'/api/state',timeout=1) as r:
            return 'schedule' in json.load(r)
    except Exception: return False
if not ready():
    (root/'logs').mkdir(exist_ok=True)
    with (root/'logs'/'dashboard.log').open('a') as out, (root/'logs'/'dashboard-error.log').open('a') as err:
        subprocess.Popen([sys.executable,str(root/'jobpilot.py'),'--serve'],cwd=str(root),
                         creationflags=subprocess.CREATE_NO_WINDOW,stdout=out,stderr=err)
    for _ in range(30):
        if ready(): break
        time.sleep(.2)
    else:
        print('JobPilot could not start. See logs/dashboard-error.log.'); sys.exit(1)
webbrowser.open(url)
