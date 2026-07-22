# handlers/router.py — 路由分发
_M = None
def g(name): return getattr(_M, name, None) if _M else None

from handlers.crypto_handler import (
    handle_encrypt, handle_encrypt_status, handle_encrypt_save_file,
    handle_pass_password, handle_encrypt_folders, handle_decrypt,
)
from handlers.file_handler import (
    handle_tb_files, handle_tb_read_file, handle_tb_save_file,
    handle_tb_create_file, handle_tb_delete_file, handle_tb_rename_file,
    handle_list_files, handle_browse_dirs,
)
from handlers.system_handler import (
    handle_usage_status, handle_cache_stats, handle_quickcheck,
    handle_list_subagents, handle_thinking_toggle, handle_weaponry_toggle,
)
from handlers.helper_handler import (
    handle_memory_file_get, handle_memory_file_list, handle_memory_file_save,
    handle_secretary_log, handle_facts_stale_check, handle_reminders,
    handle_read_facts,
)
from handlers.awake_handler import (
    handle_awake_list, handle_awake_save, handle_awake_send,
    handle_awake_questions, handle_tts,
)
from handlers.session_handler import (
    handle_get_session_data, handle_delete_session, handle_trim_session,
    handle_session_rpc, handle_list_backups, handle_restore_backup,
    handle_update_last_user_msg, handle_cleanup_inject_lock,
)
from handlers.inject_handler import (
    handle_inject, handle_edit, handle_clear_lock, handle_pulse,
    handle_spawn_subagent, handle_auth_subagent, handle_exec_subagent,
    handle_abort, handle_restart_http,
)
from handlers.momo_handler import handle_momo, handle_pet_me

def get(handler):
    cp = handler.path.split('?')[0]
    st = lambda d: handler._send_json(200, d)
    
    if cp == '/api/status': return st(handle_usage_status(handler))
    if cp == '/api/cache-stats': return st(handle_cache_stats(handler))
    if cp == '/api/list-sessions': 
        fn = g('list_all_sessions')
        return st(fn()) if fn else handler._send_json(404, {})
    if cp == '/api/system-health':
        fn = g('_system_health')
        return st(fn()) if fn else handler._send_json(404, {})
    if cp == '/api/switch-session':
        ss = g('set_active_session_key')
        key = handler._get_query_param('key') or ''
        if ss: ss(key or None)
        return st(handle_get_session_data(handler))
    if cp == '/api/delete-session':
        return handle_delete_session(handler)
    if cp.startswith('/api/session'):
        qkey = handler._get_query_param('key') or ''
        if qkey:
            ok = g('get_active_session_key')
            ss = g('set_active_session_key')
            old = ok() if ok else None
            if ss: ss(qkey)
            data = handle_get_session_data(handler)
            if ss and old: ss(old)
            return st(data)
        return st(handle_get_session_data(handler))
    if cp == '/api/session-rpc': return handle_session_rpc(handler)
    
    # — 一对一的 mapping (module-level functions, not handler methods) —
    for p, f in [
        ('/api/digestion-status', '_digestion_status'),
        ('/api/digestion-skill', '_digestion_skill_status'),
        ('/api/digestion-history', '_digestion_history'),
        ('/api/backlog', '_backlog_status'),
        ('/api/backup-stale', '_backup_stale_status'),
        ('/api/thinking-status', '_thinking_status'),
        ('/api/weaponry-toggle', '_weaponry_toggle_status'),
        ('/api/plugin-health', '_plugin_health'),
        ('/api/last-injection', '_last_injection'),
        ('/api/last-processing', '_last_processing'),
        ('/api/subagent-history', '_get_subagent_history'),
    ]:
        if cp == p:
            fn = g(f)
            if fn: return st(fn())
    
    if cp.startswith('/api/tb-files'): return handle_tb_files(handler)
    if cp.startswith('/api/tb-read-file'): return handle_tb_read_file(handler)
    if cp.startswith('/api/tb-save-file'): return handle_tb_save_file(handler)
    if cp.startswith('/api/tb-create-file'): return handle_tb_create_file(handler)
    if cp.startswith('/api/tb-rename-file'): return handle_tb_rename_file(handler)
    if cp.startswith('/api/tb-delete-file'): return handle_tb_delete_file(handler)
    if cp.startswith('/api/list-files'): return handle_list_files(handler)
    if cp.startswith('/api/browse-dirs'): return handle_browse_dirs(handler)
    if cp.startswith('/api/encrypt'): return handle_encrypt(handler)
    if cp == '/api/memory-files': return handle_memory_file_list(handler)
    if cp.startswith('/api/memory-file'): return handle_memory_file_get(handler)
    
    if cp == '/api/quickcheck': return st(handle_quickcheck(handler))
    if cp == '/api/secretary-log': return handle_secretary_log(handler)
    if cp == '/api/facts-stale': return handle_facts_stale_check(handler)
    if cp == '/api/reminders': return handle_reminders(handler)
    if cp == '/api/backups': return st(handle_list_backups(handler))
    if cp == '/api/subagents': return st(handle_list_subagents(handler))
    if cp == '/api/awake-questions/list': return handle_awake_list(handler)
    if cp == '/paper-annotated.html':
        import os as _o
        cs = [_o.path.join(g('LIGHT_SMOKE_DIR') or '', '..', '..', '牛马工作', '沈总论文', '论文_AI高频词标注.html'),
              '/vol1/@team/qh团队/QH/AI专用/牛马工作/沈总论文/论文_AI高频词标注.html']
        for c in cs:
            if _o.path.exists(c): return handler._serve_static_file(c, 'text/html; charset=utf-8')
        return st({'ok': False, 'error': '论文文件不存在'})
    if cp == '/':
        fn = g('_get_html_page')
        if fn:
            page = fn().encode(); import gzip
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/html; charset=utf-8')
            handler.send_header('Cache-Control', 'no-cache')
            if 'gzip' in handler.headers.get('Accept-Encoding', ''):
                page = gzip.compress(page)
                handler.send_header('Content-Encoding', 'gzip')
            handler.send_header('Vary', 'Accept-Encoding')
            handler.end_headers()
            return handler.wfile.write(page)
        return handler._send_json(500, {'ok': False})
    if cp.startswith('/static/'):
        d = g('_THIS_DIR')
        if d:
            fp = __import__('os').path.join(d, cp.lstrip('/'))
            if __import__('os').path.exists(fp):
                ext = __import__('os').path.splitext(fp)[1]
                mt = {'.js': 'application/javascript; charset=utf-8',
                      '.css': 'text/css; charset=utf-8',
                      '.html': 'text/html; charset=utf-8',
                      '.png': 'image/png', '.jpg': 'image/jpeg',
                      '.svg': 'image/svg+xml'}.get(ext, 'application/octet-stream')
                return handler._serve_static_file(fp, mt)
        return handler._send_json(404, {'ok': False, 'error': 'File not found'})
    
    handler._send_json(404, {'ok': False, 'error': 'not found'})

