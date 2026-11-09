"""Task Scheduler entry point with durable logs and no terminal window needed."""
import contextlib, os, sys
from datetime import datetime
from pathlib import Path
root=Path(__file__).resolve().parent
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(root/'browsers')
(root/'logs').mkdir(exist_ok=True)
with (root/'logs'/'scheduled.log').open('a',encoding='utf-8',buffering=1) as log:
    with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        print('\nRUN',datetime.now().isoformat())
        import jobpilot
        jobpilot.init()
        try: print(jobpilot.run())
        except Exception:
            import traceback
            traceback.print_exc()
            sys.exit(1)
