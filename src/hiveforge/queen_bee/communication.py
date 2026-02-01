"""Colony間通信 - メッセージング基盤

複数Colonyが協調動作するための通信機構を提供。
既存のConference機能と連携してColony間でメッセージをやり取り。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ulid import ULID


class MessageType(str, Enum):
    """Colony間メッセージタイプ"""

    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    BROADCAST = "broadcast"


class MessagePriority(str, Enum):
    """メッセージ優先度"""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class ColonyMessage:
    """Colony間メッセージ"""

    message_id: str
    from_colony: str
    to_colony: str | None  # Noneはブロードキャスト
    message_type: MessageType
    priority: MessagePriority
    payload: dict[str, Any]
    correlation_id: str | None = None  # リクエスト-レスポンス紐付け


@dataclass
class MessageQueue:
    """Colonyごとのメッセージキュー"""

    colony_id: str
    pending: list[ColonyMessage] = field(default_factory=list)
    processed: list[str] = field(default_factory=list)  # 処理済みmessage_id

    def enqueue(self, message: ColonyMessage) -> None:
        """メッセージを追加"""
        # 優先度順にソート挿入
        priority_order = {
            MessagePriority.URGENT: 0,
            MessagePriority.HIGH: 1,
            MessagePriority.NORMAL: 2,
            MessagePriority.LOW: 3,
        }
        insert_idx = 0
        for i, m in enumerate(self.pending):
            if priority_order[message.priority] < priority_order[m.priority]:
                insert_idx = i
                break
            insert_idx = i + 1
        self.pending.insert(insert_idx, message)

    def dequeue(self) -> ColonyMessage | None:
        """次のメッセージを取得"""
        if not self.pending:
            return None
        message = self.pending.pop(0)
        self.processed.append(message.message_id)
        return message

    def peek(self) -> ColonyMessage | None:
        """次のメッセージを確認（取り出さない）"""
        return self.pending[0] if self.pending else None


class ColonyMessenger:
    """Colony間メッセージング管理"""

    def __init__(self) -> None:
        self._queues: dict[str, MessageQueue] = {}
        self._all_colonies: set[str] = set()

    def register_colony(self, colony_id: str) -> None:
        """Colonyを登録"""
        self._all_colonies.add(colony_id)
        if colony_id not in self._queues:
            self._queues[colony_id] = MessageQueue(colony_id=colony_id)

    def unregister_colony(self, colony_id: str) -> None:
        """Colonyを登録解除"""
        self._all_colonies.discard(colony_id)
        self._queues.pop(colony_id, None)

    def send(
        self,
        from_colony: str,
        to_colony: str,
        message_type: MessageType,
        payload: dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
        correlation_id: str | None = None,
    ) -> str:
        """メッセージを送信"""
        message_id = str(ULID())
        message = ColonyMessage(
            message_id=message_id,
            from_colony=from_colony,
            to_colony=to_colony,
            message_type=message_type,
            priority=priority,
            payload=payload,
            correlation_id=correlation_id,
        )

        if to_colony in self._queues:
            self._queues[to_colony].enqueue(message)

        return message_id

    def broadcast(
        self,
        from_colony: str,
        message_type: MessageType,
        payload: dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> str:
        """全Colonyにブロードキャスト"""
        message_id = str(ULID())

        for colony_id in self._all_colonies:
            if colony_id == from_colony:
                continue
            message = ColonyMessage(
                message_id=message_id,
                from_colony=from_colony,
                to_colony=None,
                message_type=MessageType.BROADCAST,
                priority=priority,
                payload=payload,
            )
            self._queues[colony_id].enqueue(message)

        return message_id

    def receive(self, colony_id: str) -> ColonyMessage | None:
        """メッセージを受信"""
        if colony_id not in self._queues:
            return None
        return self._queues[colony_id].dequeue()

    def peek(self, colony_id: str) -> ColonyMessage | None:
        """次のメッセージを確認（取り出さない）"""
        if colony_id not in self._queues:
            return None
        return self._queues[colony_id].peek()

    def pending_count(self, colony_id: str) -> int:
        """未処理メッセージ数"""
        if colony_id not in self._queues:
            return 0
        return len(self._queues[colony_id].pending)

    def request(
        self,
        from_colony: str,
        to_colony: str,
        payload: dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> str:
        """リクエストを送信（レスポンスを期待）"""
        return self.send(
            from_colony=from_colony,
            to_colony=to_colony,
            message_type=MessageType.REQUEST,
            payload=payload,
            priority=priority,
        )

    def respond(
        self,
        original_message: ColonyMessage,
        payload: dict[str, Any],
    ) -> str:
        """リクエストにレスポンス"""
        return self.send(
            from_colony=original_message.to_colony or "",
            to_colony=original_message.from_colony,
            message_type=MessageType.RESPONSE,
            payload=payload,
            priority=original_message.priority,
            correlation_id=original_message.message_id,
        )


class ResourceConflict:
    """リソース競合の検出と解決"""

    def __init__(self) -> None:
        # リソースID -> 保持しているColony
        self._locks: dict[str, str] = {}
        # 待機キュー: リソースID -> [colony_id, ...]
        self._waiting: dict[str, list[str]] = {}

    def try_acquire(self, resource_id: str, colony_id: str) -> bool:
        """リソースのロック取得を試みる"""
        if resource_id not in self._locks:
            self._locks[resource_id] = colony_id
            return True
        if self._locks[resource_id] == colony_id:
            return True  # 既に保持
        return False

    def release(self, resource_id: str, colony_id: str) -> str | None:
        """リソースを解放し、次の待機Colonyを返す"""
        if resource_id not in self._locks:
            return None
        if self._locks[resource_id] != colony_id:
            return None

        del self._locks[resource_id]

        # 待機キューから次のColonyにロックを渡す
        if resource_id in self._waiting and self._waiting[resource_id]:
            next_colony = self._waiting[resource_id].pop(0)
            self._locks[resource_id] = next_colony
            if not self._waiting[resource_id]:
                del self._waiting[resource_id]
            return next_colony

        return None

    def wait_for(self, resource_id: str, colony_id: str) -> None:
        """リソースの待機キューに追加"""
        if resource_id not in self._waiting:
            self._waiting[resource_id] = []
        if colony_id not in self._waiting[resource_id]:
            self._waiting[resource_id].append(colony_id)

    def get_holder(self, resource_id: str) -> str | None:
        """リソースの現在の保持者を取得"""
        return self._locks.get(resource_id)

    def get_waiting(self, resource_id: str) -> list[str]:
        """リソースの待機Colonyリストを取得"""
        return self._waiting.get(resource_id, []).copy()

    def is_deadlock(self, colony_ids: list[str]) -> bool:
        """デッドロック検出（簡易版）

        指定されたColonyが互いのリソースを待っている場合True。
        """
        # 各Colonyが保持しているリソースを取得
        held_by: dict[str, set[str]] = {}
        for resource_id, holder in self._locks.items():
            if holder not in held_by:
                held_by[holder] = set()
            held_by[holder].add(resource_id)

        # 各Colonyが待っているリソースを取得
        waiting_for: dict[str, set[str]] = {}
        for resource_id, waiters in self._waiting.items():
            for waiter in waiters:
                if waiter not in waiting_for:
                    waiting_for[waiter] = set()
                waiting_for[waiter].add(resource_id)

        # 循環チェック
        for colony_id in colony_ids:
            waiting = waiting_for.get(colony_id, set())
            for resource_id in waiting:
                holder = self._locks.get(resource_id)
                if holder and holder in colony_ids and holder != colony_id:
                    # holderもcolony_idのリソースを待っているか
                    holder_waiting = waiting_for.get(holder, set())
                    for hw_resource in holder_waiting:
                        if self._locks.get(hw_resource) == colony_id:
                            return True

        return False