def post(handler):
    cp = handler.path.split('?')[0]
    if cp == '/api/abort': return handle_abort(handler)
    if cp == '/api/restart-http': return handle_restart_http(handler)
    if cp == '/api/pet-me': return handle_pet_me(handler)
    if cp == '/api/trim-session': return handle_trim_session(handler)
    if cp == '/api/thinking-toggle': return handle_thinking_toggle(handler)
    if cp == '/api/weaponry-toggle': return handle_weaponry_toggle(handler)
    if cp == '/api/inject': return handle_inject(handler)
    if cp == '/api/edit': return handle_edit(handler)
    if cp == '/api/clear-inject-lock': return handle_clear_lock(handler)
    if cp == '/api/pulse': return handle_pulse(handler)
    if cp == '/api/momo':
        handle_update_last_user_msg(handler)
        return handle_momo(handler)
    if cp == '/api/spawn-subagent': return handle_spawn_subagent(handler)
    if cp == '/api/auth-subagent': return handle_auth_subagent(handler)
    if cp == '/api/exec-subagent': return handle_exec_subagent(handler)
    if cp == '/api/reminders': return handle_reminders(handler)
    if cp == '/api/memory-file': return handle_memory_file_save(handler)
    if cp == '/api/awake-questions/list': return handle_awake_list(handler)
    if cp == '/api/awake-questions/save': return handle_awake_save(handler)
    if cp == '/api/tts': return handle_tts(handler)
    if cp.startswith('/api/encrypt'): return handle_encrypt(handler)
    if cp.startswith('/api/tb-save-file'): return handle_tb_save_file(handler)
    if cp.startswith('/api/tb-create-file'): return handle_tb_create_file(handler)
    if cp.startswith('/api/tb-rename-file'): return handle_tb_rename_file(handler)
    if cp.startswith('/api/tb-delete-file'): return handle_tb_delete_file(handler)
    if cp == '/api/memory-file': return handle_memory_file_save(handler)
    if cp == '/api/quickcheck': return handler._send_json(200, handle_quickcheck(handler))
    handler._send_json(404, {'ok': False, 'error': 'not found'})
