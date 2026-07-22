# 轻如烟编辑器 版本回滚指南

## 版本索引
| 版本 | 文件 | 日期 | 说明 |
|------|------|------|------|
| v1 | revisions/20260612_v1_editor-backup.py | 6/12 | 最早的分离尝试 |
| v2 | revisions/20260613_v2_zuixin.py | 6/13 | 第二次分离尝试 |
| v4 | 当前 scripts/edit-web.py | 当前 | 部分分离架构 |

## 回滚到 v1
```bash
cp scripts/revisions/20260612_v1_editor-backup.py scripts/edit-web.py
# 重启编辑器
```

## 回滚到 v2
```bash
cp scripts/revisions/20260613_v2_zuixin.py scripts/edit-web.py
# 重启编辑器
```

## 当前版本状态
- router.py 已分离 ✅
- utils/ 已分离 ✅
- handlers/ 为空壳 ❌
