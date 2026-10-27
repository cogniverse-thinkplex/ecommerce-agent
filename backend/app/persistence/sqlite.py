from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Iterator

from app.agent.state import CustomerAgentState
from app.persistence.models import (
    ActionStatus,
    AgentRunRecord,
    AgentRunStepRecord,
    AuditEventRecord,
    AuthAuditEventRecord,
    AuthSessionRecord,
    ConversationGroupRecord,
    ConversationRecord,
    CustomerAddressRecord,
    DemoOrderMetadataRecord,
    MessageRecord,
    PendingActionRecord,
    PolicyChunkRecord,
    PolicyDocumentRecord,
    RegressionCaseRecord,
    RegressionCaseRunRecord,
    FeedbackRecord,
    HandoffStatus,
    HumanHandoffRecord,
    RuntimeIssueRecord,
    UserRecord,
)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value is not None else None


def _message_from_row(row: sqlite3.Row) -> MessageRecord:
    return MessageRecord(
        message_id=row["message_id"],
        conversation_id=row["conversation_id"],
        sequence=row["sequence"],
        role=row["role"],
        kind=row["kind"],
        text=row["text"],
        payload=json.loads(row["payload_json"]),
        delivery_state=row["delivery_state"],
        request_id=row["request_id"],
        created_at=row["created_at"],
    )


def _customer_address_from_row(row: sqlite3.Row) -> CustomerAddressRecord:
    return CustomerAddressRecord(
        address_id=row["address_id"], owner_user_id=row["owner_user_id"],
        recipient_name=row["recipient_name"], phone=row["phone"], address1=row["address1"],
        address2=row["address2"], city=row["city"], state=row["state"], country=row["country"],
        zip=row["zip"], is_default=bool(row["is_default"]), status=row["status"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class SqliteCustomerAddressRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, record: CustomerAddressRecord) -> None:
        self._connection.execute(
            "INSERT INTO customer_addresses (address_id,owner_user_id,recipient_name,phone,address1,address2,city,state,country,zip,is_default,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (record.address_id, record.owner_user_id, record.recipient_name, record.phone,
             record.address1, record.address2, record.city, record.state, record.country,
             record.zip, int(record.is_default), record.status, _iso(record.created_at), _iso(record.updated_at)),
        )

    def list_for_owner(self, owner_user_id: str) -> list[CustomerAddressRecord]:
        rows = self._connection.execute(
            "SELECT * FROM customer_addresses WHERE owner_user_id=? AND status='active' ORDER BY is_default DESC, updated_at DESC",
            (owner_user_id,),
        ).fetchall()
        return [_customer_address_from_row(row) for row in rows]

    def get_for_owner(self, address_id: str, owner_user_id: str) -> CustomerAddressRecord | None:
        row = self._connection.execute(
            "SELECT * FROM customer_addresses WHERE address_id=? AND owner_user_id=? AND status='active'",
            (address_id, owner_user_id),
        ).fetchone()
        return _customer_address_from_row(row) if row else None

    def update(self, record: CustomerAddressRecord) -> bool:
        result = self._connection.execute(
            "UPDATE customer_addresses SET recipient_name=?,phone=?,address1=?,address2=?,city=?,state=?,country=?,zip=?,is_default=?,status=?,updated_at=? WHERE address_id=? AND owner_user_id=?",
            (record.recipient_name, record.phone, record.address1, record.address2, record.city,
             record.state, record.country, record.zip, int(record.is_default), record.status,
             _iso(record.updated_at), record.address_id, record.owner_user_id),
        )
        return result.rowcount == 1

    def set_default_for_owner(self, address_id: str, owner_user_id: str) -> bool:
        now = _iso(datetime.now(timezone.utc))
        self._connection.execute(
            "UPDATE customer_addresses SET is_default=0,updated_at=? WHERE owner_user_id=? AND status='active'",
            (now, owner_user_id),
        )
        result = self._connection.execute(
            "UPDATE customer_addresses SET is_default=1,updated_at=? WHERE address_id=? AND owner_user_id=? AND status='active'",
            (now, address_id, owner_user_id),
        )
        return result.rowcount == 1

    def archive_for_owner(self, address_id: str, owner_user_id: str) -> bool:
        result = self._connection.execute(
            "UPDATE customer_addresses SET status='archived',is_default=0,updated_at=? WHERE address_id=? AND owner_user_id=? AND status='active'",
            (_iso(datetime.now(timezone.utc)), address_id, owner_user_id),
        )
        return result.rowcount == 1


class SqliteDemoOrderMetadataRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, order_id: str) -> DemoOrderMetadataRecord | None:
        row = self._connection.execute(
            "SELECT * FROM demo_order_metadata WHERE order_id=?", (order_id,)
        ).fetchone()
        if not row:
            return None
        return DemoOrderMetadataRecord(
            order_id=row["order_id"], purchased_at=row["purchased_at"], created_at=row["created_at"]
        )

    def save(self, record: DemoOrderMetadataRecord) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO demo_order_metadata(order_id,purchased_at,created_at) VALUES (?,?,?)",
            (record.order_id, _iso(record.purchased_at), _iso(record.created_at)),
        )


