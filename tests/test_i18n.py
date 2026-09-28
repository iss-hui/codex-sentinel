from codex_sentinel.i18n import detect_system_lang, get_lang, set_lang, t


def test_detect_system_lang():
    lang = detect_system_lang()
    assert lang in ("zh", "en")


def test_i18n_translation():
    # Test Chinese
    set_lang("zh")
    assert get_lang() == "zh"
    assert "配额已恢复" in t("default_resume_prompt")
    assert "未检测到生效中" in t("status_normal_exit")

    # Test English
    set_lang("en")
    assert get_lang() == "en"
    assert "Quota has been restored" in t("default_resume_prompt")
    assert "No active 5-hour rate limit detected" in t("status_normal_exit")


def test_i18n_formatting():
    set_lang("en")
    msg = t("label_session_id", val="abc-123")
    assert "Session ID : abc-123" in msg

    set_lang("zh")
    msg_zh = t("label_session_id", val="abc-123")
    assert "会话 ID   : abc-123" in msg_zh
