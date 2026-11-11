import base64,json,tempfile,time,unittest,urllib.parse,urllib.request
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch
import google_mail as gm

CLIENT={'client_id':'fixture.apps.googleusercontent.com','client_secret':'fixture-only'}
class GoogleTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def test_requires_desktop_credentials(self):
        with self.assertRaises(ValueError): gm.save_client(self.root,{'web':CLIENT})
        with patch.object(gm,'write_secret') as save:
            gm.save_client(self.root,{'installed':CLIENT}); save.assert_called_once()
    def test_refresh_preserves_offline_token(self):
        token={'email':'candidate@example.com','refresh_token':'fixture-refresh','access_token':'old','expires_at':0}
        with patch.object(gm,'read_secret',side_effect=[token,CLIENT]),patch.object(gm,'request_json',return_value={'access_token':'new','expires_in':3600}),patch.object(gm,'write_secret') as save:
            self.assertEqual(gm.access_token(self.root,'candidate@example.com'),'new')
            self.assertEqual(save.call_args.args[2]['refresh_token'],'fixture-refresh')
    def test_wrong_account_cannot_send(self):
        with patch.object(gm,'read_secret',side_effect=[{'email':'other@example.com'},CLIENT]):
            with self.assertRaises(ValueError): gm.access_token(self.root,'candidate@example.com')
    def test_gmail_api_sends_mime_and_requires_receipt(self):
        msg=EmailMessage();msg['To']='employer@example.com';msg.set_content('Fixture application')
        with patch.object(gm,'access_token',return_value='fixture'),patch.object(gm,'request_json',return_value={'id':'gmail-fixture-id'}) as send:
            self.assertIn('gmail-fixture-id',gm.send(self.root,'candidate@example.com',msg))
            raw=send.call_args.kwargs['payload']['raw']; self.assertIn(b'employer@example.com',base64.urlsafe_b64decode(raw))
        with patch.object(gm,'access_token',return_value='fixture'),patch.object(gm,'request_json',return_value={}):
            with self.assertRaises(RuntimeError): gm.send(self.root,'candidate@example.com',msg)
    def test_callback_pkce_state_and_account_verification(self):
        with gm.LOCK: gm.FLOW.clear()
        scopes=gm.SCOPES
        token={'access_token':'fixture-token','refresh_token':'fixture-refresh','expires_in':3600,'scope':scopes}
        with patch.object(gm,'read_secret',return_value=CLIENT),patch.object(gm,'write_secret') as save,patch.object(gm,'request_json',side_effect=[token,{'email':'candidate@example.com','email_verified':True}]) as exchange,patch.object(gm.webbrowser,'open') as launch:
            gm.start(self.root,'candidate@example.com')
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(launch.call_args.args[0]).query)
            self.assertEqual(q['code_challenge_method'],['S256']); self.assertNotIn('gmail.readonly',scopes)
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(q['redirect_uri'][0]+'?state=wrong&code=fixture',timeout=5)
            save.assert_not_called()
            callback=q['redirect_uri'][0]+'?'+urllib.parse.urlencode({'state':q['state'][0],'code':'fixture-code'})
            with urllib.request.urlopen(callback,timeout=5) as r: self.assertIn(b'account connected',r.read())
            save.assert_called_once(); self.assertEqual(save.call_args.args[2]['email'],'candidate@example.com')
            self.assertIn('code_verifier',exchange.call_args_list[0].kwargs['form'])
        with gm.LOCK: gm.FLOW.clear()

if __name__=='__main__':unittest.main()
