"""轻如烟编辑器 — 版本号唯一数据源"""

VERSION = "v5.0"
VERSION_DATE = "2026-07-01"
VERSION_TAG = "自由王国 (Freedom First)"
VERSION_FULL = f"轻如烟 {VERSION}「{VERSION_TAG}」— {VERSION_DATE}"
DELIVER = True


def get_version():
    """返回版本字典，供 /api/version 端点使用"""
    return {
        "version": VERSION,
        "date": VERSION_DATE,
        "tag": VERSION_TAG,
        "full": f"轻如烟 {VERSION} - {VERSION_DATE}",
        "deliver": DELIVER,
    }
