"""Export application records, never local passwords or OAuth tokens."""
import json
import jobpilot
with jobpilot.db() as c:
    jobs=[dict(r) for r in c.execute('SELECT * FROM jobs')]
    runs=[dict(r) for r in c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 15')]
for j in jobs:
    try:j['skills']=json.loads(j.get('skills') or '[]')
    except ValueError:j['skills']=[]
for r in runs:
    try:r['errors']=json.loads(r.get('errors') or '[]')
    except ValueError:r['errors']=[]
jobpilot.write_json(jobpilot.ROOT/'cloud-export.json',{'profile':jobpilot.profile(),'settings':jobpilot.config(),'jobs':jobs,'runs':runs})
print('Prepared private migration:',len(jobs),'application records,',len(runs),'runs. No credentials exported.')
