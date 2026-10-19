from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.gui.common import status_text, time_text, tr
from codex_sentinel.gui.ui import STATUS_ROLE, StatusDelegate, card, heading, label


class SessionsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions_data = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        heading(
            layout,
            tr("本地对话", "Local conversations"),
            tr(
                "查找本地未归档聊天，核对标题、目录与记录状态。",
                "Find local unarchived conversations and inspect their records.",
            ),
        )
        table_card, table_layout = card()
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(18, 15, 18, 15)
        row.addWidget(
            label(tr("全部未归档对话", "All unarchived conversations"), "section"), 1
        )
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(
            tr("搜索标题、模型、路径…", "Search title, model, directory…")
        )
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setMaximumWidth(310)
        self.txt_search.textChanged.connect(self.filter_sessions)
        row.addWidget(self.txt_search, 1)
        table_layout.addLayout(row)
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
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        for i, width in enumerate((220, 100, 145, 165, 85, 105, 55)):
            self.table.setColumnWidth(i, width)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(43)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(280)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setItemDelegateForColumn(5, StatusDelegate(self.table))
        self.table.itemSelectionChanged.connect(self.show_detail)
        table_layout.addWidget(self.table, 1)
        self.lbl_stats = label("", "hint")
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(18, 10, 18, 10)
        stats_row.addWidget(self.lbl_stats)
        table_layout.addLayout(stats_row)
        layout.addWidget(table_card, 1)
        detail_card, detail_layout = card(
            tr("对话信息 · 只读查看", "Conversation details · read only")
        )
        self.lbl_detail = label(
            tr(
                "选择对话查看完整 ID 与工作目录。",
                "Select a conversation to see its full ID and directory.",
            ),
            "path",
            True,
        )
        detail_layout.addWidget(self.lbl_detail)
        detail_layout.addWidget(
            label(
                tr(
                    "Token 与状态来自本地记录；缺失信息显示未知，不视为 0。",
                    "Tokens and status come from local records; missing data is unknown, not zero.",
                ),
                "hint",
            )
        )
        layout.addWidget(detail_card)

    def show_detail(self):
        item = self.table.item(self.table.currentRow(), 0)
        if item:
            session = next(
                (
                    s
                    for s in self.sessions_data
                    if s["session_id"] == item.data(Qt.ItemDataRole.UserRole)
                ),
                None,
            )
            if session:
                self.lbl_detail.setText(
                    f"{session.get('title') or session['session_id']}\nID: {session['session_id']}\n{session.get('cwd') or '—'}"
                )
                return
        self.lbl_detail.setText(
            tr(
                "选择对话查看完整 ID 与工作目录。",
                "Select a conversation to see its full ID and directory.",
            )
        )

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
        selected = self.table.item(self.table.currentRow(), 0)
        selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected else ""
        self.table.blockSignals(True)
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
                item.setData(Qt.ItemDataRole.UserRole, session["session_id"])
                if column == 5:
                    item.setData(STATUS_ROLE, session.get("task_status", "unknown"))
                if column in (4, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
            if session["session_id"] == selected_id:
                self.table.selectRow(row)

        if self.table.currentRow() < 0 and sessions:
            self.table.selectRow(0)
        self.table.blockSignals(False)
        self.show_detail()
