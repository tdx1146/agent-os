# handlers/session_handler.py — 会话管理

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from edit_web_merged import *

def handle_session_get(handler, path, clean_path):
    qkey = handler._get_query_param('key') or handler._get_query_param('sessionKey') or ''
    if qkey:
        old_key = get_active_session_key()
        set_active_session_key(qkey)
        data = handler._get_session_data()
        set_active_session_key(old_key)
        handler._send_json(200, data)
    else:
        handler._send_json(200, handler._get_session_data())

def handle_session_rpc(handler):
    handler._handle_session_rpc()

def handle_list_sessions(handler):
    handler._send_json(200, list_all_sessions())

def handle_switch_session(handler):
    key = handler._get_query_param('key') or handler._get_query_param('sessionKey') or ''
    set_active_session_key(key if key else None)
    handler._send_json(200, handler._get_session_data())

def handle_delete_session(handler):
    key = handler._get_query_param('key') or handler._get_query_param('sessionKey') or ''
    handler._handle_delete_session(key)

def handle_edit(handler):
    handler._handle_api('edit')

def handle_trim_session(handler):
    handler._handle_trim_session()
