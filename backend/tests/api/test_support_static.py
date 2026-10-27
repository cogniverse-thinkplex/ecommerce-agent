from fastapi.testclient import TestClient

from app.api.main import create_app


def test_support_page_is_mounted_as_customer_facing_chinese_application():
    client = TestClient(create_app())

    response = client.get("/support/")

    assert response.status_code == 200
    assert 'lang="zh-CN"' in response.text
    assert "独立客服中心" not in response.text
    assert "订单与售后服务" not in response.text
    assert 'aria-label="发送消息"' in response.text
    assert 'aria-live="polite"' in response.text
    assert 'type="module"' in response.text
    assert "/support/app.js" in response.text
    assert 'id="logout-button"' in response.text
    assert 'id="sidebar-account-name"' in response.text
    assert 'aria-label="编辑个人信息"' in response.text
    assert 'href="/account/"' in response.text
    assert 'href="/account/spending/"' in response.text
    assert "消费分析" in response.text
    assert 'href="/support/feedback/"' in response.text
    assert 'id="retail-auth-state"' not in response.text
    for internal_term in ("reward", "cost", "policy", "trace", "benchmark"):
        assert internal_term not in response.text.lower()


def test_support_static_modules_and_styles_are_served():
    client = TestClient(create_app())

    for path in (
        "/support/styles.css",
        "/support/app.js",
        "/support/api.js",
        "/support/session.js",
        "/support/chat.js",
        "/support/cards.js",
        "/support/history.js",
        "/support/feedback.js",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.text.strip(), path


def test_support_uses_dedicated_issue_feedback_page():
    client = TestClient(create_app())
    html = client.get("/support/").text
    feedback_page = client.get("/support/feedback/")

    assert 'id="conversation-feedback"' not in html
    assert "有帮助" not in html
    assert "没帮助" not in html
    assert feedback_page.status_code == 200
    assert 'id="feedback-form"' in feedback_page.text
    assert 'value="interface"' in feedback_page.text
    assert 'id="feedback-description"' in feedback_page.text
    assert 'id="feedback-conversation"' in feedback_page.text
    assert "/support/feedback/feedback.js" in feedback_page.text


def test_support_entrypoint_cache_busts_current_history_module():
    client = TestClient(create_app())
    javascript = client.get("/support/app.js").text

    assert 'history.js?v=20261023-customer-shell' in javascript
    assert 'api.js?v=20261023-customer-shell' in javascript


def test_support_shows_a_visible_pending_reply_while_agent_is_working():
    client = TestClient(create_app())

    app = client.get("/support/app.js").text
    chat = client.get("/support/chat.js").text
    styles = client.get("/support/styles.css").text

    assert "chat.beginActivity" in app
    assert "chat.updateActivity" in app
    assert "chat.finishActivity" in app
    assert "请求已发送，等待客服处理" in chat
    assert 'role", "status"' in chat
    assert ".activity-row" in styles


def test_support_primary_composer_uses_server_driven_streaming_progress():
    client = TestClient(create_app())

    app = client.get("/support/app.js").text
    api = client.get("/support/api.js").text
    chat = client.get("/support/chat.js").text
    stream = client.get("/support/stream.js")

    assert stream.status_code == 200
    assert "api.streamMessage" in app
    assert "api.sendMessage(activeId" not in app
    assert "parseSSEStream" in api
    assert "beginActivity" in chat
    assert "updateActivity" in chat
    assert 'role", "status"' in chat
    assert "innerHTML" not in stream.text
    assert "requestId, index" in chat
    assert "data-stream-request" in chat
    assert "terminal SSE event" in stream.text


def test_support_keeps_human_handoff_in_header_without_permission_banner():
    client = TestClient(create_app())

    html = client.get("/support/").text
    app = client.get("/support/app.js").text
    cards = client.get("/support/cards.js").text

    assert "查询自动执行" not in html
    assert "操作需确认" not in html
    assert "人工可接管" not in html
    assert 'class="header-human-service"' in html
    assert 'id="transfer-to-human"' in html
    assert "api.createHandoff" in app
    assert "仅授权本次操作一次" in cards
    assert "拒绝操作" in cards


def test_support_empty_state_offers_customer_shortcuts():
    client = TestClient(create_app())
    chat = client.get("/support/chat.js").text
    app = client.get("/support/app.js").text

    for label in ("查询全部订单", "查询订单状态", "取消待处理订单", "办理退换货"):
        assert label in chat
    assert "support-shortcut" in chat
    assert "onShortcut" in chat
    assert "els.input.value" in app


def test_support_order_cards_format_items_and_addresses_for_people():
    client = TestClient(create_app())

    cards = client.get("/support/cards.js").text
    styles = client.get("/support/styles.css").text

    assert 'key === "items" && Array.isArray(value)' in cards
    assert 'key === "address"' in cards and "addressText(value)" in cards
    assert "item-list" in styles


def test_support_operation_results_translate_business_status_and_hide_verification_detail():
    client = TestClient(create_app())

    cards = client.get("/support/cards.js").text

    assert 'action: "操作"' in cards
    assert 'order_status: "订单状态"' in cards
    assert 'verification' in cards
    assert 'cancelled: "已取消"' in cards
    assert 'succeeded: "成功"' in cards


def test_root_redirects_to_support_while_dashboard_remains_available():
    client = TestClient(create_app(), follow_redirects=False)

    root = client.get("/")

    assert root.status_code == 307
    assert root.headers["location"] == "/support/"
    assert client.get("/dashboard/").status_code == 200


def test_support_sidebar_exposes_conversation_and_group_management():
    client = TestClient(create_app())
    html = client.get("/support/").text
    app = client.get("/support/app.js").text
    history = client.get("/support/history.js").text
    api = client.get("/support/api.js").text

    assert 'id="manage-groups"' in html
    assert 'id="group-manager"' in html
    assert "renderHistoryList" in app and "groups" in app
    for action in ("重命名", "置顶", "移动到分组", "删除会话"):
        assert action in history
    assert "确定删除此会话吗" in app
    assert "updateConversation" in api
    assert "listGroups" in api
    assert "createGroup" in api
    assert "deleteGroup" in api


def test_support_groups_are_collapsible_and_remember_their_open_state():
    client = TestClient(create_app())
    history = client.get("/support/history.js").text
    app = client.get("/support/app.js").text

    assert 'document.createElement("details")' in history
    assert "history-section" in history
    assert "sectionOpen" in app
    assert "localStorage" in app
    assert "conversations = conversations.filter" in app


def test_support_groups_remain_visible_when_empty_and_use_a_move_dialog():
    client = TestClient(create_app())
    html = client.get("/support/").text
    history = client.get("/support/history.js").text
    app = client.get("/support/app.js").text

    assert 'id="move-conversation-dialog"' in html
    assert 'id="move-group-select"' in html
    assert "暂无会话" in history
    assert "sections.filter" not in history
    assert "x.group_id===g.group_id" in history
    assert "openMoveDialog" in app
    assert "moveGroupSelect" in app
    assert "window.prompt(`移动到分组" not in app


def test_support_list_refresh_sends_the_current_draft_for_empty_cleanup():
    client = TestClient(create_app())
    api = client.get("/support/api.js").text
    app = client.get("/support/app.js").text

    assert "active_conversation_id" in api
    assert "api.listConversations(activeId)" in app

