"""Verify candidate employer feeds before adding them to the local settings."""
import json
import jobpilot
SOURCES=[
 {'type':'lever','company':'Binance','url':'https://api.lever.co/v0/postings/binance?mode=json'},
 {'type':'ashby','company':'Ashby','url':'https://api.ashbyhq.com/posting-api/job-board/Ashby'},
 {'type':'greenhouse','company':'GitLab','url':'https://boards-api.greenhouse.io/v1/boards/gitlab/jobs?content=true'}]
if __name__=='__main__':
    cfg=jobpilot.config()
    for source in SOURCES:
        try:
            data=jobpilot.cached_json(source['url'])
            jobs=data if isinstance(data,list) else data.get('jobs',[])
            if not jobs: raise ValueError('No published jobs returned')
            if not any(s['url']==source['url'] for s in cfg['sources']): cfg['sources'].append(source)
            print(source['company'],len(jobs),'published jobs; enabled')
        except Exception as e: print(source['company'],'not enabled:',str(e))
    jobpilot.write_json(jobpilot.ROOT/'settings.json',cfg)
