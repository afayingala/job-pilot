"""Additional public employer feeds and conservative geographic eligibility."""
import re

def eligible_location(location,remote=False):
    s=location.lower()
    if 'douala' in s: return True
    return bool(remote and re.search(r'\b(worldwide|anywhere|global|africa|emea|cameroon)\b',s))

def postings(source,data):
    company=source.get('company') or source['url'].split('/')[-1].split('?')[0]
    if source['type']=='lever':
        for v in data:
            cat=v.get('categories',{}); loc=cat.get('location','')
            text=v.get('descriptionPlain','')+' '+v.get('additionalPlain','')
            text+=' '+' '.join(x.get('content','') for x in v.get('lists',[]))
            yield {'title':v['text'],'company':company,'url':v.get('applyUrl') or v['hostedUrl'],
                'source_url':v['hostedUrl'],'source':'Employer','description':text,'location':loc,
                'eligible':eligible_location(loc,v.get('workplaceType')=='remote')}
    elif source['type']=='ashby':
        for v in data.get('jobs',[]):
            if not v.get('isListed',True): continue
            loc='; '.join([v.get('location','')]+[x.get('location','') for x in v.get('secondaryLocations',[])])
            yield {'title':v['title'],'company':company,'url':v.get('applyUrl') or v['jobUrl'],
                'source_url':v['jobUrl'],'source':'Employer','description':v.get('descriptionPlain') or v.get('descriptionHtml',''),
                'location':loc,'eligible':eligible_location(loc,v.get('isRemote',False))}

def source_for(url,company=''):
    from urllib.parse import urlsplit
    p=urlsplit(url); parts=[x for x in p.path.split('/') if x]
    if p.hostname in ('jobs.lever.co','jobs.eu.lever.co') and parts:
        host='api.eu.lever.co' if '.eu.' in p.hostname else 'api.lever.co'
        return {'type':'lever','company':company or parts[0],'url':f'https://{host}/v0/postings/{parts[0]}?mode=json'}
    if p.hostname=='jobs.ashbyhq.com' and parts:
        return {'type':'ashby','company':company or parts[0],'url':f'https://api.ashbyhq.com/posting-api/job-board/{parts[0]}'}
    if p.hostname in ('boards.greenhouse.io','job-boards.greenhouse.io') and parts:
        return {'type':'greenhouse','company':company or parts[0],'url':f'https://boards-api.greenhouse.io/v1/boards/{parts[0]}/jobs?content=true'}
    return None
