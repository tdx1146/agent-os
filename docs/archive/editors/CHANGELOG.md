# 轻如烟编辑器·CHANGELOG

## v4.2 (2026-06-27)

**修复 deliver:true 缺失 + fire-and-forget 恢复**

### 变更内容
- 修复 inject_handler 中 `deliver` 参数未正确传递的问题
- 恢复 fire-and-forget 模式，确保消息立即投递
- 优化前端超时重试逻辑

---

## v4.1 (2026-06-26)

**Inject Fix：subprocess.run + 前端超时重试 + 清除守护冲突**

### 变更内容
- 使用 `subprocess.run()` 替代旧版子进程调用
- 添加前端请求超时自动重试机制（最多3次）
- 清理残留的守护进程冲突
- 优化 handlers 执行顺序和异常处理

---

## v4 (2026-06-25)

**架构重构：真正分离 handlers/utils 双轨清理**

### 变更内容
- 完成 handlers 与 utils 的真正分离
- 统一配置管理（config.json）
- 实现 cache_stats 监控模块
- 完善 error handling 和日志记录