def _policy_document_from_row(row: sqlite3.Row) -> PolicyDocumentRecord:
    return PolicyDocumentRecord(
        policy_id=row["policy_id"], title=row["title"], category=row["category"],
        summary=row["summary"], source_url=row["source_url"], scope=row["scope"],
        official_version=row["official_version"], verified_at=row["verified_at"],
        content_hash=row["content_hash"], enabled=bool(row["enabled"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _policy_chunk_from_row(row: sqlite3.Row) -> PolicyChunkRecord:
    return PolicyChunkRecord(
        chunk_id=row["chunk_id"], policy_id=row["policy_id"], sequence=row["sequence"],
        content=row["content"], token_text=row["token_text"], content_hash=row["content_hash"],
        embedding=row["embedding"], embedding_model=row["embedding_model"], created_at=row["created_at"],
    )


class SqlitePolicyDocumentRepository:
    def __init__(self, connection: sqlite3.Connection) -> None: self._connection = connection

    def upsert(self, record: PolicyDocumentRecord) -> None:
        self._connection.execute(
            """INSERT INTO policy_documents(policy_id,title,category,summary,source_url,scope,official_version,verified_at,content_hash,enabled,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(policy_id) DO UPDATE SET
            title=excluded.title,category=excluded.category,summary=excluded.summary,source_url=excluded.source_url,
            scope=excluded.scope,official_version=excluded.official_version,verified_at=excluded.verified_at,
            content_hash=excluded.content_hash,enabled=excluded.enabled,updated_at=excluded.updated_at""",
            (record.policy_id, record.title, record.category, record.summary, record.source_url,
             record.scope, record.official_version, record.verified_at, record.content_hash,
             int(record.enabled), _iso(record.created_at), _iso(record.updated_at)),
        )

    def get(self, policy_id: str) -> PolicyDocumentRecord | None:
        row = self._connection.execute("SELECT * FROM policy_documents WHERE policy_id=?", (policy_id,)).fetchone()
        return _policy_document_from_row(row) if row else None

    def list_enabled(self, category: str | None = None) -> list[PolicyDocumentRecord]:
        if category:
            rows = self._connection.execute("SELECT * FROM policy_documents WHERE enabled=1 AND category=? ORDER BY title", (category,)).fetchall()
        else:
            rows = self._connection.execute("SELECT * FROM policy_documents WHERE enabled=1 ORDER BY category,title").fetchall()
        return [_policy_document_from_row(row) for row in rows]


class SqlitePolicyChunkRepository:
    def __init__(self, connection: sqlite3.Connection) -> None: self._connection = connection

    def replace_for_policy(self, policy_id: str, chunks: list[PolicyChunkRecord]) -> None:
        existing = self._connection.execute("SELECT chunk_id FROM policy_chunks WHERE policy_id=?", (policy_id,)).fetchall()
        for row in existing:
            self._connection.execute("DELETE FROM policy_chunks_fts WHERE chunk_id=?", (row["chunk_id"],))
        self._connection.execute("DELETE FROM policy_chunks WHERE policy_id=?", (policy_id,))
        for record in chunks:
            self._connection.execute(
                "INSERT INTO policy_chunks(chunk_id,policy_id,sequence,content,token_text,content_hash,embedding,embedding_model,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (record.chunk_id, record.policy_id, record.sequence, record.content, record.token_text,
                 record.content_hash, record.embedding, record.embedding_model, _iso(record.created_at)),
            )
            self._connection.execute("INSERT INTO policy_chunks_fts(chunk_id,policy_id,token_text) VALUES(?,?,?)", (record.chunk_id, record.policy_id, record.token_text))

    def list_enabled(self) -> list[PolicyChunkRecord]:
        rows = self._connection.execute("SELECT c.* FROM policy_chunks c JOIN policy_documents d USING(policy_id) WHERE d.enabled=1 ORDER BY c.policy_id,c.sequence").fetchall()
        return [_policy_chunk_from_row(row) for row in rows]

    def update_embedding(self, chunk_id: str, embedding: bytes, model: str) -> None:
        self._connection.execute("UPDATE policy_chunks SET embedding=?,embedding_model=? WHERE chunk_id=?", (embedding, model, chunk_id))

    def search_bm25(self, tokens: list[str], limit: int = 20) -> list[tuple[PolicyChunkRecord, float]]:
        if not tokens: return []
        query = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)
        rows = self._connection.execute(
            "SELECT c.*, bm25(policy_chunks_fts) AS score FROM policy_chunks_fts f JOIN policy_chunks c ON c.chunk_id=f.chunk_id JOIN policy_documents d ON d.policy_id=c.policy_id WHERE policy_chunks_fts MATCH ? AND d.enabled=1 ORDER BY score LIMIT ?",
            (query, limit),
        ).fetchall()
        return [(_policy_chunk_from_row(row), float(row["score"])) for row in rows]

class SqliteConversationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, record: ConversationRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO conversations (
                conversation_id, title, status, owner_user_id, authenticated_user_id,
                authentication_method, state_json, last_error_code,
                created_at, updated_at, group_id, is_pinned, title_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                title=excluded.title,
                status=excluded.status,
                owner_user_id=excluded.owner_user_id,
                authenticated_user_id=excluded.authenticated_user_id,
                authentication_method=excluded.authentication_method,
                state_json=excluded.state_json,
                last_error_code=excluded.last_error_code,
                group_id=excluded.group_id,
                is_pinned=excluded.is_pinned,
                title_source=excluded.title_source,
                updated_at=excluded.updated_at
            """,
            (
                record.conversation_id,
                record.title,
                record.status,
                record.owner_user_id,
                record.authenticated_user_id,
                record.authentication_method,
                record.state.model_dump_json(),
                record.last_error_code,
                _iso(record.created_at),
                _iso(record.updated_at),
                record.group_id,
                int(record.is_pinned),
                record.title_source,
            ),
        )

    def get(self, conversation_id: str) -> ConversationRecord | None:
        row = self._connection.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return _conversation_from_row(row) if row is not None else None

    def list_active(self) -> list[ConversationRecord]:
        rows = self._connection.execute(
            "SELECT * FROM conversations WHERE status = 'active' ORDER BY updated_at DESC"
        ).fetchall()
        return [_conversation_from_row(row) for row in rows]

    def list_active_for_owner(self, owner_user_id: str) -> list[ConversationRecord]:
        rows = self._connection.execute(
            "SELECT * FROM conversations WHERE status = 'active' AND owner_user_id = ? "
            "ORDER BY is_pinned DESC, updated_at DESC",
            (owner_user_id,),
        ).fetchall()
        return [_conversation_from_row(row) for row in rows]

    def get_for_owner(
        self, conversation_id: str, owner_user_id: str
    ) -> ConversationRecord | None:
        row = self._connection.execute(
            "SELECT * FROM conversations WHERE conversation_id = ? AND owner_user_id = ?",
            (conversation_id, owner_user_id),
        ).fetchone()
        return _conversation_from_row(row) if row is not None else None

    def archive(self, conversation_id: str) -> bool:
        result = self._connection.execute(
            "UPDATE conversations SET status = 'archived', updated_at = ? "
            "WHERE conversation_id = ? AND status = 'active'",
            (_iso(datetime.now(timezone.utc)), conversation_id),
        )
        return result.rowcount == 1

    def archive_for_owner(self, conversation_id: str, owner_user_id: str) -> bool:
        result = self._connection.execute(
            "UPDATE conversations SET status = 'archived', updated_at = ? "
            "WHERE conversation_id = ? AND owner_user_id = ? AND status = 'active'",
            (_iso(datetime.now(timezone.utc)), conversation_id, owner_user_id),
        )
        return result.rowcount == 1

    def update_management(
        self,
        conversation_id: str,
        owner_user_id: str,
        *,
        title: str | None = None,
        is_pinned: bool | None = None,
        group_id: str | None = None,
        update_group: bool = True,
    ) -> bool:
        updates: list[str] = []
        values: list[Any] = []
        if title is not None:
            updates.extend(["title = ?", "title_source = 'custom'"])
            values.append(title)
        if is_pinned is not None:
            updates.append("is_pinned = ?")
            values.append(int(is_pinned))
        if update_group:
            updates.append("group_id = ?")
            values.append(group_id)
        if not updates:
            return True
        updates.append("updated_at = ?")
        values.append(_iso(datetime.now(timezone.utc)))
        values.extend([conversation_id, owner_user_id])
        result = self._connection.execute(
            f"UPDATE conversations SET {', '.join(updates)} "
            "WHERE conversation_id = ? AND owner_user_id = ? AND status = 'active'",
            values,
        )
        return result.rowcount == 1

    def archive_empty_for_owner(self, owner_user_id: str | None, *, exclude_conversation_id: str | None = None) -> int:
        owner_clause = "owner_user_id = ?" if owner_user_id is not None else "owner_user_id IS NULL"
        params: list[Any] = [_iso(datetime.now(timezone.utc))]
        if owner_user_id is not None:
            params.append(owner_user_id)
        exclude_clause = ""
        if exclude_conversation_id is not None:
            exclude_clause = " AND conversation_id <> ?"
            params.append(exclude_conversation_id)
        result = self._connection.execute(
            "UPDATE conversations SET status = 'archived', updated_at = ? WHERE "
            + owner_clause
            + exclude_clause
            + " AND status = 'active' AND NOT EXISTS ("
            "SELECT 1 FROM messages WHERE messages.conversation_id = conversations.conversation_id "
            "AND messages.role = 'user')",
            params,
        )
        return result.rowcount


class SqliteConversationGroupRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, record: ConversationGroupRecord) -> None:
        self._connection.execute(
            "INSERT INTO conversation_groups (group_id, owner_user_id, name, sort_order, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (record.group_id, record.owner_user_id, record.name, record.sort_order,
             _iso(record.created_at), _iso(record.updated_at)),
        )

    def get_for_owner(self, group_id: str, owner_user_id: str) -> ConversationGroupRecord | None:
        row = self._connection.execute(
            "SELECT * FROM conversation_groups WHERE group_id = ? AND owner_user_id = ?",
            (group_id, owner_user_id),
        ).fetchone()
        return _conversation_group_from_row(row) if row else None

    def list_for_owner(self, owner_user_id: str) -> list[ConversationGroupRecord]:
        rows = self._connection.execute(
            "SELECT * FROM conversation_groups WHERE owner_user_id = ? ORDER BY sort_order, created_at",
            (owner_user_id,),
        ).fetchall()
        return [_conversation_group_from_row(row) for row in rows]

    def rename_for_owner(self, group_id: str, owner_user_id: str, name: str) -> bool:
        result = self._connection.execute(
            "UPDATE conversation_groups SET name = ?, updated_at = ? WHERE group_id = ? AND owner_user_id = ?",
            (name, _iso(datetime.now(timezone.utc)), group_id, owner_user_id),
        )
        return result.rowcount == 1

    def delete_for_owner(self, group_id: str, owner_user_id: str) -> bool:
        result = self._connection.execute(
            "DELETE FROM conversation_groups WHERE group_id = ? AND owner_user_id = ?",
            (group_id, owner_user_id),
        )
        return result.rowcount == 1

class SqliteMessageRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def append(self, record: MessageRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO messages (
                message_id, conversation_id, sequence, role, kind, text,
                payload_json, delivery_state, request_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.message_id,
                record.conversation_id,
                record.sequence,
                record.role,
                record.kind,
                record.text,
                json.dumps(record.payload, ensure_ascii=False, sort_keys=True),
                record.delivery_state,
                record.request_id,
                _iso(record.created_at),
            ),
        )

    def list_for_conversation(self, conversation_id: str) -> list[MessageRecord]:
        rows = self._connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY sequence, created_at",
            (conversation_id,),
        ).fetchall()
        return [
            MessageRecord(
                message_id=row["message_id"],
                conversation_id=row["conversation_id"],
                sequence=row["sequence"],
                role=row["role"],
                kind=row["kind"],
                text=row["text"],
                payload=json.loads(row["payload_json"]),
                delivery_state=row["delivery_state"],
                request_id=row["request_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def count_user_messages(self, conversation_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND role = 'user'",
            (conversation_id,),
        ).fetchone()
        return int(row[0])

    def first_user_message(self, conversation_id: str) -> MessageRecord | None:
        row = self._connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? AND role = 'user' "
            "ORDER BY sequence, created_at LIMIT 1",
            (conversation_id,),
        ).fetchone()
        return _message_from_row(row) if row is not None else None

    def last_user_message(self, conversation_id: str) -> MessageRecord | None:
        row = self._connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? AND role = 'user' "
            "ORDER BY sequence DESC, created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        return _message_from_row(row) if row is not None else None

    def find_by_request_id(
        self, conversation_id: str, request_id: str
    ) -> MessageRecord | None:
        row = self._connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? AND request_id = ?",
            (conversation_id, request_id),
        ).fetchone()
        if row is None:
            return None
        return self.list_for_conversation(conversation_id)[row["sequence"] - 1]

    def next_sequence(self, conversation_id: str) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return int(row[0])


class SqlitePendingActionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, record: PendingActionRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO pending_actions (
                action_id, conversation_id, tool_name, arguments_json,
                fingerprint, idempotency_key, confirmation_summary, status,
                result_json, failure_code, created_at, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.action_id,
                record.conversation_id,
                record.tool_name,
                json.dumps(record.arguments, ensure_ascii=False, sort_keys=True),
                record.fingerprint,
                record.idempotency_key,
                record.confirmation_summary,
                record.status,
                json.dumps(record.result, ensure_ascii=False) if record.result else None,
                record.failure_code,
                _iso(record.created_at),
                _iso(record.resolved_at),
            ),
        )

    def get(self, action_id: str) -> PendingActionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM pending_actions WHERE action_id = ?", (action_id,)
        ).fetchone()
        if row is None:
            return None
        return PendingActionRecord(
            action_id=row["action_id"],
            conversation_id=row["conversation_id"],
            tool_name=row["tool_name"],
            arguments=json.loads(row["arguments_json"]),
            fingerprint=row["fingerprint"],
            idempotency_key=row["idempotency_key"],
            confirmation_summary=row["confirmation_summary"],
            status=row["status"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            failure_code=row["failure_code"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )

    def transition(
        self, action_id: str, *, expected: ActionStatus, target: ActionStatus
    ) -> bool:
        terminal = target in {"rejected", "succeeded", "failed"}
        result = self._connection.execute(
            "UPDATE pending_actions SET status = ?, resolved_at = ? "
            "WHERE action_id = ? AND status = ?",
            (
                target,
                _iso(datetime.now(timezone.utc)) if terminal else None,
                action_id,
                expected,
            ),
        )
        return result.rowcount == 1

    def claim_if_no_active_handoff(
        self, action_id: str, conversation_id: str
    ) -> bool:
        result = self._connection.execute(
            "UPDATE pending_actions SET status='executing' "
            "WHERE action_id=? AND conversation_id=? AND status='pending' "
            "AND NOT EXISTS (SELECT 1 FROM human_handoffs "
            "WHERE conversation_id=? AND status IN ('open','in_progress'))",
            (action_id, conversation_id, conversation_id),
        )
        return result.rowcount == 1

    def has_executing_for_conversation(self, conversation_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM pending_actions WHERE conversation_id=? "
            "AND status='executing' LIMIT 1",
            (conversation_id,),
        ).fetchone()
        return row is not None

    def list_for_conversation(self, conversation_id: str) -> list[PendingActionRecord]:
        rows = self._connection.execute(
            "SELECT action_id FROM pending_actions WHERE conversation_id = ? "
            "ORDER BY created_at, action_id",
            (conversation_id,),
        ).fetchall()
        return [self.get(row[0]) for row in rows if self.get(row[0]) is not None]

    def set_outcome(
        self,
        action_id: str,
        *,
        status: ActionStatus,
        result: dict[str, Any] | None = None,
        failure_code: str | None = None,
    ) -> None:
        self._connection.execute(
            "UPDATE pending_actions SET status = ?, result_json = ?, failure_code = ?, "
            "resolved_at = ? WHERE action_id = ?",
            (
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                failure_code,
                _iso(datetime.now(timezone.utc)),
                action_id,
            ),
        )


class SqliteAuditEventRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def append(self, record: AuditEventRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO audit_events (
                event_id, conversation_id, action_id, event_type, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.event_id,
                record.conversation_id,
                record.action_id,
                record.event_type,
                json.dumps(record.payload, ensure_ascii=False, sort_keys=True),
                _iso(record.created_at),
            ),
        )

    def list_for_conversation(self, conversation_id: str) -> list[AuditEventRecord]:
        rows = self._connection.execute(
            "SELECT * FROM audit_events WHERE conversation_id = ? ORDER BY created_at, event_id",
            (conversation_id,),
        ).fetchall()
        return [
            AuditEventRecord(
                event_id=row["event_id"],
                conversation_id=row["conversation_id"],
                action_id=row["action_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def update_forbidden(self, event_id: str) -> bool:
        return False


class SqliteHumanHandoffRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, record: HumanHandoffRecord) -> None:
        self._connection.execute(
            """INSERT INTO human_handoffs (
                ticket_id,conversation_id,owner_user_id,reason,customer_message,
                context_summary,status,assigned_developer_user_id,created_at,
                updated_at,resolved_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.ticket_id, record.conversation_id, record.owner_user_id,
                record.reason, record.customer_message, record.context_summary,
                record.status, record.assigned_developer_user_id,
                _iso(record.created_at), _iso(record.updated_at),
                _iso(record.resolved_at),
            ),
        )

    def get(self, ticket_id: str) -> HumanHandoffRecord | None:
        row = self._connection.execute(
            "SELECT * FROM human_handoffs WHERE ticket_id=?", (ticket_id,)
        ).fetchone()
        return _handoff_from_row(row) if row is not None else None

    def get_active_for_conversation(
        self, conversation_id: str, owner_user_id: str | None = None
    ) -> HumanHandoffRecord | None:
        sql = (
            "SELECT * FROM human_handoffs WHERE conversation_id=? "
            "AND status IN ('open','in_progress')"
        )
        values: list[str] = [conversation_id]
        if owner_user_id is not None:
            sql += " AND owner_user_id=?"
            values.append(owner_user_id)
        sql += " ORDER BY created_at DESC LIMIT 1"
        row = self._connection.execute(sql, values).fetchone()
        return _handoff_from_row(row) if row is not None else None

    def get_latest_for_conversation(
        self, conversation_id: str, owner_user_id: str
    ) -> HumanHandoffRecord | None:
        row = self._connection.execute(
            "SELECT * FROM human_handoffs WHERE conversation_id=? AND owner_user_id=? "
            "ORDER BY updated_at DESC LIMIT 1",
            (conversation_id, owner_user_id),
        ).fetchone()
        return _handoff_from_row(row) if row is not None else None

    def list(self, status: HandoffStatus | None = None) -> list[HumanHandoffRecord]:
        if status is None:
            rows = self._connection.execute(
                "SELECT * FROM human_handoffs ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM human_handoffs WHERE status=? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        return [_handoff_from_row(row) for row in rows]

    def claim(self, ticket_id: str, developer_user_id: str) -> bool:
        now = _iso(datetime.now(timezone.utc))
        result = self._connection.execute(
            "UPDATE human_handoffs SET status='in_progress', "
            "assigned_developer_user_id=?, updated_at=? "
            "WHERE ticket_id=? AND status='open'",
            (developer_user_id, now, ticket_id),
        )
        return result.rowcount == 1

    def transition(
        self,
        ticket_id: str,
        *,
        expected: HandoffStatus,
        target: HandoffStatus,
        developer_user_id: str | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        terminal = target in {"resolved", "cancelled"}
        result = self._connection.execute(
            "UPDATE human_handoffs SET status=?, "
            "assigned_developer_user_id=COALESCE(?,assigned_developer_user_id), "
            "updated_at=?, resolved_at=? WHERE ticket_id=? AND status=?",
            (
                target, developer_user_id, _iso(now), _iso(now) if terminal else None,
                ticket_id, expected,
            ),
        )
        return result.rowcount == 1


class SqliteUserRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, record: UserRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO users (
                user_id, email, display_name, password_hash, role, status,
                must_change_password, created_by_user_id, created_at, updated_at,
                last_login_at, retail_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.user_id,
                record.email.strip().lower(),
                record.display_name,
                record.password_hash,
                record.role,
                record.status,
                int(record.must_change_password),
                record.created_by_user_id,
                _iso(record.created_at),
                _iso(record.updated_at),
                _iso(record.last_login_at),
                record.retail_user_id,
            ),
        )

    def get(self, user_id: str) -> UserRecord | None:
        row = self._connection.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return _user_from_row(row) if row is not None else None

    def get_by_email(self, email: str) -> UserRecord | None:
        row = self._connection.execute(
            "SELECT * FROM users WHERE lower(trim(email)) = ?",
            (email.strip().lower(),),
        ).fetchone()
        return _user_from_row(row) if row is not None else None

    def list_developers(self) -> list[UserRecord]:
        rows = self._connection.execute(
            "SELECT * FROM users WHERE role = 'developer' ORDER BY created_at, user_id"
        ).fetchall()
        return [_user_from_row(row) for row in rows]

    def update(self, record: UserRecord) -> None:
        result = self._connection.execute(
            """
            UPDATE users SET email = ?, display_name = ?, password_hash = ?, role = ?,
                status = ?, must_change_password = ?, updated_at = ?, last_login_at = ?,
                retail_user_id = ?
            WHERE user_id = ?
            """,
            (
                record.email.strip().lower(),
                record.display_name,
                record.password_hash,
                record.role,
                record.status,
                int(record.must_change_password),
                _iso(record.updated_at),
                _iso(record.last_login_at),
                record.retail_user_id,
                record.user_id,
            ),
        )
        if result.rowcount != 1:
            raise KeyError(record.user_id)


class SqliteAuthSessionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, record: AuthSessionRecord) -> None:
        self._connection.execute(
            "INSERT INTO auth_sessions (session_id, user_id, token_hash, created_at, "
            "expires_at, last_seen_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.session_id,
                record.user_id,
                record.token_hash,
                _iso(record.created_at),
                _iso(record.expires_at),
                _iso(record.last_seen_at),
                _iso(record.revoked_at),
            ),
        )

    def get_by_token_hash(self, token_hash: str) -> AuthSessionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM auth_sessions WHERE token_hash = ?", (token_hash,)
        ).fetchone()
        return _session_from_row(row) if row is not None else None

    def revoke(self, session_id: str) -> bool:
        result = self._connection.execute(
            "UPDATE auth_sessions SET revoked_at = ? WHERE session_id = ? AND revoked_at IS NULL",
            (_iso(datetime.now(timezone.utc)), session_id),
        )
        return result.rowcount == 1

    def revoke_all_for_user(self, user_id: str) -> int:
        result = self._connection.execute(
            "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (_iso(datetime.now(timezone.utc)), user_id),
        )
        return result.rowcount


class SqliteAuthAuditRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def append(self, record: AuthAuditEventRecord) -> None:
        self._connection.execute(
            "INSERT INTO auth_audit_events (event_id, user_id, event_type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                record.event_id,
                record.user_id,
                record.event_type,
                json.dumps(record.payload, ensure_ascii=False, sort_keys=True),
                _iso(record.created_at),
            ),
        )

    def list_for_user(self, user_id: str) -> list[AuthAuditEventRecord]:
        rows = self._connection.execute(
            "SELECT * FROM auth_audit_events WHERE user_id = ? ORDER BY created_at, event_id",
            (user_id,),
        ).fetchall()
        return [
            AuthAuditEventRecord(
                event_id=row["event_id"],
                user_id=row["user_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]


class SqliteFeedbackRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def append(self, record: FeedbackRecord) -> None:
        self._connection.execute(
            "INSERT INTO user_feedback (feedback_id,user_id,conversation_id,message_id,rating,category,comment,status,developer_note,created_at,updated_at,resolved_by_user_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (record.feedback_id, record.user_id, record.conversation_id, record.message_id,
             record.rating, record.category, record.comment, record.status, record.developer_note,
             _iso(record.created_at), _iso(record.updated_at), record.resolved_by_user_id),
        )

    def get(self, feedback_id: str) -> FeedbackRecord | None:
        row = self._connection.execute("SELECT * FROM user_feedback WHERE feedback_id=?", (feedback_id,)).fetchone()
        return _feedback_from_row(row) if row else None

    def list_for_conversation(self, conversation_id: str) -> list[FeedbackRecord]:
        rows = self._connection.execute("SELECT * FROM user_feedback WHERE conversation_id=? ORDER BY created_at DESC", (conversation_id,)).fetchall()
        return [_feedback_from_row(row) for row in rows]

    def list_filtered(self, *, status=None, rating=None, category=None, query=None, limit=50, offset=0):
        clauses, args = [], []
        for column, value in (("status", status), ("rating", rating), ("category", category)):
            if value:
                clauses.append(f"{column}=?"); args.append(value)
        if query:
            clauses.append("(comment LIKE ? OR COALESCE(conversation_id, '') LIKE ?)"); args.extend([f"%{query}%"] * 2)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total = self._connection.execute("SELECT COUNT(*) FROM user_feedback" + where, args).fetchone()[0]
        rows = self._connection.execute("SELECT * FROM user_feedback" + where + " ORDER BY created_at DESC LIMIT ? OFFSET ?", (*args, min(limit, 100), offset)).fetchall()
        return [_feedback_from_row(row) for row in rows], total

    def update_review(self, feedback_id: str, *, status: str, developer_note: str | None, resolved_by_user_id: str | None, updated_at: datetime) -> FeedbackRecord:
        self._connection.execute("UPDATE user_feedback SET status=?,developer_note=?,resolved_by_user_id=?,updated_at=? WHERE feedback_id=?", (status, developer_note, resolved_by_user_id, _iso(updated_at), feedback_id))
        result = self.get(feedback_id)
        if result is None: raise KeyError(feedback_id)
        return result


class SqliteRuntimeIssueRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert_occurrence(self, record: RuntimeIssueRecord) -> RuntimeIssueRecord:
        self._connection.execute(
            """INSERT INTO runtime_issues (issue_id,fingerprint,source,severity,error_code,summary,sanitized_detail,status,occurrence_count,first_seen_at,last_seen_at,last_request_id,last_conversation_id,context_json,developer_note,resolved_by_user_id,resolved_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(fingerprint) DO UPDATE SET occurrence_count=runtime_issues.occurrence_count+1,last_seen_at=excluded.last_seen_at,last_request_id=excluded.last_request_id,last_conversation_id=excluded.last_conversation_id,context_json=excluded.context_json""",
            (record.issue_id, record.fingerprint, record.source, record.severity, record.error_code, record.summary, record.sanitized_detail, record.status, record.occurrence_count, _iso(record.first_seen_at), _iso(record.last_seen_at), record.last_request_id, record.last_conversation_id, json.dumps(record.context, ensure_ascii=False), record.developer_note, record.resolved_by_user_id, _iso(record.resolved_at)),
        )
        row = self._connection.execute("SELECT * FROM runtime_issues WHERE fingerprint=?", (record.fingerprint,)).fetchone()
        return _issue_from_row(row)

    def get(self, issue_id: str) -> RuntimeIssueRecord | None:
        row = self._connection.execute("SELECT * FROM runtime_issues WHERE issue_id=?", (issue_id,)).fetchone()
        return _issue_from_row(row) if row else None

    def list_filtered(self, *, status=None, severity=None, source=None, query=None, limit=50, offset=0):
        clauses, args = [], []
        for column, value in (("status", status), ("severity", severity), ("source", source)):
            if value: clauses.append(f"{column}=?"); args.append(value)
        if query: clauses.append("(summary LIKE ? OR error_code LIKE ?)"); args.extend([f"%{query}%"] * 2)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total = self._connection.execute("SELECT COUNT(*) FROM runtime_issues" + where, args).fetchone()[0]
        rows = self._connection.execute("SELECT * FROM runtime_issues" + where + " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'error' THEN 1 ELSE 2 END,last_seen_at DESC LIMIT ? OFFSET ?", (*args, min(limit, 100), offset)).fetchall()
        return [_issue_from_row(row) for row in rows], total

    def update_review(self, issue_id: str, *, status: str, developer_note: str | None, resolved_by_user_id: str | None, resolved_at: datetime | None) -> RuntimeIssueRecord:
        self._connection.execute("UPDATE runtime_issues SET status=?,developer_note=?,resolved_by_user_id=?,resolved_at=? WHERE issue_id=?", (status, developer_note, resolved_by_user_id, _iso(resolved_at), issue_id))
        result = self.get(issue_id)
        if result is None: raise KeyError(issue_id)
        return result


class SqliteAgentRunRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, record: AgentRunRecord) -> None:
        self._connection.execute(
            """INSERT INTO agent_runs (
                run_id,conversation_id,source,planner_type,model,tool_backend,
                policy_version,data_version,status,stopped_reason,business_success,
                confirmation_gate_success,confirmed_outcome_success,exact_match,
                step_count,prompt_tokens,completion_tokens,total_tokens,
                estimated_cost_cny,started_at,finished_at,duration_ms,error_code,issue_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            _agent_run_values(record),
        )

    def get(self, run_id: str) -> AgentRunRecord | None:
        row = self._connection.execute(
            "SELECT * FROM agent_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        return _agent_run_from_row(row) if row else None

    def finish(self, run_id: str, **updates: Any) -> AgentRunRecord:
        allowed = {
            "status", "stopped_reason", "business_success",
            "confirmation_gate_success", "confirmed_outcome_success",
            "exact_match", "step_count", "prompt_tokens", "completion_tokens",
            "total_tokens", "estimated_cost_cny", "finished_at", "duration_ms",
            "error_code", "issue_id",
        }
        if not updates or not set(updates) <= allowed:
            raise ValueError("Unsupported agent run update")
        columns = ",".join(f"{name}=?" for name in updates)
        values = [_db_value(updates[name]) for name in updates]
        result = self._connection.execute(
            f"UPDATE agent_runs SET {columns} WHERE run_id=? AND status='running'",
            (*values, run_id),
        )
        if result.rowcount != 1:
            raise KeyError(run_id)
        record = self.get(run_id)
        if record is None:
            raise KeyError(run_id)
        return record

    def list_all(self) -> list[AgentRunRecord]:
        rows = self._connection.execute(
            "SELECT * FROM agent_runs ORDER BY started_at DESC, run_id"
        ).fetchall()
        return [_agent_run_from_row(row) for row in rows]


class SqliteAgentRunStepRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def append(self, record: AgentRunStepRecord) -> AgentRunStepRecord:
        sequence = record.sequence
        if sequence <= 0:
            sequence = int(
                self._connection.execute(
                    "SELECT COALESCE(MAX(sequence),0)+1 FROM agent_run_steps WHERE run_id=?",
                    (record.run_id,),
                ).fetchone()[0]
            )
        stored = record.model_copy(update={"sequence": sequence})
        self._connection.execute(
            """INSERT INTO agent_run_steps (
                step_id,run_id,sequence,kind,name,status,duration_ms,summary_json,
                started_at,finished_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                stored.step_id, stored.run_id, stored.sequence, stored.kind,
                stored.name, stored.status, stored.duration_ms,
                json.dumps(stored.summary, ensure_ascii=False, sort_keys=True),
                _iso(stored.started_at), _iso(stored.finished_at),
            ),
        )
        return stored

    def list_for_run(self, run_id: str) -> list[AgentRunStepRecord]:
        rows = self._connection.execute(
            "SELECT * FROM agent_run_steps WHERE run_id=? ORDER BY sequence",
            (run_id,),
        ).fetchall()
        return [_agent_run_step_from_row(row) for row in rows]

    def list_all(self) -> list[AgentRunStepRecord]:
        rows = self._connection.execute(
            "SELECT * FROM agent_run_steps ORDER BY started_at,run_id,sequence"
        ).fetchall()
        return [_agent_run_step_from_row(row) for row in rows]


class SqliteRegressionCaseRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, record: RegressionCaseRecord) -> None:
        self._connection.execute(
            """INSERT INTO regression_cases (
                case_id,name,description,origin_type,origin_id,fixture_type,
                fixture_json,expected_json,status,created_by_user_id,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.case_id, record.name, record.description, record.origin_type,
                record.origin_id, record.fixture_type,
                json.dumps(record.fixture, ensure_ascii=False, sort_keys=True),
                json.dumps(record.expected, ensure_ascii=False, sort_keys=True),
                record.status, record.created_by_user_id, _iso(record.created_at),
                _iso(record.updated_at),
            ),
        )

    def get(self, case_id: str) -> RegressionCaseRecord | None:
        row = self._connection.execute(
            "SELECT * FROM regression_cases WHERE case_id=?", (case_id,)
        ).fetchone()
        return _regression_case_from_row(row) if row else None

    def get_by_origin(self, origin_type: str, origin_id: str) -> RegressionCaseRecord | None:
        row = self._connection.execute(
            "SELECT * FROM regression_cases WHERE origin_type=? AND origin_id=?",
            (origin_type, origin_id),
        ).fetchone()
        return _regression_case_from_row(row) if row else None

    def list_all(self) -> list[RegressionCaseRecord]:
        rows = self._connection.execute(
            "SELECT * FROM regression_cases ORDER BY updated_at DESC, case_id"
        ).fetchall()
        return [_regression_case_from_row(row) for row in rows]

    def update(self, record: RegressionCaseRecord) -> RegressionCaseRecord:
        changed = self._connection.execute(
            """UPDATE regression_cases SET
                name=?,description=?,origin_type=?,origin_id=?,fixture_type=?,
                fixture_json=?,expected_json=?,status=?,updated_at=?
                WHERE case_id=?""",
            (
                record.name, record.description, record.origin_type, record.origin_id,
                record.fixture_type,
                json.dumps(record.fixture, ensure_ascii=False, sort_keys=True),
                json.dumps(record.expected, ensure_ascii=False, sort_keys=True),
                record.status, _iso(record.updated_at), record.case_id,
            ),
        ).rowcount
        if not changed:
            raise KeyError(record.case_id)
        return record

    def delete(self, case_id: str) -> bool:
        return self._connection.execute(
            "DELETE FROM regression_cases WHERE case_id=?", (case_id,)
        ).rowcount == 1


class SqliteRegressionCaseRunRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, record: RegressionCaseRunRecord) -> None:
        self._connection.execute(
            """INSERT INTO regression_case_runs (
                case_run_id,case_id,agent_run_id,batch_id,status,failure_reason,
                created_at,finished_at
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                record.case_run_id, record.case_id, record.agent_run_id,
                record.batch_id, record.status, record.failure_reason,
                _iso(record.created_at), _iso(record.finished_at),
            ),
        )

    def latest_for_case(self, case_id: str) -> RegressionCaseRunRecord | None:
        row = self._connection.execute(
            "SELECT * FROM regression_case_runs WHERE case_id=? "
            "ORDER BY created_at DESC, case_run_id DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        return _regression_case_run_from_row(row) if row else None

    def list_for_batch(self, batch_id: str) -> list[RegressionCaseRunRecord]:
        rows = self._connection.execute(
            "SELECT * FROM regression_case_runs WHERE batch_id=? ORDER BY created_at,case_run_id",
            (batch_id,),
        ).fetchall()
        return [_regression_case_run_from_row(row) for row in rows]

    def get(self, case_run_id: str) -> RegressionCaseRunRecord | None:
        row = self._connection.execute(
            "SELECT * FROM regression_case_runs WHERE case_run_id=?", (case_run_id,)
        ).fetchone()
        return _regression_case_run_from_row(row) if row else None


class SqliteUnitOfWork:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._lock = RLock()
        self.conversations = SqliteConversationRepository(self._connection)
        self.conversation_groups = SqliteConversationGroupRepository(self._connection)
        self.messages = SqliteMessageRepository(self._connection)
        self.pending_actions = SqlitePendingActionRepository(self._connection)
        self.audit_events = SqliteAuditEventRepository(self._connection)
        self.human_handoffs = SqliteHumanHandoffRepository(self._connection)
        self.users = SqliteUserRepository(self._connection)
        self.customer_addresses = SqliteCustomerAddressRepository(self._connection)
        self.demo_order_metadata = SqliteDemoOrderMetadataRepository(self._connection)
        self.policy_documents = SqlitePolicyDocumentRepository(self._connection)
        self.policy_chunks = SqlitePolicyChunkRepository(self._connection)
        self.auth_sessions = SqliteAuthSessionRepository(self._connection)
        self.auth_audit_events = SqliteAuthAuditRepository(self._connection)
        self.feedback = SqliteFeedbackRepository(self._connection)
        self.runtime_issues = SqliteRuntimeIssueRepository(self._connection)
        self.agent_runs = SqliteAgentRunRepository(self._connection)
        self.agent_run_steps = SqliteAgentRunStepRepository(self._connection)
        self.regression_cases = SqliteRegressionCaseRepository(self._connection)
        self.regression_case_runs = SqliteRegressionCaseRunRepository(self._connection)

    def initialize(self) -> None:
        migrations = sorted((Path(__file__).parent / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
        with self._lock:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            self._connection.commit()
            applied = {row[0] for row in self._connection.execute("SELECT version FROM schema_migrations")}
            for migration in migrations:
                version = int(migration.name.split("_", 1)[0])
                if version in applied:
                    continue
                applied_at = _iso(datetime.now(timezone.utc)).replace("'", "''")
                script = migration.read_text(encoding="utf-8")
                try:
                    self._connection.executescript(
                        "BEGIN IMMEDIATE;\n"
                        + script
                        + f"\nINSERT INTO schema_migrations(version, applied_at) VALUES ({version}, '{applied_at}');\n"
                        + "COMMIT;"
                    )
                except BaseException:
                    self._connection.rollback()
                    raise

    @contextmanager
    def transaction(self) -> Iterator[SqliteUnitOfWork]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def pragma(self, name: str) -> Any:
        if name not in {"foreign_keys", "journal_mode"}:
            raise ValueError(f"Unsupported pragma: {name}")
        return self._connection.execute(f"PRAGMA {name}").fetchone()[0]

    def applied_migrations(self) -> list[int]:
        rows = self._connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        return [row[0] for row in rows]

    def close(self) -> None:
        self._connection.close()


def _conversation_from_row(row: sqlite3.Row) -> ConversationRecord:
    return ConversationRecord(
        conversation_id=row["conversation_id"],
        title=row["title"],
        status=row["status"],
        owner_user_id=row["owner_user_id"],
        group_id=row["group_id"],
        is_pinned=bool(row["is_pinned"]),
        title_source=row["title_source"],
        authenticated_user_id=row["authenticated_user_id"],
        authentication_method=row["authentication_method"],
        state=CustomerAgentState.model_validate_json(row["state_json"]),
        last_error_code=row["last_error_code"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _conversation_group_from_row(row: sqlite3.Row) -> ConversationGroupRecord:
    return ConversationGroupRecord(
        group_id=row["group_id"],
        owner_user_id=row["owner_user_id"],
        name=row["name"],
        sort_order=row["sort_order"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _handoff_from_row(row: sqlite3.Row) -> HumanHandoffRecord:
    return HumanHandoffRecord(
        ticket_id=row["ticket_id"],
        conversation_id=row["conversation_id"],
        owner_user_id=row["owner_user_id"],
        reason=row["reason"],
        customer_message=row["customer_message"],
        context_summary=row["context_summary"],
        status=row["status"],
        assigned_developer_user_id=row["assigned_developer_user_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        resolved_at=row["resolved_at"],
    )


def _user_from_row(row: sqlite3.Row) -> UserRecord:
    return UserRecord(
        user_id=row["user_id"],
        email=row["email"],
        display_name=row["display_name"],
        password_hash=row["password_hash"],
        role=row["role"],
        status=row["status"],
        must_change_password=bool(row["must_change_password"]),
        retail_user_id=row["retail_user_id"],
        created_by_user_id=row["created_by_user_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_login_at=row["last_login_at"],
    )


def _session_from_row(row: sqlite3.Row) -> AuthSessionRecord:
    return AuthSessionRecord(
        session_id=row["session_id"],
        user_id=row["user_id"],
        token_hash=row["token_hash"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        last_seen_at=row["last_seen_at"],
        revoked_at=row["revoked_at"],
    )


def _feedback_from_row(row: sqlite3.Row) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=row["feedback_id"], user_id=row["user_id"],
        conversation_id=row["conversation_id"], message_id=row["message_id"],
        rating=row["rating"], category=row["category"], comment=row["comment"],
        status=row["status"], developer_note=row["developer_note"],
        created_at=row["created_at"], updated_at=row["updated_at"],
        resolved_by_user_id=row["resolved_by_user_id"],
    )


def _issue_from_row(row: sqlite3.Row) -> RuntimeIssueRecord:
    return RuntimeIssueRecord(
        issue_id=row["issue_id"], fingerprint=row["fingerprint"], source=row["source"],
        severity=row["severity"], error_code=row["error_code"], summary=row["summary"],
        sanitized_detail=row["sanitized_detail"], status=row["status"],
        occurrence_count=row["occurrence_count"], first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"], last_request_id=row["last_request_id"],
        last_conversation_id=row["last_conversation_id"], context=json.loads(row["context_json"]),
        developer_note=row["developer_note"], resolved_by_user_id=row["resolved_by_user_id"],
        resolved_at=row["resolved_at"],
    )


def _db_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, bool):
        return int(value)
    return value


def _agent_run_values(record: AgentRunRecord) -> tuple[Any, ...]:
    return (
        record.run_id, record.conversation_id, record.source, record.planner_type,
        record.model, record.tool_backend, record.policy_version, record.data_version,
        record.status, record.stopped_reason, _db_value(record.business_success),
        _db_value(record.confirmation_gate_success),
        _db_value(record.confirmed_outcome_success), _db_value(record.exact_match),
        record.step_count, record.prompt_tokens, record.completion_tokens,
        record.total_tokens, record.estimated_cost_cny, _iso(record.started_at),
        _iso(record.finished_at), record.duration_ms, record.error_code, record.issue_id,
    )


def _agent_run_from_row(row: sqlite3.Row) -> AgentRunRecord:
    values = dict(row)
    for key in (
        "business_success", "confirmation_gate_success",
        "confirmed_outcome_success", "exact_match",
    ):
        values[key] = bool(values[key]) if values[key] is not None else None
    return AgentRunRecord.model_validate(values)


def _agent_run_step_from_row(row: sqlite3.Row) -> AgentRunStepRecord:
    values = dict(row)
    values["summary"] = json.loads(values.pop("summary_json"))
    return AgentRunStepRecord.model_validate(values)


def _regression_case_from_row(row: sqlite3.Row) -> RegressionCaseRecord:
    values = dict(row)
    values["fixture"] = json.loads(values.pop("fixture_json"))
    values["expected"] = json.loads(values.pop("expected_json"))
    return RegressionCaseRecord.model_validate(values)


def _regression_case_run_from_row(row: sqlite3.Row) -> RegressionCaseRunRecord:
    return RegressionCaseRunRecord.model_validate(dict(row))

