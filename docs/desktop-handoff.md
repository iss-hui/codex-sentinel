# 桌面交接与执行进程清理

2026-10-03（Asia/Tokyo）。

## 发现与修正

GUI 原先在调度和执行器两处遇到锁即等待，没有连接旧版的自动关闭桌面、结束后重开流程。执行器只有在 CLI 进程退出后才解析完成事件，也只在取消或超时时清理当时能枚举到的子进程；这不能保证主进程先退出后遗留的后台进程被回收。

新流程默认开启，可在设置中关闭：

1. 目标会话被占用时，根据程序路径识别 Codex 桌面，停止其主管进程和后台进程树。此操作会中断桌面内正在执行的任务。
2. 确认会话锁释放后，按明确的会话 ID 执行任务。无法识别桌面或无法释放锁时，不启动任务，也不反复强杀重试。
3. 实时解析 CLI 顶层 `turn.completed` / `turn.failed`。完成后给进程 2 秒正常退出时间，随后清理本次启动的全部执行进程。命令输出中出现同名文字不算完成事件。
4. Windows 使用独立 Job Object；CLI 以挂起状态启动，加入 Job 后才恢复运行，子进程随 Job 管理。Job 设置 `KILL_ON_JOB_CLOSE`，Sentinel 异常退出也会触发回收。正常结束时等待 Job 内进程归零并确认会话锁释放。
5. 清理完成后，重新打开本次关闭的 Codex 桌面。成功、失败和取消都会清理；清理失败会暂停队列并显示原因。已收到完成事件的任务保持已完成，避免误导用户重复执行。

设置项 `take_over_desktop` 默认 `true`。Sentinel 监控窗口继续运行；被回收的是它启动的 CLI 和执行子进程。GUI 不再调用旧版按进程名称批量终止所有 Codex/ChatGPT 的实现。Windows MSIX 重开入口已对照本机 AppxManifest 的 `Application Id="App"` 核实。

## 验证

使用模拟 CLI 和实际 Python 子进程验证：完成但不退出、父进程先退出而子进程持锁、失败终止事件、半行 JSON、取消/超时、交接后启动失败、锁未释放、错误会话 ID、GUI 完成状态及清理失败暂停。未强制关闭当前实际 Codex 桌面，也未发送真实模型请求。

57 项 pytest 测试通过，Ruff 致命错误检查通过。原用户日志没有 `turn.completed`，保存的结果是取消，因此未把那次“执行中”直接判断为错误；本次已用可重复的模拟场景验证并修正完成后进程滞留问题。

实现依据：[Microsoft Job Objects 文档](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) 与[挂起启动后加入 Job 的说明](https://devblogs.microsoft.com/oldnewthing/20131209-00/?p=2433)。
