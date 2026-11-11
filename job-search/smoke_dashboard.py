"""Check the running dashboard and save a review screenshot; no employer interaction."""
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
root=Path(__file__).resolve().parent
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(root/'browsers')
try:
    urlopen(Request('http://127.0.0.1:8765/api/settings',data=b'{}',headers={'Content-Type':'application/json'}))
    raise AssertionError('Unauthenticated mutation was accepted')
except HTTPError as e: assert e.code==403
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1280,'height':900})
    page.goto('http://127.0.0.1:8765')
    page.get_by_role('button',name='Settings & connections',exact=True).click()
    page.get_by_label('SMTP server',exact=True).wait_for()
    assert page.get_by_label('Submit matching applications automatically',exact=True).is_checked()
    assert page.get_by_role('button',name='Open job-site browser',exact=True).is_visible()
    assert page.locator('#savedanswers').is_visible()
    assert page.get_by_role('button',name='Sign in with Google',exact=True).is_visible()
    assert page.get_by_label('Google Desktop OAuth credentials JSON',exact=True).count()==1
    page.screenshot(path=str(root/'evidence'/'jobpilot-settings.png'),full_page=False)
    page.get_by_role('button',name='Applications',exact=True).click()
    assert page.locator('#filter').input_value()=='active'
    page.screenshot(path=str(root/'evidence'/'jobpilot-dashboard.png'),full_page=False)
    browser.close()
print('Dashboard controls, mutation protection, and screenshots verified.')
