# handlers/momo_handler.py — 消化/摸摸

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from edit_web_merged import *

def handle_momo(handler):
    handler._update_last_user_msg()
    _req_t0 = __import__('time').time()
    handler._handle_api('momo')
    _req_t1 = __import__('time').time()
    print(f"[timing] FULL /api/momo: {_req_t1-_req_t0:.3f}s", file=sys.stderr)
