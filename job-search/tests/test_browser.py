import os, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from browser_apply import apply
from test_jobpilot import PROFILE

FORM='''<html><body><h1>Fixture vacancy</h1><form method="POST">
<label>Full name<input name="name" required></label><label>Email<input name="email" type="email" required></label>
<label>Cover letter<textarea name="letter" required></textarea></label><label>Resume<input name="resume" type="file" required></label>
EXTRA<button type="submit">Submit application</button></form></body></html>'''
class Fixture(BaseHTTPRequestHandler):
    extra=''; submissions=[]
    def log_message(self,*a): pass
    def do_GET(self):
        body=FORM.replace('EXTRA',self.extra).encode(); self.send_response(200); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        self.submissions.append(self.rfile.read(int(self.headers.get('Content-Length',0))))
        self.send_response(200); self.end_headers(); self.wfile.write(b'<html><body><h1>Thank you for applying</h1><p>Your application has been received.</p></body></html>')

class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(Path(__file__).resolve().parents[1]/'browsers')
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        (self.root/'evidence').mkdir(); (self.root/'RESUME.pdf').write_bytes(b'%PDF-1.4 fixture resume')
        Fixture.extra=''; Fixture.submissions=[]
        self.job={'id':'fixture','url':f'http://127.0.0.1:{self.server.server_port}/','draft':'Application fixture'}
    def tearDown(self): self.tmp.cleanup()
    def test_complete_form_submits_and_saves_receipt(self):
        result=apply(self.job,PROFILE,self.root)
        self.assertEqual(result['status'],'submitted',result)
        self.assertEqual(len(Fixture.submissions),1)
        self.assertTrue((self.root/'evidence'/'fixture.png').exists())
    def test_unknown_required_question_never_submits(self):
        Fixture.extra='<label>Salary expectation<input name="salary" required></label>'
        result=apply(self.job,PROFILE,self.root)
        self.assertEqual(result['status'],'blocked',result); self.assertEqual(len(Fixture.submissions),0)
    def test_binding_terms_not_accepted(self):
        Fixture.extra='<p>By submitting you agree to our terms of service.</p>'
        result=apply(self.job,PROFILE,self.root)
        self.assertEqual(result['status'],'blocked',result); self.assertEqual(len(Fixture.submissions),0)
    def test_aria_labelled_field_is_filled(self):
        Fixture.extra='<span id="site-label">Portfolio</span><input aria-labelledby="site-label" required>'
        result=apply(self.job,PROFILE,self.root)
        self.assertEqual(result['status'],'submitted',result)
    def test_hidden_resume_upload_is_supported(self):
        Fixture.extra='<input type="file" name="resume_attachment" style="display:none" required>'
        result=apply(self.job,PROFILE,self.root)
        self.assertEqual(result['status'],'submitted',result)
    def test_explicit_saved_select_answer_is_used(self):
        Fixture.extra='<label>Preferred working hours<select name="hours" required><option value="">Choose</option><option>Afternoons</option></select></label>'
        p=PROFILE|{'answers':{'Preferred working hours':'Afternoons'}}
        result=apply(self.job,p,self.root)
        self.assertEqual(result['status'],'submitted',result)

if __name__=='__main__': unittest.main()
