# handlers/router.py — 路由分发
_M = None
def g(name): return getattr(_M, name, None) if _M else None

def get(handler):
    cp = handler.path.split('?')[0]
    st = lambda d: handler._send_json(200, d)
    
    if cp == '/api/status': return st(handler._get_usage_status())
    if cp == '/api/cache-stats': return st(handler._get_cache_stats())
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
        return st(handler._get_session_data())
    if cp == '/api/delete-session':
        key = handler._get_query_param('key') or ''
        return handler._handle_delete_session(key)
    if cp.startswith('/api/session'):
        qkey = handler._get_query_param('key') or ''
        if qkey:
            ok = g('get_active_session_key')
            ss = g('set_active_session_key')
            old = ok() if ok else None
            if ss: ss(qkey)
            data = handler._get_session_data()
            if ss and old: ss(old)
            return st(data)
        return st(handler._get_session_data())
    if cp == '/api/session-rpc': return handler._handle_session_rpc()
    
    # — 一对一的 mapping —
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
            m = getattr(handler, f, None)
            if m: return st(m())
    
    if cp.startswith('/api/tb-files'): return handler._handle_tb_files()
    if cp.startswith('/api/tb-read-file'): return handler._handle_tb_read_file()
    if cp.startswith('/api/tb-save-file'): return handler._handle_tb_save_file()
    if cp.startswith('/api/tb-create-file'): return handler._handle_tb_create_file()
    if cp.startswith('/api/tb-rename-file'): return handler._handle_tb_rename_file()
    if cp.startswith('/api/tb-delete-file'): return handler._handle_tb_delete_file()
    if cp.startswith('/api/list-files'): return handler._handle_list_files()
    if cp.startswith('/api/browse-dirs'): return handler._handle_browse_dirs()
    if cp.startswith('/api/encrypt'): return handler._handle_encrypt()
    if cp.startswith('/api/memory-file'): return handler._handle_memory_file_get()
    
    if cp == '/api/quickcheck': return st(handler._handle_quickcheck())
    if cp == '/api/memory-files': return handler._handle_memory_file_list()
    if cp == '/api/secretary-log': return handler._handle_secretary_log()
    if cp == '/api/facts-stale': return handler._handle_facts_stale_check()
    if cp == '/api/reminders': return handler._handle_reminders()
    if cp == '/api/backups': return st(handler._list_backups())
    if cp == '/api/subagents': return st(handler._list_subagents())
    if cp == '/api/awake-questions/list': return handler._handle_awake_list()
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
    if cp == '/api/abort': return handler._handle_abort()
    if cp == '/api/restart-http': return handler._handle_restart_http()
    if cp == '/api/pet-me': return handler._handle_pet_me()
    if cp == '/api/trim-session': return handler._handle_trim_session()
    if cp == '/api/thinking-toggle': return handler._handle_thinking_toggle()
    if cp == '/api/weaponry-toggle': return handler._handle_weaponry_toggle()
    if cp == '/api/inject': return handler._handle_api('inject')
    if cp == '/api/edit': return handler._handle_api('edit')
    if cp == '/api/clear-inject-lock': return handler._handle_api('clear_lock')
    if cp == '/api/pulse': return handler._handle_api('pulse')
    if cp == '/api/momo':
        handler._update_last_user_msg()
        return handler._handle_api('momo')
    if cp == '/api/spawn-subagent': return handler._handle_spawn_subagent()
    if cp == '/api/auth-subagent': return handler._handle_auth_subagent()
    if cp == '/api/exec-subagent': return handler._handle_exec_subagent()
    if cp == '/api/reminders': return handler._handle_reminders()
    if cp == '/api/memory-file': return handler._handle_memory_file_save()
    if cp == '/api/awake-questions/list': return handler._handle_awake_list()
    if cp == '/api/awake-questions/save': return handler._handle_awake_save()
    if cp.startswith('/api/encrypt'): return handler._handle_encrypt()
    if cp == '/api/quickcheck': return handler._send_json(200, handler._handle_quickcheck())
    handler._send_json(404, {'ok': False, 'error': 'not found'})
