from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStyle

from codex_sentinel.i18n import get_lang
from codex_sentinel.session_catalog import folder_name, normalized_path


def tr(zh, en):
    return zh if get_lang() == "zh" else en


def time_text(value):
    return (
        datetime.fromtimestamp(value).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        if value
        else "—"
    )


def permission_text(sandbox):
    if sandbox == "workspace-write":
        return tr("工作区可写 · 自动审批", "Workspace write · automatic approval reviews")
    return tr("只读 · 不申请审批", "Read-only · no approval requests")


def status_text(status):
    labels = {
        "retry": ("等待网络重试", "Waiting to retry network failure"),
        "awaiting_limit": ("等待新的限额时间", "Waiting for updated quota time"),
        "migrated": ("已转入独立监控", "Moved to independent monitoring"),
        "pending": ("待执行", "Pending"),
        "paused": ("自动恢复已关闭", "Auto-resume disabled"),
        "waiting": ("等待限额 / 对话空闲", "Waiting"),
        "running": ("执行中", "Running"),
        "completed": ("已完成", "Completed"),
        "failed": ("失败", "Failed"),
        "cancelled": ("已取消", "Cancelled"),
        "interrupted": ("已中断", "Interrupted"),
        "missed": ("已错过，请重新预约", "Missed; reschedule"),
        "rate_limited": ("限额中断", "Rate limited"),
        "error": ("错误", "Error"),
        "unknown": ("未知", "Unknown"),
        "simulated": ("已模拟（未发送）", "Simulated (not sent)"),
    }
    return tr(*labels.get(status, (status, status)))


def populate_sessions(combo, sessions, new_session=True):
    selected = combo.currentData()
    selected_text = combo.currentText()
    selected_tooltip = combo.currentData(Qt.ItemDataRole.ToolTipRole)
    if not getattr(combo, "_session_tooltip_connected", False):
        combo.currentIndexChanged.connect(
            lambda index: combo.setToolTip(
                combo.itemData(index, Qt.ItemDataRole.ToolTipRole) or ""
            )
        )
        combo._session_tooltip_connected = True
    combo.blockSignals(True)
    combo.clear()
    if new_session:
        combo.addItem(tr("新建对话", "New conversation"), "")
    first_session = -1
    previous_group = None
    for s in sessions:
        title = " ".join((s.get("title") or s["session_id"][:12]).split())
        cwd = s.get("cwd") or ""
        group = s.get("project_key", normalized_path(cwd))
        folder = s.get("project_name", folder_name(cwd)) or tr(
            "未分组对话", "Ungrouped conversations"
        )
        if group != previous_group:
            combo.addItem(
                combo.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon),
                folder,
            )
            heading = combo.model().item(combo.count() - 1)
            heading.setFlags(Qt.ItemFlag.NoItemFlags)
            font = heading.font()
            font.setBold(True)
            heading.setFont(font)
            previous_group = group
        combo.addItem("    " + title, s["session_id"])
        if first_session < 0:
            first_session = combo.count() - 1
        tooltip = f"{folder} › {title}\n{cwd}\n{tr('模型', 'Model')}: {s.get('model') or tr('默认', 'Default')}\nID: {s['session_id']}"
        combo.setItemData(combo.count() - 1, tooltip, Qt.ItemDataRole.ToolTipRole)
    index = combo.findData(selected) if selected is not None else -1
    if selected and index < 0:
        # Preserve an explicit target instead of silently selecting another chat.
        combo.addItem(selected_text or str(selected), selected)
        index = combo.count() - 1
        combo.setItemData(index, selected_tooltip, Qt.ItemDataRole.ToolTipRole)
    if index >= 0:
        combo.setCurrentIndex(index)
    elif not new_session:
        combo.setCurrentIndex(first_session)
    combo.setMaxVisibleItems(20)
    combo.blockSignals(False)
    combo.setToolTip(combo.currentData(Qt.ItemDataRole.ToolTipRole) or "")


def populate_models(combo, models):
    text = combo.currentText()
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("")
    combo.addItems([m["slug"] for m in models])
    combo.setCurrentText(text)
    combo.setToolTip(
        tr(
            "空白使用 Codex 默认模型；也可输入模型 ID",
            "Leave blank for Codex default, or enter a model ID",
        )
    )
    combo.blockSignals(False)
