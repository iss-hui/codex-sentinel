import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.gui.common import status_text, time_text, tr


class TaskQueuePage(QWidget):
    add_requested = Signal()
    edit_requested = Signal(str)
    cancel_requested = Signal(str)
    retry_requested = Signal(str)
    move_requested = Signal(str, int)
    stop_requested = Signal()
    enabled_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks = []
        self.session_titles = {}
        layout = QVBoxLayout(self)
        self.chk_auto = QCheckBox(
            tr(
                "启用预约队列（按顺序逐个执行）",
                "Enable scheduled queue (one task at a time)",
            )
        )
        self.chk_auto.toggled.connect(self.enabled_changed)
        layout.addWidget(self.chk_auto)
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
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.show_detail)
        layout.addWidget(self.table, 2)
        row = QHBoxLayout()
        add = QPushButton(tr("添加", "Add"))
        add.clicked.connect(self.add_requested)
        row.addWidget(add)
        for label, signal in (
            (tr("编辑", "Edit"), self.edit_requested),
            (tr("取消", "Cancel"), self.cancel_requested),
            (tr("重新排期至现在", "Reschedule now"), self.retry_requested),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, sig=signal: self._emit(sig))
            row.addWidget(button)
        for label, delta in (("↑", -1), ("↓", 1)):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, d=delta: (
                    self.move_requested.emit(self.selected_id(), d)
                    if self.selected_id()
                    else None
                )
            )
            row.addWidget(button)
        stop = QPushButton(tr("停止当前执行", "Stop current run"))
        stop.clicked.connect(self.stop_requested)
        row.addWidget(stop)
        layout.addLayout(row)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumBlockCount(1000)
        layout.addWidget(self.detail, 1)

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
                task.last_error,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    f"{value}\nID: {task.session_id}" if column == 3 else value
                )
                item.setData(Qt.ItemDataRole.UserRole, task.id)
                self.table.setItem(row, column, item)
            if task.id == selected:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        self.show_detail()

    def show_detail(self):
        task = next((t for t in self.tasks if t.id == self.selected_id()), None)
        if task is None:
            self.detail.clear()
            return
        title = (
            self.session_titles.get(task.session_id)
            or task.session_id
            or tr("新建对话", "New conversation")
        )
        text = (
            f"{task.name}\n"
            f"{tr('恢复 / 执行目标', 'Target conversation')}: {title}\n"
            f"{tr('目标会话 ID', 'Target thread ID')}: {task.session_id or '—'}\n"
            f"{tr('模型', 'Model')}: {task.model or tr('默认', 'Default')}\n"
            f"{tr('工作目录', 'Directory')}: {task.cwd}\n"
            f"{tr('发送语句', 'Prompt')}: {task.prompt}\n\n{task.last_error}\n"
        )
        if task.log_file:
            text += f"Log: {task.log_file}\n"
            try:
                with Path(task.log_file).open("rb") as stream:
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
                    stream.seek(max(0, Path(task.log_file).stat().st_size - 24000))
                    text += stream.read().decode("utf-8", errors="replace")
            except OSError as exc:
                text += str(exc)
        self.detail.setPlainText(text)
