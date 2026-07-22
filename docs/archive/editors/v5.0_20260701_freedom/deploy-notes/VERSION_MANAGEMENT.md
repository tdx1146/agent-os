# 版本管理规则

## 版本号规则
- MAJOR.MINOR：v4.1 → v4.2 → v4.3 ...
- MAJOR 大版本（架构变更）
- MINOR 小版本（功能修复）

## 更新版本的流程
1. 改 `utils/version.py` 中的 VERSION 和 VERSION_DATE
2. 改完后重启编辑器验证标题
3. 执行 v4.2 完整备份（见下方"创建新版备份"）
4. 更新 VERSION 根目录文件
5. 更新 VERSION_INDEX.md

## 创建新版备份的流程
1. 确认所有文件清单（核心 ~8 个 + 辅助 ~37 个）
2. 复制到 `编辑器所有版本/v<version>_<date>_<description>/`
3. diff 验证一致性
4. 更新 VERSION_INDEX.md
5. 更新 scripts/revisions/revert-guide.md

## 修改代码前的流程
1. 备份要改的文件（cp file.py file.py.bak.$(date +%Y%m%d_%H%M)）
2. 改代码
3. 验证
4. 写 deploy-notes 记录改动
5. 更新 revisions 目录
