from pathlib import Path

from app.agent.state import CustomerAgentState
from app.persistence.models import (
    ConversationGroupRecord,
    ConversationRecord,
    MessageRecord,
    UserRecord,
)
from app.persistence.sqlite import SqliteUnitOfWork


def _seed(unit: SqliteUnitOfWork) -> None:
    with unit.transaction():
        for user_id in ("owner-1", "owner-2"):
            unit.users.create(
                UserRecord(
                    user_id=user_id,
                    email=f"{user_id}@example.com",
                    display_name=user_id,
                    password_hash="hash",
                    role="customer",
                )
            )


def _conversation(conversation_id: str, owner: str) -> ConversationRecord:
    return ConversationRecord(
        conversation_id=conversation_id,
        owner_user_id=owner,
        state=CustomerAgentState(conversation_id=conversation_id),
    )


def test_migration_and_management_fields_round_trip(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "management.db")
    unit.initialize()
    _seed(unit)
    group = ConversationGroupRecord(
        group_id="group-1", owner_user_id="owner-1", name="退货咨询"
    )
    record = _conversation("conversation-1", "owner-1").model_copy(
        update={
            "title": "键盘换货",
            "title_source": "custom",
            "is_pinned": True,
            "group_id": group.group_id,
        }
    )

    with unit.transaction():
        unit.conversation_groups.create(group)
        unit.conversations.save(record)

    loaded = unit.conversations.get_for_owner("conversation-1", "owner-1")
    assert unit.applied_migrations()[-1] == 14
    assert loaded is not None
    assert loaded.title == "键盘换货"
    assert loaded.title_source == "custom"
    assert loaded.is_pinned is True
    assert loaded.group_id == "group-1"


def test_management_updates_and_groups_are_owner_scoped(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "ownership.db")
    unit.initialize()
    _seed(unit)
    with unit.transaction():
        unit.conversations.save(_conversation("conversation-1", "owner-1"))
        unit.conversation_groups.create(
            ConversationGroupRecord(group_id="group-1", owner_user_id="owner-1", name="售后")
        )

    with unit.transaction():
        assert unit.conversations.update_management(
            "conversation-1", "owner-2", title="越权", is_pinned=True
        ) is False
        assert unit.conversations.update_management(
            "conversation-1", "owner-1", title="我的售后", is_pinned=True, group_id="group-1"
        ) is True

    assert unit.conversations.get_for_owner("conversation-1", "owner-2") is None
    assert unit.conversation_groups.get_for_owner("group-1", "owner-2") is None
    loaded = unit.conversations.get_for_owner("conversation-1", "owner-1")
    assert loaded is not None and loaded.title == "我的售后" and loaded.is_pinned


def test_deleting_group_unassigns_conversations(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "delete-group.db")
    unit.initialize()
    _seed(unit)
    with unit.transaction():
        unit.conversation_groups.create(
            ConversationGroupRecord(group_id="group-1", owner_user_id="owner-1", name="订单")
        )
        unit.conversations.save(
            _conversation("conversation-1", "owner-1").model_copy(update={"group_id": "group-1"})
        )
    with unit.transaction():
        assert unit.conversation_groups.delete_for_owner("group-1", "owner-2") is False
        assert unit.conversation_groups.delete_for_owner("group-1", "owner-1") is True

    loaded = unit.conversations.get("conversation-1")
    assert loaded is not None and loaded.group_id is None


def test_archive_empty_only_archives_active_conversations_without_user_questions(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "empty.db")
    unit.initialize()
    _seed(unit)
    with unit.transaction():
        unit.conversations.save(_conversation("empty", "owner-1"))
        unit.conversations.save(_conversation("asked", "owner-1"))
        unit.conversations.save(_conversation("foreign", "owner-2"))
        unit.messages.append(
            MessageRecord(
                message_id="message-1",
                conversation_id="asked",
                sequence=1,
                role="user",
                kind="text",
                text="查询订单",
            )
        )
    with unit.transaction():
        assert unit.conversations.archive_empty_for_owner("owner-1") == 1

    assert unit.conversations.get("empty").status == "archived"
    assert unit.conversations.get("asked").status == "active"
    assert unit.conversations.get("foreign").status == "active"


def test_archive_empty_can_preserve_the_current_draft(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "draft.db")
    unit.initialize()
    _seed(unit)
    with unit.transaction():
        unit.conversations.save(_conversation("stale-empty", "owner-1"))
        unit.conversations.save(_conversation("current-empty", "owner-1"))

    with unit.transaction():
        archived = unit.conversations.archive_empty_for_owner(
            "owner-1", exclude_conversation_id="current-empty"
        )

    assert archived == 1
    assert unit.conversations.get("stale-empty").status == "archived"
    assert unit.conversations.get("current-empty").status == "active"
