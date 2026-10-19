import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.gui.common import permission_text, status_text, time_text, tr
from codex_sentinel.gui.ui import (
    STATUS_ROLE,
    StatusDelegate,
    Toggle,
    card,
    heading,
    label,
)


class TaskQueuePage(QWidget):
    add_requested = Signal()
    edit_requested = Signal(str)
    delete_requested = Signal(str)
    retry_requested = Signal(str)
    move_requested = Signal(str, int)
    stop_requested = Signal()
    enabled_changed = Signal(bool)

    def __init__(self, parent=None, *, read_only=False):
        super().__init__(parent)
        self.tasks = []
        self.session_titles = {}
        self._detail_task_id = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        heading(
            layout,
            tr("自动化记录与日志", "Automation history and logs")
            if read_only
            else tr("执行队列", "Task queue"),
            tr(
                "查看执行目标、结果与 CLI 原始日志。",
                "Inspect targets, results and original CLI logs.",
            )
            if read_only
            else tr(
                "只管理用户预约；自动恢复与持续激活独立运行。",
                "Manages your schedules; recovery and activation run independently.",
            ),
        )
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        list_card, list_layout = card()
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)
        self.chk_auto = Toggle(tr("启用预约队列", "Enable scheduled queue"))
        self.chk_auto.toggled.connect(self.enabled_changed)
        self.chk_auto.setVisible(not read_only)
        top = QHBoxLayout()
        top.setContentsMargins(18, 12, 18, 12)
        top.addWidget(self.chk_auto)
        top.addStretch()
        self.lbl_count = label("", "hint")
        self.lbl_count.setWordWrap(False)
        top.addWidget(self.lbl_count)
        list_layout.addLayout(top)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                tr("名称", "Name"),
                tr("最早执行（含缓冲）", "Earliest run (with buffer)"),
                tr("模型", "Model"),
                tr("对话", "Conversation"),
                tr("状态", "Status"),
                tr("结果 / 原因", "Result / reason"),
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        for i, width in enumerate((190, 160, 95, 150, 100, 190)):
            self.table.setColumnWidth(i, width)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(45)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(210)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setItemDelegateForColumn(4, StatusDelegate(self.table))
        self.table.itemSelectionChanged.connect(self.show_detail)
        list_layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(7)
        add = QPushButton(tr("添加", "Add"))
        add.setObjectName("primary")
        add.clicked.connect(self.add_requested)
        row.addWidget(add)
        for title, signal in (
            (tr("编辑", "Edit"), self.edit_requested),
            (tr("删除", "Delete"), self.delete_requested),
            (tr("重新排期至现在", "Reschedule now"), self.retry_requested),
        ):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, sig=signal: self._emit(sig))
            row.addWidget(button)
        for title, delta in (("↑", -1), ("↓", 1)):
            button = QPushButton(title)
            button.setToolTip(
                tr("上移", "Move up") if delta < 0 else tr("下移", "Move down")
            )
            button.clicked.connect(
                lambda checked=False, d=delta: (
                    self.move_requested.emit(self.selected_id(), d)
                    if self.selected_id()
                    else None
                )
            )
            row.addWidget(button)
        row.addStretch()
        self.btn_stop = QPushButton(tr("停止当前执行", "Stop current run"))
        self.btn_stop.clicked.connect(self.stop_requested)
        row.addWidget(self.btn_stop)
        list_layout.addLayout(row)
        if read_only:
            for index in range(row.count()):
                widget = row.itemAt(index).widget()
                if widget:
                    widget.hide()
        splitter.addWidget(list_card)
        detail_card, detail_layout = card(
            tr("任务详情与 CLI 日志", "Task details and CLI log")
        )
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setObjectName("executionLog")
        self.detail.setMinimumHeight(150)
        self.detail.setPlaceholderText(
            tr(
                "选择任务查看提示词、权限、目录与执行结果。",
                "Select a task to inspect its prompt, permissions, directory and result.",
            )
        )
        # Preserve the full header and stable text selection while logs refresh.
        detail_layout.addWidget(self.detail, 1)
        splitter.addWidget(detail_card)
        splitter.setSizes([370, 230])
        layout.addWidget(splitter, 1)
        if not read_only:
            layout.addWidget(
                label(
                    tr(
                        "暂停队列不影响自动恢复与持续激活。失败或中断的任务需查看日志后手动重新排期。",
                        "Pausing the queue does not affect recovery or activation. Inspect failed or interrupted runs before rescheduling.",
                    ),
                    "hint",
                )
            )

    def selected_id(self):
        item = self.table.item(self.table.currentRow(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _emit(self, signal):
        if self.selected_id():
            signal.emit(self.selected_id())

    def set_sessions(self, sessions):
        self.session_titles = {s["session_id"]: s.get("title") for s in sessions}
        self.refresh_table(self.tasks)

    def refresh_table(self, tasks):
        selected = self.selected_id()
        self.tasks = tasks
        self.table.blockSignals(True)
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            due = (
                max(task.scheduled_at or 0, task.deferred_until) + task.buffer_seconds
                if task.scheduled_at
                else None
            )
            values = [
                task.name,
                time_text(due),
                task.model or tr("默认", "Default"),
                self.session_titles.get(task.session_id)
                or task.session_id
                or tr("新建", "New"),
                status_text(task.status),
                task.last_error.replace("\n", " ") if task.last_error else "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    f"{value}\nID: {task.session_id}" if column == 3 else value
                )
                item.setData(Qt.ItemDataRole.UserRole, task.id)
                if column == 4:
                    item.setData(STATUS_ROLE, task.status)
                self.table.setItem(row, column, item)
            if task.id == selected:
                self.table.selectRow(row)
        if self.table.currentRow() < 0 and tasks:
            self.table.selectRow(0)
        self.table.blockSignals(False)
        pending = sum(t.status in ("pending", "waiting") for t in tasks)
        self.lbl_count.setText(tr(f"{len(tasks)} 条记录 · {pending} 个待执行", f"{len(tasks)} records · {pending} pending"))
        self.show_detail()

    def show_detail(self):
        task = next((t for t in self.tasks if t.id == self.selected_id()), None)
        if task is None:
            self.detail.clear()
            self._detail_task_id = None
            return
        same_task = task.id == self._detail_task_id
        # While the user copies text, retain the displayed log even if the
        # bounded tail moves. The next refresh after deselection catches up.
        if same_task and self.detail.textCursor().hasSelection():
            return
        title = (
            self.session_titles.get(task.session_id)
            or task.session_id
            or tr("新建对话", "New conversation")
        )
        error_part = (
            f"\n{tr('错误 / 原因: ', 'Error / reason: ')}{task.last_error}\n"
            if task.last_error else ""
        )
        text = (
            f"{task.name}\n"
            f"{tr('执行状态', 'Execution status')}: {status_text(task.status)}\n"
            f"{tr('完成时间', 'Completed at')}: {time_text(task.completed_at)}\n"
            f"{tr('恢复 / 执行目标', 'Target conversation')}: {title}\n"
            f"{tr('目标会话 ID', 'Target thread ID')}: {task.session_id or '—'}\n"
            f"{tr('模型', 'Model')}: {task.model or tr('默认', 'Default')}\n"
            f"{tr('工作目录', 'Directory')}: {task.cwd}\n"
            f"{tr('执行权限', 'Execution permissions')}: {permission_text(task.sandbox)}\n"
            f"{tr('发送语句', 'Prompt')}: {task.prompt}\n{error_part}\n"
        )
        if task.status == "completed" and not task.last_error:
            text += tr(
                "执行已完成。原始日志中的辅助服务错误或警告不代表本次执行失败。\n\n",
                "Execution completed. Auxiliary service errors or warnings in the raw log do not mean this run failed.\n\n",
            )
        if task.log_file:
            text += f"Log: {task.log_file}\n"
            log_path = Path(task.log_file)
            if not log_path.exists():
                text += tr(
                    "（日志文件不存在；可能在执行初始化阶段发生异常）\n",
                    "(Log file does not exist; an error may have occurred during initialization)\n",
                )
            else:
                try:
                    with log_path.open("rb") as stream:
                        # The tail often excludes thread.started. Keep the actual
                        # CLI target visible above tool output, even for long logs.
                        for line in (
                            stream.read(16384)
                            .decode("utf-8", errors="replace")
                            .splitlines()
                        ):
                            try:
                                event = json.loads(line)
                            except ValueError:
                                continue
                            if (
                                isinstance(event, dict)
                                and event.get("type") == "thread.started"
                            ):
                                actual_id = event.get("thread_id") or "—"
                                text += f"{tr('实际启动会话 ID', 'Started thread ID')}: {actual_id}\n"
                                if task.session_id and actual_id != task.session_id:
                                    text += tr(
                                        "注意：实际启动 ID 与目标不一致。\n",
                                        "Warning: started ID differs from the target.\n",
                                    )
                                break
                        text += tr(
                            "\n原始执行日志（含工具调用与命令输出；其中提及的其他标题不代表恢复目标）：\n",
                            "\nRaw execution log (includes tool calls and command output; mentioned titles are not target identities):\n",
                        )
                        stream.seek(max(0, log_path.stat().st_size - 24000))
                        text += stream.read().decode("utf-8", errors="replace")
                except OSError as exc:
                    text += str(exc)
        # QTextDocument normalizes Windows newlines; compare the same form so
        # unchanged logs do not trigger a full replacement on every tick.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        previous = self.detail.toPlainText()
        if previous == text:
            self._detail_task_id = task.id
            return
        vsb = self.detail.verticalScrollBar()
        at_bottom = same_task and vsb.value() == vsb.maximum()
        old_val = vsb.value()
        if same_task and text.startswith(previous):
            # Append without resetting Qt's lazily laid-out wrapped lines.
            cursor = QTextCursor(self.detail.document())
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text[len(previous):])
        else:
            self.detail.setPlainText(text)
        vsb.setValue(vsb.maximum() if at_bottom else old_val if same_task else 0)
        self._detail_task_id = task.id
