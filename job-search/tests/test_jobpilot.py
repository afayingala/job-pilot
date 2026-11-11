import json, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
import jobpilot as jp

PROFILE={"name":"Test Candidate","email":"candidate@example.com","phone":"+237600000000",
 "current_location_from_resume":"Buea, Cameroon","portfolio":"https://example.com/portfolio","github":"https://github.com/example",
 "linkedin":"https://linkedin.com/in/example","degree":{"completed_confirmed":False},
 "skills":["React","TypeScript","Node.js","Python","Java"]}

def job(**overrides):
    return dict(title='Junior Frontend Developer',company='Example Employer',url='https://example.com/jobs/1',
        source='Employer',source_url='https://example.com/jobs/1',location='Douala',
        description='Build React and TypeScript apps with Node.js. Send your CV to careers@example.com.',eligible=True,**overrides)

class CoreTests(unittest.TestCase):
    def test_resume_match_and_location(self):
        score,skills,_=jp.match(job(),PROFILE)
        self.assertGreaterEqual(score,55); self.assertIn('React',skills); self.assertNotIn('Java',skills)
        other=job(); other.update(location='United States',eligible=False)
        self.assertEqual(jp.match(other,PROFILE)[0],0)
    def test_senior_expired_and_fluent_french_excluded(self):
        for field,value in [('title','Senior React Developer'),('deadline','2020-01-01'),('description','Fluent French required. React TypeScript')]:
            j=job(); j[field]=value; self.assertEqual(jp.match(j,PROFILE)[0],0)
    def test_only_explicit_unambiguous_application_email(self):
        self.assertIsNone(jp.application_email(jp.Page('<footer>Contact info@example.com</footer>')))
        self.assertEqual(jp.application_email(jp.Page('<p>Send your CV to careers@example.com</p>')),'careers@example.com')
        self.assertIsNone(jp.application_email(jp.Page('<p>Send your CV to a@example.com or b@example.com</p>')))
    def test_private_urls_rejected(self):
        for url in ('file:///etc/passwd','http://127.0.0.1/test','http://user:password@example.com','http://169.254.169.254/'):
            with self.assertRaises(ValueError): jp.validate_url(url)
    def test_nested_jobposting(self):
        obj={'@graph':[{'@type':'Organization'},{'@type':['JobPosting'],'title':'Developer'}]}
        self.assertEqual(len(list(jp.structured_jobs(obj))),1)
    def test_employer_deadlines(self):
        self.assertTrue(jp.expired(jp.page_deadline('Apply by March 31, 2025')))
        self.assertIn('2026-11-20',jp.page_deadline('Candidatures jusqu’au 20 novembre 2026'))
    def test_direct_employer_feed(self):
        data={'jobs':[{'title':'Junior Frontend Developer','absolute_url':'https://example.com/job',
                      'location':{'name':'Home based - Worldwide'},'content':'&lt;p&gt;React TypeScript&lt;/p&gt;'}]}
        with patch.object(jp,'cached_json',return_value=data):
            jobs,errors=jp.discover({'sources':[{'type':'greenhouse','url':'https://example.com/api','company':'Example'}]})
        self.assertFalse(errors); self.assertTrue(jobs[0]['eligible']); self.assertEqual(jobs[0]['source'],'Employer')
    def test_extra_sources_and_country_restrictions(self):
        from discovery import postings,source_for
        source={'type':'lever','url':'https://api.lever.co/v0/postings/example?mode=json','company':'Example'}
        data=[{'text':'Junior React Developer','categories':{'location':'Remote - United States'},'workplaceType':'remote','hostedUrl':'https://example.com/job'}]
        self.assertFalse(list(postings(source,data))[0]['eligible'])
        data[0]['categories']['location']='Remote - EMEA'
        self.assertTrue(list(postings(source,data))[0]['eligible'])
        self.assertEqual(source_for('https://jobs.ashbyhq.com/Example')['type'],'ashby')
    def test_draft_does_not_claim_graduation(self):
        j=job(); j['skills']='["React"]'
        text=jp.draft(j,PROFILE)
        self.assertIn('expected in December 2026',text); self.assertNotIn('I graduated',text)

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.rootpatch=patch.object(jp,'ROOT',self.root); self.rootpatch.start()
        jp.write_json(self.root/'profile.json',PROFILE); (self.root/'RESUME.pdf').write_bytes(b'%PDF fixture')
        jp.init()
    def tearDown(self): self.rootpatch.stop(); self.tmp.cleanup()
    def test_run_sends_once_and_skips_duplicate_url_variants(self):
        data=job()
        with patch.object(jp,'discover',return_value=([data],[])),patch.object(jp,'fetch',return_value=('<p>Send your CV to careers@example.com</p>',data['url'])),patch.object(jp,'password',return_value='not-a-real-secret'),patch.object(jp,'deliver_email',return_value='fixture SMTP accepted') as send:
            self.assertEqual(jp.run()['submitted'],1)
            duplicate=data|{'url':'https://example.com/jobs/1?source=another'}
            with patch.object(jp,'discover',return_value=([duplicate],[])):
                self.assertEqual(jp.run()['submitted'],0)
            self.assertEqual(send.call_count,1)
    def test_dry_run_never_sends(self):
        with patch.object(jp,'discover',return_value=([job()],[])),patch.object(jp,'deliver_email') as send:
            self.assertTrue(jp.run(dry=True)['dry_run']); send.assert_not_called()
            with jp.db() as c: self.assertTrue(c.execute('SELECT draft FROM jobs').fetchone()['draft'])
    def test_http_block_uses_browser_fallback(self):
        with patch.object(jp,'discover',return_value=([job()],[])),patch.object(jp,'fetch',side_effect=OSError('blocked')),patch('browser_apply.apply',return_value={'status':'blocked','reason':'Fixture CAPTCHA'}) as browser:
            jp.run(); self.assertEqual(browser.call_count,1)
            with jp.db() as c: self.assertEqual(c.execute('SELECT reason FROM jobs').fetchone()['reason'],'Fixture CAPTCHA')
    def test_retry_cooldown_uses_attempt_time_not_discovery_time(self):
        from datetime import datetime,timedelta
        with patch.object(jp,'discover',return_value=([job()],[])),patch.object(jp,'fetch',return_value=('<p>Apply here</p>','https://example.com')),patch('browser_apply.apply',return_value={'status':'blocked','reason':'Fixture CAPTCHA'}) as browser:
            jp.run()
            with jp.db() as c:
                c.execute('UPDATE jobs SET attempted_at=?,updated=?',((datetime.now(jp.TZ)-timedelta(hours=25)).isoformat(),jp.now()))
            jp.run(); jp.run()
            self.assertEqual(browser.call_count,2)
    def test_user_skip_survives_rediscovery(self):
        with patch.object(jp,'discover',return_value=([job()],[])):
            jp.run(dry=True)
            with jp.db() as c: c.execute("UPDATE jobs SET status='excluded',reason='Status updated by user'")
            jp.run(dry=True)
            with jp.db() as c: self.assertEqual(c.execute('SELECT status FROM jobs').fetchone()['status'],'excluded')
    def test_uncertain_delivery_never_automatically_retries(self):
        data=job()
        with patch.object(jp,'discover',return_value=([data],[])),patch.object(jp,'fetch',return_value=('<p>Send your CV to careers@example.com</p>',data['url'])),patch.object(jp,'password',return_value='fixture'),patch.object(jp,'deliver_email',side_effect=TimeoutError) as send:
            jp.run(); jp.run()
            self.assertEqual(send.call_count,1)
            with jp.db() as c: self.assertEqual(c.execute('SELECT status FROM jobs').fetchone()['status'],'submission_uncertain')
    def test_missing_credentials_block_without_attempt(self):
        data=job()
        with patch.object(jp,'discover',return_value=([data],[])),patch.object(jp,'fetch',return_value=('<p>Send your CV to careers@example.com</p>',data['url'])),patch.object(jp,'password',return_value=''),patch.object(jp,'deliver_email') as send:
            jp.run(); send.assert_not_called()
            with jp.db() as c: self.assertEqual(c.execute('SELECT status FROM jobs').fetchone()['status'],'blocked')
    def test_paused_run_releases_lease(self):
        jp.write_json(self.root/'settings.json',jp.DEFAULT|{'paused':True})
        self.assertTrue(jp.run()['paused'])
        with jp.db() as c: self.assertEqual(c.execute("SELECT COUNT(*) FROM slots WHERE slot='running'").fetchone()[0],0)
    def test_message_contains_resume_and_actual_recipient(self):
        j=job(); j.update(email='careers@example.com',draft='Fixture application')
        class FakeSMTP:
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def send_message(self,msg):
                self.msg=msg; return {}
        smtp=FakeSMTP()
        with patch.object(jp,'connect_smtp',return_value=smtp): receipt=jp.deliver_email(j,jp.DEFAULT,PROFILE)
        self.assertEqual(smtp.msg['To'],'careers@example.com')
        self.assertEqual(list(smtp.msg.iter_attachments())[0].get_content_type(),'application/pdf')
        self.assertIn('SMTP accepted',receipt)

if __name__=='__main__': unittest.main()
