"""Conservative browser adapter: fills known facts; submits only complete ordinary forms."""
import json, re, unicodedata
from pathlib import Path

def clean_label(value):
    value=re.sub(r'([a-z])([A-Z])',r'\1 \2',value)
    s=''.join(c for c in unicodedata.normalize('NFKD',value).lower() if not unicodedata.combining(c))
    s=re.sub(r'[_\-*?:]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def supplied_answer(label,profile):
    key=clean_label(label)
    return next((value for question,value in profile.get('answers',{}).items() if clean_label(question)==key),None)

FIELD_INFO='''e=>{
 const labelText=l=>{if(!l)return '';const copy=l.cloneNode(true);copy.querySelectorAll('input,select,textarea,button').forEach(x=>x.remove());return copy.textContent.trim()};
 return {tag:e.tagName,type:e.type,name:e.name,id:e.id,required:e.required||e.getAttribute('aria-required')==='true',aria:e.getAttribute('aria-label'),placeholder:e.getAttribute('placeholder'),labels:Array.from(e.labels||[]).map(labelText).join(' ')||((e.getAttribute('aria-labelledby')||'').split(' ').map(id=>document.getElementById(id)?.innerText||'').join(' ')).trim()||labelText(e.closest('label')),value:e.value}
}'''

def apply(job,profile,root,headless=True):
    try: from playwright.sync_api import sync_playwright
    except ImportError: return {'status':'blocked','reason':'Browser dependency missing. Run Setup.cmd.'}
    clicked=False
    import os
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(root/'browsers'))
    with sync_playwright() as pw:
        try: context=pw.chromium.launch_persistent_context(str(root/'browser-session'),headless=headless,accept_downloads=False)
        except Exception as e: return {'status':'blocked','reason':'Browser could not start: '+str(e)[:200]}
        page=context.new_page()
        try:
            page.goto(job['url'],wait_until='domcontentloaded',timeout=45000)
            # Follow an explicit application link once, not arbitrary navigation.
            if not page.locator('input[type="email"],input[type="file"]').count():
                links=page.get_by_role('link',name=re.compile(r'^(apply(?: for this (?:role|job))?(?: now)?|postuler(?: maintenant)?|deposer ma candidature)$',re.I))
                if links.count()==1:
                    old_pages=list(context.pages)
                    links.click(timeout=10000)
                    page.wait_for_load_state('domcontentloaded')
                    new_pages=[p for p in context.pages if p not in old_pages]
                    if new_pages: page=new_pages[-1]; page.wait_for_load_state('domcontentloaded')
            text=page.locator('body').inner_text(timeout=10000)
            if re.search(r'no longer accepting|position (?:is |has been )?closed|job expired',text,re.I): return {'status':'excluded','reason':'Employer posting closed'}
            if page.locator('iframe[src*="recaptcha"],iframe[src*="hcaptcha"]').count() or re.search(r'captcha|verify you are human|just a moment',page.title(),re.I):
                return {'status':'blocked','reason':'CAPTCHA or bot verification requires attention'}
            first,*rest=profile['name'].split(' ')
            known={r'^(full name|name|nom complet|prenom et nom)$':profile['name'],
                r'^(first name|prenom)$':first,r'^(last name|surname|nom)$':' '.join(rest),
                r'email|e-mail':profile['email'],r'phone|telephone|mobile number':profile['phone'],
                r'linkedin':profile['linkedin'],r'github':profile['github'],r'portfolio|personal (?:web)?site':profile['portfolio'],
                r'cover letter|message|motivation|parlez.nous':job['draft'],
                r'^(current location|location|city|ville)$':profile['current_location_from_resume'],
                r'^time ?zone$':'UTC+1'}
            for key,pattern in [('availability',r'availability|disponibilite'),('citizenship',r'citizenship|nationality|nationalite'),
                ('work_authorization',r'work authori[sz]ation'),('expected_hourly_rate',r'hourly rate|taux horaire'),
                ('salary_expectation',r'salary expectation|expected salary|salaire souhaite')]:
                if profile.get(key): known[pattern]=profile[key]
            missing=[]
            diagnostics=[]
            # Labels, placeholders and field names are visible form metadata, not generated answers.
            for field in page.locator('input,textarea,select').all():
                if not field.is_enabled(): continue
                info=field.evaluate(FIELD_INFO)
                typ=info['type'] or ''
                if typ in ('hidden','submit','button','reset'): continue
                label=next((str(info.get(k)).strip().rstrip('*').strip() for k in ('labels','aria','placeholder','name') if info.get(k)), '')
                label=clean_label(label)
                if typ=='file':
                    hint=label+' '+(info['name'] or '')+' '+(info['id'] or '')
                    if re.search(r'cover|motivation',hint,re.I):
                        letter=root/'drafts'/(job['id']+'-cover.txt'); letter.parent.mkdir(exist_ok=True)
                        letter.write_text(job['draft'],encoding='utf-8')
                        accept=field.get_attribute('accept') or ''
                        if accept and 'txt' not in accept and 'text/plain' not in accept:
                            if info['required']: missing.append('Cover letter upload requires another file format')
                        else: field.set_input_files(str(letter))
                    elif re.search(r'resume|curriculum|\bcv\b',hint,re.I) or page.locator('input[type="file"]').count()==1:
                        field.set_input_files(str(root/'RESUME.pdf'))
                    elif info['required']: missing.append(label or 'Unidentified document upload')
                    continue
                if not field.is_visible(): continue
                diagnostics.append({'label':label,'required':bool(info['required']),'type':typ})
                value=supplied_answer(label,profile) or next((v for k,v in known.items() if re.search(k,label,re.I)),None)
                if info['tag']=='SELECT':
                    if value:
                        options=field.locator('option').all_text_contents()
                        choices=[x for x in options if clean_label(x)==clean_label(value)]
                        if len(choices)==1: field.select_option(label=choices[0])
                    if info['required'] and not field.evaluate('e=>e.checkValidity()'): missing.append(label or 'required choice')
                    continue
                if typ in ('checkbox','radio') or info['tag']=='SELECT':
                    if info['required'] and not field.evaluate('e=>e.checkValidity()'): missing.append(label or 'required choice')
                    continue
                if value:
                    field.fill(value)
                elif info['required'] and not info['value']: missing.append(label or 'unlabelled required field')
            if missing:
                (root/'evidence'/(job['id']+'-questions.json')).write_text(json.dumps(diagnostics,indent=2),encoding='utf-8')
                return {'status':'blocked','reason':'Required answers unavailable: '+', '.join(missing[:6])}
            if re.search(r'by (?:submitting|applying).{0,120}(?:agree to.{0,30}terms|legally binding)|j.accepte.{0,80}conditions',text,re.I):
                return {'status':'blocked','reason':'Application requires agreement to terms; review required'}
            buttons=page.get_by_role('button',name=re.compile(r'^(submit(?: application)?|send application|apply(?: now)?|envoyer ma candidature|soumettre la demande)$',re.I))
            if buttons.count()!=1: return {'status':'blocked','reason':'No unambiguous supported submit button; inspect application page'}
            # Presence of a real applicant form is mandatory.
            if not page.locator('input[type="email"],input[type="file"]').count(): return {'status':'blocked','reason':'Application form was not reached'}
            invalid=page.locator('input:invalid,textarea:invalid,select:invalid')
            if invalid.count(): return {'status':'blocked','reason':'Form validation requires additional answers'}
            before=page.locator('body').inner_text()
            clicked=True; buttons.click(timeout=15000)
            try:
                page.get_by_text(re.compile(r'thank you for (?:applying|your (?:application|interest))|application (?:has been |was )?(?:received|submitted|sent)|candidature.{0,30}(?:recue|reçue|envoyee|envoyée)',re.I)).first.wait_for(timeout=20000)
                after=page.locator('body').inner_text()
                if after==before: raise RuntimeError('No new confirmation')
            except Exception: return {'status':'submission_uncertain','reason':'Submit clicked; no clear receipt. Verify before retrying.'}
            path=root/'evidence'/(job['id']+'.png'); page.screenshot(path=str(path),full_page=True)
            return {'status':'submitted','reason':'Employer form confirmed receipt','confirmation':str(path)}
        except Exception as e:
            return {'status':'submission_uncertain' if clicked else 'blocked','reason':f'Browser: {type(e).__name__}: {str(e)[:180]}'}
        finally: context.close()

def login(root):
    import os
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(root/'browsers'))
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx=pw.chromium.launch_persistent_context(str(root/'browser-session'),headless=False)
        page=ctx.new_page(); page.goto('https://www.linkedin.com/login')
        print('Use this browser to sign into job sites. Close it when finished.')
        page.wait_for_event('close',timeout=0); ctx.close()
