from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.gui.common import status_text, time_text, tr


class SessionsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions_data = []
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("本地未归档对话", "Local unarchived conversations")))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(
            tr("搜索标题、模型、路径…", "Search title, model, directory…")
        )
        self.txt_search.textChanged.connect(self.filter_sessions)
        row.addWidget(self.txt_search)
        layout.addLayout(row)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                tr("标题 / ID", "Title / ID"),
                tr("模型", "Model"),
                tr("更新时间", "Updated"),
                tr("工作目录", "Directory"),
                tr("Token 记录", "Recorded tokens"),
                tr("状态", "Status"),
                tr("轮次", "Turns"),
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        self.lbl_stats = QLabel()
        layout.addWidget(self.lbl_stats)

    def on_scan_completed(self, sessions):
        self.sessions_data = sessions
        self.filter_sessions(self.txt_search.text())
        self.lbl_stats.setText(
            tr(
                f"已读取 {len(sessions)} 个对话；仅统计本地扫描范围。",
                f"Read {len(sessions)} conversations; local scan scope only.",
            )
        )

    def filter_sessions(self, query):
        sessions = [s for s in self.sessions_data if query.lower() in str(s).lower()]
        self.table.setRowCount(len(sessions))
        for row, session in enumerate(sessions):
            values = [
                session.get("title") or session.get("session_id", ""),
                session.get("model") or tr("默认", "Default"),
                time_text(session.get("updated_at")),
                session.get("cwd") or "—",
                str(
                    session.get("tokens_used")
                    if session.get("tokens_used") is not None
                    else "—"
                ),
                status_text(session.get("task_status", "unknown")),
                str(session.get("total_turns"))
                if session.get("total_turns") is not None
                else "—",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(session["session_id"] if column == 0 else value)
                self.table.setItem(row, column, item)
