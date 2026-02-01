"""Akashic Record ストレージのテスト"""

from datetime import UTC

import pytest

from hiveforge.core.ar import AkashicRecord
from hiveforge.core.events import (
    RunStartedEvent,
    TaskCreatedEvent,
    parse_event,
)


class TestAkashicRecord:
    """AkashicRecordのテスト"""

    def test_append_and_replay(self, temp_vault):
        """イベントの追記とリプレイ"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-001"

        # イベントを追記
        event1 = RunStartedEvent(run_id=run_id, payload={"goal": "Test"})
        event2 = TaskCreatedEvent(
            run_id=run_id,
            task_id="task-001",
            payload={"title": "Task 1"},
        )

        ar.append(event1, run_id)
        ar.append(event2, run_id)

        # リプレイ
        events = list(ar.replay(run_id))
        assert len(events) == 2
        assert events[0].type == event1.type
        assert events[1].type == event2.type

    def test_event_chain_integrity(self, temp_vault):
        """イベントチェーンの整合性"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-002"

        # 複数イベントを追記
        for i in range(5):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i:03d}",
                payload={"title": f"Task {i}"},
            )
            ar.append(event, run_id)

        # チェーンを検証
        valid, error = ar.verify_chain(run_id)
        assert valid is True
        assert error is None

    def test_list_runs(self, temp_vault):
        """Run一覧の取得"""
        ar = AkashicRecord(temp_vault)

        # 複数のRunを作成
        for i in range(3):
            run_id = f"run-{i:03d}"
            event = RunStartedEvent(run_id=run_id, payload={"goal": f"Goal {i}"})
            ar.append(event, run_id)

        runs = ar.list_runs()
        assert len(runs) == 3
        assert "run-000" in runs
        assert "run-001" in runs
        assert "run-002" in runs

    def test_count_events(self, temp_vault):
        """イベント数のカウント"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-count"

        # イベントを追記
        for i in range(10):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"Task {i}"},
            )
            ar.append(event, run_id)

        count = ar.count_events(run_id)
        assert count == 10

    def test_get_last_event(self, temp_vault):
        """最後のイベント取得"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-last"

        # イベントを追記
        event1 = RunStartedEvent(run_id=run_id, payload={"goal": "Test"})
        event2 = TaskCreatedEvent(
            run_id=run_id,
            task_id="task-001",
            payload={"title": "Last Task"},
        )

        ar.append(event1, run_id)
        ar.append(event2, run_id)

        last = ar.get_last_event(run_id)
        assert last is not None
        assert last.task_id == "task-001"

    def test_replay_empty_run(self, temp_vault):
        """存在しないRunのリプレイは空"""
        ar = AkashicRecord(temp_vault)
        events = list(ar.replay("nonexistent-run"))
        assert len(events) == 0

    def test_export_run(self, temp_vault):
        """Runのエクスポート"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-export"

        # イベントを追記
        for i in range(5):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"Task {i}"},
            )
            ar.append(event, run_id)

        # エクスポート
        export_path = temp_vault / "export.jsonl"
        count = ar.export_run(run_id, export_path)

        assert count == 5
        assert export_path.exists()

        # エクスポートファイルを検証
        with open(export_path) as f:
            lines = f.readlines()
        assert len(lines) == 5


class TestAkashicRecordEdgeCases:
    """AkashicRecord のエッジケーステスト"""

    def test_append_without_run_id_raises_error(self, temp_vault):
        """run_idがない場合はエラーになる"""
        # Arrange: ARとrun_idがNoneのイベント
        ar = AkashicRecord(temp_vault)
        event = RunStartedEvent(run_id=None, payload={"goal": "Test"})

        # Act & Assert: run_idなしでappendするとエラー
        with pytest.raises(ValueError, match="run_id must be specified"):
            ar.append(event, run_id=None)

    def test_replay_with_since_filter(self, temp_vault):
        """since パラメータによる時刻フィルタリング"""
        from datetime import datetime, timedelta

        ar = AkashicRecord(temp_vault)
        run_id = "test-run-since"

        # 複数イベントを追記
        events_created = []
        for i in range(5):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"Task {i}"},
            )
            appended = ar.append(event, run_id)
            events_created.append(appended)

        # 中間のタイムスタンプ以降でフィルタ
        # 全イベントはほぼ同時刻なので、最初のイベントより前の時刻を使う
        since_time = events_created[0].timestamp - timedelta(seconds=1)
        filtered = list(ar.replay(run_id, since=since_time))
        assert len(filtered) == 5  # 全て取得

        # 未来の時刻を使うと何も取得されない
        future_time = datetime.now(UTC) + timedelta(hours=1)
        filtered = list(ar.replay(run_id, since=future_time))
        assert len(filtered) == 0

    def test_get_last_event_nonexistent_run(self, temp_vault):
        """存在しないRunの最終イベントはNone"""
        ar = AkashicRecord(temp_vault)
        result = ar.get_last_event("nonexistent-run")
        assert result is None

    def test_count_events_nonexistent_run(self, temp_vault):
        """存在しないRunのイベント数は0"""
        ar = AkashicRecord(temp_vault)
        count = ar.count_events("nonexistent-run")
        assert count == 0

    def test_verify_chain_detects_tampering(self, temp_vault):
        """改ざんされたチェーンを検出"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-tamper"

        # イベントを追記
        for i in range(3):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"Task {i}"},
            )
            ar.append(event, run_id)

        # ファイルを直接改ざん
        events_file = temp_vault / run_id / "events.jsonl"
        with open(events_file) as f:
            lines = f.readlines()

        # 2行目のprev_hashを改ざん
        import json

        data = json.loads(lines[1])
        data["prev_hash"] = "tampered_hash"
        lines[1] = json.dumps(data) + "\n"

        with open(events_file, "w") as f:
            f.writelines(lines)

        # 検証
        valid, error = ar.verify_chain(run_id)
        assert valid is False
        assert "Hash mismatch" in error

    def test_list_runs_excludes_directories_without_events(self, temp_vault):
        """events.jsonlがないディレクトリは除外される"""
        ar = AkashicRecord(temp_vault)

        # 正常なRunを作成
        event = RunStartedEvent(run_id="valid-run", payload={"goal": "Test"})
        ar.append(event, "valid-run")

        # events.jsonlがないディレクトリを作成
        empty_dir = temp_vault / "empty-run"
        empty_dir.mkdir()

        runs = ar.list_runs()
        assert "valid-run" in runs
        assert "empty-run" not in runs

    def test_replay_skips_empty_lines(self, temp_vault):
        """空行を含むファイルでもリプレイできる"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-empty-lines"

        # イベントを追記
        event = RunStartedEvent(run_id=run_id, payload={"goal": "Test"})
        ar.append(event, run_id)

        # 空行を追加
        events_file = temp_vault / run_id / "events.jsonl"
        with open(events_file, "a") as f:
            f.write("\n\n")  # 空行を追加

        # リプレイ
        events = list(ar.replay(run_id))
        assert len(events) == 1

    def test_get_last_event_with_empty_lines(self, temp_vault):
        """空行を含むファイルでも最終イベントを取得できる"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-last-empty"

        # イベントを追記
        event = RunStartedEvent(run_id=run_id, payload={"goal": "Test"})
        ar.append(event, run_id)

        # 空行を追加
        events_file = temp_vault / run_id / "events.jsonl"
        with open(events_file, "a") as f:
            f.write("\n\n")  # 末尾に空行

        # 最終イベント取得
        last = ar.get_last_event(run_id)
        assert last is not None

    def test_get_last_event_file_with_only_empty_lines(self, temp_vault):
        """空行のみのファイルではNoneを返す"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-only-empty"

        # ディレクトリと空行のみのファイルを作成
        run_dir = temp_vault / run_id
        run_dir.mkdir()
        events_file = run_dir / "events.jsonl"
        with open(events_file, "w") as f:
            f.write("\n\n\n")  # 空行のみ

        # 最終イベント取得
        last = ar.get_last_event(run_id)
        assert last is None

    def test_count_events_with_empty_lines(self, temp_vault):
        """空行を含むファイルでも正しくカウントする"""
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-count-empty"

        # イベントを追記
        for i in range(3):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"Task {i}"},
            )
            ar.append(event, run_id)

        # 空行を挿入
        events_file = temp_vault / run_id / "events.jsonl"
        with open(events_file) as f:
            content = f.read()
        # 途中に空行を挿入
        lines = content.split("\n")
        new_content = "\n\n".join(lines)  # 空行を挿入
        with open(events_file, "w") as f:
            f.write(new_content)

        # カウント
        count = ar.count_events(run_id)
        assert count == 3  # 空行は無視される

    def test_append_with_japanese_multibyte_characters(self, temp_vault):
        """日本語マルチバイト文字を含むイベントの追記とリプレイ

        UTF-8マルチバイト文字（日本語）を含むpayloadでも正しく
        追記・リプレイできることを確認。ファイル途中からの読み込みで
        文字境界の問題が発生しないことを検証する。
        """
        # Arrange: 日本語を含むイベントを準備
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-japanese"

        japanese_goals = [
            "テスト目標その1：日本語のテスト",
            "セキュリティパッチを適用します。一時的にサービスが停止する可能性があります。",
            "データベースのマイグレーションを実行します。既存データに影響がある可能性があります。",
        ]

        # Act: 複数の日本語イベントを追記
        for i, goal in enumerate(japanese_goals):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i:03d}",
                payload={"title": goal, "description": f"説明：{goal}"},
            )
            ar.append(event, run_id)

        # Assert: リプレイで正しく取得できる
        events = list(ar.replay(run_id))
        assert len(events) == 3

        for i, event in enumerate(events):
            assert event.payload["title"] == japanese_goals[i]
            assert event.payload["description"] == f"説明：{japanese_goals[i]}"

        # チェーンも正しく構築されている
        valid, error = ar.verify_chain(run_id)
        assert valid is True
        assert error is None

    def test_decode_utf8_safe_skips_continuation_bytes(self, temp_vault):
        """_decode_utf8_safeがUTF-8継続バイトを正しくスキップする

        ファイル途中から読み込んだ場合、先頭がUTF-8マルチバイト文字の
        途中（継続バイト 0x80-0xBF）になる可能性がある。
        このメソッドはそれらをスキップして安全にデコードする。
        """
        # Arrange: 継続バイトが先頭にあるバイト列を準備
        ar = AkashicRecord(temp_vault)

        # "日本語" のUTF-8表現: \xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e
        # 途中から読んだ場合（例：\xa5から）をシミュレート
        incomplete_start = b"\xa5\xe6\x9c\xac\xe8\xaa\x9e test"  # \xa5は継続バイト

        # Act: 安全にデコード
        result = ar._decode_utf8_safe(incomplete_start)

        # Assert: 継続バイトがスキップされ、残りがデコードされる
        assert "test" in result
        # 先頭の不完全な部分はスキップまたは置換される
        assert "\ufffd" not in result or result.endswith("test")

    def test_decode_utf8_safe_handles_valid_utf8(self, temp_vault):
        """_decode_utf8_safeが正常なUTF-8を正しくデコードする"""
        # Arrange
        ar = AkashicRecord(temp_vault)
        valid_utf8 = "日本語テスト".encode()

        # Act
        result = ar._decode_utf8_safe(valid_utf8)

        # Assert
        assert result == "日本語テスト"

    def test_decode_utf8_safe_handles_empty_bytes(self, temp_vault):
        """_decode_utf8_safeが空バイト列を処理できる"""
        # Arrange
        ar = AkashicRecord(temp_vault)

        # Act
        result = ar._decode_utf8_safe(b"")

        # Assert
        assert result == ""

    def test_append_creates_correct_prev_hash_chain_with_multibyte(self, temp_vault):
        """マルチバイト文字を含むファイルでprev_hashチェーンが正しく構築される

        ファイル末尾から読み込んでprev_hashを取得する際、UTF-8文字境界の
        問題が発生してもチェーンが正しく構築されることを検証する。
        """
        # Arrange: 大量の日本語イベントを追記
        ar = AkashicRecord(temp_vault)
        run_id = "test-run-chain-multibyte"

        # Act: 十分な量のイベントを追記してファイルサイズを大きくする
        for i in range(20):
            long_text = f"これは長い日本語テキストです。タスク番号{i}の説明文。" * 5
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i:03d}",
                payload={"title": f"タスク{i}", "description": long_text},
            )
            ar.append(event, run_id)

        # Assert: チェーンが正しく構築されている
        events = list(ar.replay(run_id))
        assert len(events) == 20

        # prev_hashチェーンを検証
        for i in range(1, len(events)):
            assert events[i].prev_hash == events[i - 1].hash

        # チェーン全体の検証
        valid, error = ar.verify_chain(run_id)
        assert valid is True
        assert error is None


class TestAkashicRecordMultibyteOperations:
    """マルチバイト文字を含む操作の包括的テスト

    UTF-8マルチバイト文字（日本語、中国語、絵文字など）を含むイベントが
    全てのAkashicRecord操作で正しく処理されることを検証する。
    """

    def test_replay_with_japanese_events(self, temp_vault):
        """replay()が日本語を含むイベントを正しくリプレイする"""
        # Arrange
        ar = AkashicRecord(temp_vault)
        run_id = "test-replay-japanese"
        japanese_texts = [
            "日本語テスト",
            "セキュリティパッチを適用します",
            "データベースマイグレーション実行中",
        ]

        for i, text in enumerate(japanese_texts):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": text},
            )
            ar.append(event, run_id)

        # Act
        events = list(ar.replay(run_id))

        # Assert
        assert len(events) == 3
        for i, event in enumerate(events):
            assert event.payload["title"] == japanese_texts[i]

    def test_get_last_event_with_japanese(self, temp_vault):
        """get_last_event()が日本語を含む最終イベントを正しく取得する"""
        # Arrange
        ar = AkashicRecord(temp_vault)
        run_id = "test-last-japanese"
        final_text = "最終タスク：本番環境へのデプロイ完了"

        for i in range(5):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"タスク{i}" if i < 4 else final_text},
            )
            ar.append(event, run_id)

        # Act
        last_event = ar.get_last_event(run_id)

        # Assert
        assert last_event is not None
        assert last_event.payload["title"] == final_text

    def test_export_run_with_japanese(self, temp_vault):
        """export_run()が日本語を含むイベントを正しくエクスポートする"""
        # Arrange
        ar = AkashicRecord(temp_vault)
        run_id = "test-export-japanese"
        japanese_titles = ["タスクA", "タスクB：データベース更新", "タスクC：完了"]

        for i, title in enumerate(japanese_titles):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": title},
            )
            ar.append(event, run_id)

        # Act
        output_path = temp_vault / "export_japanese.jsonl"
        count = ar.export_run(run_id, output_path)

        # Assert
        assert count == 3
        with open(output_path, encoding="utf-8") as f:
            exported_lines = [line.strip() for line in f if line.strip()]

        assert len(exported_lines) == 3
        for i, line in enumerate(exported_lines):
            event = parse_event(line)
            assert event.payload["title"] == japanese_titles[i]

    def test_count_events_with_japanese(self, temp_vault):
        """count_events()が日本語を含むイベントを正しくカウントする"""
        # Arrange
        ar = AkashicRecord(temp_vault)
        run_id = "test-count-japanese"

        for i in range(7):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"日本語タスク番号{i}"},
            )
            ar.append(event, run_id)

        # Act
        count = ar.count_events(run_id)

        # Assert
        assert count == 7

    def test_verify_chain_with_japanese(self, temp_vault):
        """verify_chain()が日本語を含むイベントチェーンを正しく検証する"""
        # Arrange
        ar = AkashicRecord(temp_vault)
        run_id = "test-verify-japanese"

        for i in range(10):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": f"日本語タスク{i}", "description": "詳細説明" * 10},
            )
            ar.append(event, run_id)

        # Act
        valid, error = ar.verify_chain(run_id)

        # Assert
        assert valid is True
        assert error is None

    def test_mixed_language_events(self, temp_vault):
        """複数言語（日本語、英語、中国語、絵文字）を含むイベントの処理"""
        # Arrange
        ar = AkashicRecord(temp_vault)
        run_id = "test-mixed-languages"
        mixed_texts = [
            "English text",
            "日本語テキスト",
            "中文文本",
            "Emoji 🚀🎉✨",
            "Mixed: Hello世界🌍",
        ]

        for i, text in enumerate(mixed_texts):
            event = TaskCreatedEvent(
                run_id=run_id,
                task_id=f"task-{i}",
                payload={"title": text},
            )
            ar.append(event, run_id)

        # Act
        events = list(ar.replay(run_id))
        last_event = ar.get_last_event(run_id)

        # Assert
        assert len(events) == 5
        for i, event in enumerate(events):
            assert event.payload["title"] == mixed_texts[i]
        assert last_event.payload["title"] == "Mixed: Hello世界🌍"

    def test_very_long_japanese_text(self, temp_vault):
        """非常に長い日本語テキストを含むイベントの処理

        チャンクサイズ(8192バイト)を超える長いテキストでも正しく処理されることを検証。
        """
        # Arrange
        ar = AkashicRecord(temp_vault)
        run_id = "test-long-japanese"

        # 約10KB以上の日本語テキストを生成
        long_text = "これは非常に長い日本語テキストです。" * 500

        event = TaskCreatedEvent(
            run_id=run_id,
            task_id="task-long",
            payload={"title": "長文タスク", "description": long_text},
        )
        ar.append(event, run_id)

        # 追加イベントを追記（prev_hash取得時にチャンク読み込みが発生）
        event2 = TaskCreatedEvent(
            run_id=run_id,
            task_id="task-after-long",
            payload={"title": "長文後のタスク"},
        )
        ar.append(event2, run_id)

        # Act
        events = list(ar.replay(run_id))

        # Assert
        assert len(events) == 2
        assert events[0].payload["description"] == long_text
        assert events[1].prev_hash == events[0].hash

    def test_decode_utf8_safe_with_various_continuation_bytes(self, temp_vault):
        """_decode_utf8_safeが様々なUTF-8継続バイトパターンを処理する"""
        ar = AkashicRecord(temp_vault)

        # テストケース: 様々な不完全なUTF-8シーケンス
        test_cases = [
            # (入力バイト列, 期待される部分文字列)
            (b"\x80\x81\x82hello", "hello"),  # 複数の継続バイト
            (b"\xbfworld", "world"),  # 継続バイトの最大値
            (b"normal text", "normal text"),  # 正常なASCII
            (b"\xe6\x97\xa5\xe6\x9c\xac", "日本"),  # 完全なUTF-8
        ]

        for input_bytes, expected_substring in test_cases:
            result = ar._decode_utf8_safe(input_bytes)
            assert expected_substring in result, f"Failed for {input_bytes!r}"


class TestHiveStore:
    """HiveStore のテスト

    Hive/Colony イベントは run_id を持たないため、
    Vault/hives/{hive_id}/events.jsonl に保存する。
    """

    def test_append_and_replay_hive_events(self, temp_vault):
        """Hiveイベントの追記とリプレイ

        Hiveイベントは hive_id をキーとして保存される。
        """
        # Arrange: HiveStore を作成
        from hiveforge.core.ar.hive_storage import HiveStore
        from hiveforge.core.events import ColonyCreatedEvent, HiveCreatedEvent

        store = HiveStore(temp_vault)
        hive_id = "test-hive-001"

        # Act: イベントを追記
        event1 = HiveCreatedEvent(
            actor="beekeeper",
            payload={"hive_id": hive_id, "name": "Test Hive"},
        )
        event2 = ColonyCreatedEvent(
            actor="queen_bee",
            payload={"colony_id": "colony-001", "hive_id": hive_id, "goal": "Test"},
        )

        store.append(event1, hive_id)
        store.append(event2, hive_id)

        # Assert: リプレイで取得できる
        events = list(store.replay(hive_id))
        assert len(events) == 2
        assert events[0].type.value == "hive.created"
        assert events[1].type.value == "colony.created"

    def test_event_chain_integrity(self, temp_vault):
        """イベントチェーンの整合性

        prev_hash が正しく設定される。
        """
        # Arrange
        from hiveforge.core.ar.hive_storage import HiveStore
        from hiveforge.core.events import HiveClosedEvent, HiveCreatedEvent

        store = HiveStore(temp_vault)
        hive_id = "test-hive-chain"

        # Act: 複数イベントを追記
        event1 = HiveCreatedEvent(payload={"hive_id": hive_id})
        stored1 = store.append(event1, hive_id)

        event2 = HiveClosedEvent(payload={"hive_id": hive_id})
        stored2 = store.append(event2, hive_id)

        # Assert: prev_hash が連鎖している
        assert stored1.prev_hash is None  # 最初のイベント
        assert stored2.prev_hash == stored1.hash  # 2番目は最初を参照

    def test_list_hives(self, temp_vault):
        """Hive一覧の取得

        複数のHiveを作成して一覧で取得できる。
        """
        # Arrange
        from hiveforge.core.ar.hive_storage import HiveStore
        from hiveforge.core.events import HiveCreatedEvent

        store = HiveStore(temp_vault)

        # Act: 複数Hiveを作成
        for i in range(3):
            hive_id = f"hive-{i:03d}"
            event = HiveCreatedEvent(payload={"hive_id": hive_id, "name": f"Hive {i}"})
            store.append(event, hive_id)

        # Assert: 一覧で取得できる
        hives = store.list_hives()
        assert len(hives) == 3
        assert "hive-000" in hives
        assert "hive-001" in hives
        assert "hive-002" in hives

    def test_list_hives_does_not_include_runs(self, temp_vault):
        """list_hivesはRun（通常のVaultディレクトリ）を含まない

        Vault/hives/ 配下のみを対象とする。
        """
        # Arrange: HiveStoreとAkashicRecordを両方使用
        from hiveforge.core.ar.hive_storage import HiveStore
        from hiveforge.core.ar.storage import AkashicRecord
        from hiveforge.core.events import HiveCreatedEvent, RunStartedEvent

        hive_store = HiveStore(temp_vault)
        ar = AkashicRecord(temp_vault)

        # Act: HiveとRunを両方作成
        hive_event = HiveCreatedEvent(payload={"hive_id": "hive-001"})
        hive_store.append(hive_event, "hive-001")

        run_event = RunStartedEvent(run_id="run-001", payload={"goal": "Test"})
        ar.append(run_event, "run-001")

        # Assert: list_hivesはHiveのみ、list_runsはRunのみ
        hives = hive_store.list_hives()
        runs = ar.list_runs()

        assert "hive-001" in hives
        assert "run-001" not in hives
        assert "run-001" in runs
        assert "hive-001" not in runs

    def test_storage_path_is_under_hives_directory(self, temp_vault):
        """Hiveイベントは Vault/hives/{hive_id}/ に保存される"""
        # Arrange
        from hiveforge.core.ar.hive_storage import HiveStore
        from hiveforge.core.events import HiveCreatedEvent

        store = HiveStore(temp_vault)
        hive_id = "test-hive-path"

        # Act: イベントを追記
        event = HiveCreatedEvent(payload={"hive_id": hive_id})
        store.append(event, hive_id)

        # Assert: ファイルパスを確認
        expected_path = temp_vault / "hives" / hive_id / "events.jsonl"
        assert expected_path.exists()

    def test_count_events(self, temp_vault):
        """イベント数のカウント"""
        # Arrange
        from hiveforge.core.ar.hive_storage import HiveStore
        from hiveforge.core.events import ColonyCreatedEvent

        store = HiveStore(temp_vault)
        hive_id = "test-hive-count"

        # Act: イベントを追記
        for i in range(5):
            event = ColonyCreatedEvent(payload={"colony_id": f"colony-{i}", "hive_id": hive_id})
            store.append(event, hive_id)

        # Assert
        count = store.count_events(hive_id)
        assert count == 5


# HiveStore追加テスト
from hiveforge.core.ar.hive_storage import HiveStore


class TestHiveStoreBasics:
    """HiveStoreの基本テスト"""

    def test_append_and_replay(self, tmp_path):
        """イベント追加とリプレイ"""
        from hiveforge.core.events import BaseEvent, EventType

        store = HiveStore(tmp_path)
        event = BaseEvent(type=EventType.HIVE_CREATED, data={"name": "test"})

        store.append(event, "hive-1")

        events = list(store.replay("hive-1"))
        assert len(events) == 1
        assert events[0].type == EventType.HIVE_CREATED

    def test_list_hives(self, tmp_path):
        """Hive一覧取得"""
        from hiveforge.core.events import BaseEvent, EventType

        store = HiveStore(tmp_path)
        store.append(
            BaseEvent(type=EventType.HIVE_CREATED, data={}), "hive-1"
        )
        store.append(
            BaseEvent(type=EventType.HIVE_CREATED, data={}), "hive-2"
        )

        hives = store.list_hives()
        assert "hive-1" in hives
        assert "hive-2" in hives

    def test_count_events(self, tmp_path):
        """イベント数カウント"""
        from hiveforge.core.events import BaseEvent, EventType

        store = HiveStore(tmp_path)
        store.append(
            BaseEvent(type=EventType.HIVE_CREATED, data={}), "hive-1"
        )
        store.append(
            BaseEvent(type=EventType.COLONY_CREATED, data={}), "hive-1"
        )

        count = store.count_events("hive-1")
        assert count == 2

    def test_count_events_nonexistent(self, tmp_path):
        """存在しないHiveのカウントは0"""
        store = HiveStore(tmp_path)
        count = store.count_events("nonexistent")
        assert count == 0

    def test_replay_nonexistent(self, tmp_path):
        """存在しないHiveのリプレイは空"""
        store = HiveStore(tmp_path)
        events = list(store.replay("nonexistent"))
        assert events == []

    def test_prev_hash_chain(self, tmp_path):
        """prev_hashチェーンが正しく形成される"""
        from hiveforge.core.events import BaseEvent, EventType

        store = HiveStore(tmp_path)
        event1 = store.append(
            BaseEvent(type=EventType.HIVE_CREATED, data={}), "hive-1"
        )
        event2 = store.append(
            BaseEvent(type=EventType.COLONY_CREATED, data={}), "hive-1"
        )

        # 2番目のイベントのprev_hashが1番目のhashを指す
        events = list(store.replay("hive-1"))
        assert events[0].prev_hash is None
        assert events[1].prev_hash == events[0].hash

    def test_list_hives_empty(self, tmp_path):
        """空のVaultでのHive一覧"""
        store = HiveStore(tmp_path)
        hives = store.list_hives()
        assert hives == []
