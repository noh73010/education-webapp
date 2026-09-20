import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from automation.attachments import Attachment
from automation.issue_watcher import GitHubIssueClient, IssueWatcher, MarkdownTaskStore, WatcherConfig


def make_config(tasks_dir: Path) -> WatcherConfig:
    return WatcherConfig(
        github_token="token", github_owner="owner", github_repo="repo",
        github_api_url="https://api.github.test", github_api_version="2022-11-28",
        tasks_dir=tasks_dir,
        processing_tasks_dir=tasks_dir.parent / "processing",
        done_tasks_dir=tasks_dir.parent / "done",
        logs_dir=tasks_dir.parent / "logs",
        state_dir=tasks_dir.parent / "state",
        attachments_dir=tasks_dir.parent / "attachments",
        attachment_max_bytes=10 * 1024 * 1024,
        poll_interval_seconds=30, request_timeout_seconds=15, log_level="INFO",
    )


def make_issue(number: int = 42) -> dict[str, object]:
    return {
        "number": number, "title": "Watcher refactor",
        "body": "Build a maintainable watcher.", "user": {"login": "octocat"},
        "created_at": "2026-08-10T00:00:00Z",
    }


def make_comment(
    comment_id: int,
    body: str = "이어서 수정해줘.",
    *,
    user_type: str = "User",
    created_at: str = "2026-08-10T01:00:00Z",
) -> dict[str, object]:
    return {
        "id": comment_id,
        "body": body,
        "created_at": created_at,
        "updated_at": created_at,
        "user": {"login": "octocat", "type": user_type},
    }


class MarkdownTaskStoreTests(unittest.TestCase):
    def test_saves_only_unseen_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MarkdownTaskStore(Path(directory))
            first_path = store.save_if_new(make_issue())
            second_path = store.save_if_new(make_issue())
            self.assertIsNotNone(first_path)
            self.assertIsNone(second_path)
            content = (Path(directory) / "issue_42.md").read_text(encoding="utf-8")
            self.assertEqual(
                "# Issue 42\n\n"
                "Watcher refactor\n\n"
                "Build a maintainable watcher.\n",
                content,
            )
            self.assertNotIn("Author", content)
            self.assertNotIn("Created at", content)

    def test_skips_issue_already_moved_to_done(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = root / "pending"
            done = root / "done"
            done.mkdir()
            (done / "issue_42.md").write_text("done", encoding="utf-8")
            store = MarkdownTaskStore(pending, (root / "processing", done))
            self.assertIsNone(store.save_if_new(make_issue()))
            self.assertFalse((pending / "issue_42.md").exists())


class GitHubIssueClientTests(unittest.TestCase):
    def test_fetches_issue_comments_with_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Mock(spec=requests.Session)
            session.headers = {}
            first = Mock()
            first.json.return_value = [make_comment(100)]
            first.links = {"next": {"url": "https://api.github.test/page/2"}}
            second = Mock()
            second.json.return_value = [make_comment(101)]
            second.links = {}
            session.get.side_effect = [first, second]
            client = GitHubIssueClient(make_config(Path(directory)), session=session)

            comments = client.fetch_issue_comments(42, since="2026-08-10T00:00:00Z")

            self.assertEqual([100, 101], [item["id"] for item in comments])
            self.assertEqual(
                {"per_page": 100, "since": "2026-08-10T00:00:00Z"},
                session.get.call_args_list[0].kwargs["params"],
            )
            self.assertIsNone(session.get.call_args_list[1].kwargs["params"])

    def test_filters_pull_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Mock(spec=requests.Session)
            session.headers = {}
            response = Mock()
            response.json.return_value = [make_issue(), {**make_issue(43), "pull_request": {}}]
            response.links = {}
            session.get.return_value = response
            client = GitHubIssueClient(make_config(Path(directory)), session=session)
            issues = client.fetch_open_issues()
            self.assertEqual([42], [issue["number"] for issue in issues])
            response.raise_for_status.assert_called_once_with()

    def test_wraps_request_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Mock(spec=requests.Session)
            session.headers = {}
            session.get.side_effect = requests.Timeout("timed out")
            client = GitHubIssueClient(make_config(Path(directory)), session=session)
            with self.assertRaisesRegex(RuntimeError, "GitHub API request failed"):
                client.fetch_open_issues()

    def test_creates_issue_comment_and_returns_comment_id(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Mock(spec=requests.Session)
            session.headers = {}
            response = Mock()
            response.json.return_value = {"id": 9876}
            session.post.return_value = response
            config = make_config(Path(directory))
            client = GitHubIssueClient(config, session=session)

            comment_id = client.create_issue_comment(42, "Codex response")

            self.assertEqual(9876, comment_id)
            session.post.assert_called_once_with(
                "https://api.github.test/repos/owner/repo/issues/42/comments",
                json={"body": "Codex response"},
                timeout=15,
            )
            response.raise_for_status.assert_called_once_with()

    def test_wraps_comment_http_errors_without_exposing_token(self):
        with tempfile.TemporaryDirectory() as directory:
            for status_code in (401, 403, 404, 422, 500):
                with self.subTest(status_code=status_code):
                    session = Mock(spec=requests.Session)
                    session.headers = {}
                    response = Mock(status_code=status_code)
                    response.raise_for_status.side_effect = requests.HTTPError(
                        "forbidden token", response=response
                    )
                    session.post.return_value = response
                    client = GitHubIssueClient(
                        make_config(Path(directory)), session=session
                    )

                    with self.assertRaises(RuntimeError) as raised:
                        client.create_issue_comment(42, "Codex response")

                    message = str(raised.exception)
                    self.assertIn(f"status={status_code}", message)
                    self.assertNotIn("token", message)
                    self.assertIsNone(raised.exception.__cause__)

    def test_wraps_comment_network_error_without_exposing_token(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Mock(spec=requests.Session)
            session.headers = {}
            session.post.side_effect = requests.Timeout("secret-token")
            client = GitHubIssueClient(make_config(Path(directory)), session=session)

            with self.assertRaises(RuntimeError) as raised:
                client.create_issue_comment(42, "Codex response")

            message = str(raised.exception)
            self.assertIn("status=network", message)
            self.assertIn("Timeout", message)
            self.assertNotIn("secret-token", message)
            self.assertIsNone(raised.exception.__cause__)


class IssueWatcherTests(unittest.TestCase):
    def test_dispatches_only_new_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            client = Mock()
            client.fetch_open_issues.return_value = [make_issue()]
            client.fetch_issue_comments.return_value = []
            handler = Mock()
            watcher = IssueWatcher(config, client=client, on_new_issue=handler)
            watcher.run_once()
            watcher.run_once()
            handler.assert_called_once()
            self.assertEqual(Path(directory) / "issue_42.md", handler.call_args.args[0])

    def test_creates_comment_task_with_conversation_and_korean_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root / "pending")
            config.done_tasks_dir.mkdir(parents=True)
            (config.done_tasks_dir / "issue_42.md").write_text("done", encoding="utf-8")
            config.logs_dir.mkdir(parents=True)
            (config.logs_dir / "issue_42.commented").write_text(
                "500\n", encoding="utf-8"
            )
            codex_comment = make_comment(500, "이전 Codex 답변")
            comment = make_comment(
                123,
                "한글 요청을 이어서 처리해줘.",
                created_at="2026-08-10T02:00:00Z",
            )
            client = Mock()
            client.fetch_open_issues.return_value = [make_issue()]
            client.fetch_issue_comments.return_value = [codex_comment, comment]

            created = IssueWatcher(config, client=client).run_once()

            task = config.tasks_dir / "issue_42_comment_123.md"
            self.assertEqual([task], created)
            content = task.read_text(encoding="utf-8")
            self.assertIn("# Issue 42", content)
            self.assertIn("# Comment 123", content)
            self.assertIn("Watcher refactor", content)
            self.assertIn("Codex:\n이전 Codex 답변", content)
            self.assertIn("사용자:\n한글 요청을 이어서 처리해줘.", content)
            self.assertLess(content.index("이전 Codex 답변"), content.index("한글 요청"))
            self.assertTrue((config.state_dir / "issue_42.cursor").exists())

    def test_comment_task_is_deduplicated_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root / "pending")
            config.done_tasks_dir.mkdir(parents=True)
            (config.done_tasks_dir / "issue_42.md").write_text("done", encoding="utf-8")
            comment = make_comment(123)
            client = Mock()
            client.fetch_open_issues.return_value = [make_issue()]
            client.fetch_issue_comments.return_value = [comment]

            self.assertEqual(1, len(IssueWatcher(config, client=client).run_once()))
            self.assertEqual([], IssueWatcher(config, client=client).run_once())
            self.assertEqual(
                1,
                len(list(config.tasks_dir.glob("issue_42_comment_123.md"))),
            )

    def test_skips_codex_comment_recorded_in_marker_and_external_bot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root / "pending")
            config.done_tasks_dir.mkdir(parents=True)
            (config.done_tasks_dir / "issue_42.md").write_text("done", encoding="utf-8")
            config.logs_dir.mkdir(parents=True)
            (config.logs_dir / "issue_42.commented").write_text("500\n", encoding="utf-8")
            client = Mock()
            client.fetch_open_issues.return_value = [make_issue()]
            client.fetch_issue_comments.return_value = [
                make_comment(500, "Codex answer"),
                make_comment(501, "bot answer", user_type="Bot"),
            ]

            self.assertEqual([], IssueWatcher(config, client=client).run_once())
            self.assertEqual([], list(config.tasks_dir.glob("*_comment_*.md")))

    def test_multiple_comments_create_independent_tasks_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root / "pending")
            config.done_tasks_dir.mkdir(parents=True)
            (config.done_tasks_dir / "issue_42.md").write_text("done", encoding="utf-8")
            first = make_comment(123, "첫 요청")
            second = make_comment(
                124,
                "두 번째 요청",
                created_at="2026-08-10T02:00:00Z",
            )
            client = Mock()
            client.fetch_open_issues.return_value = [make_issue()]
            client.fetch_issue_comments.return_value = [first, second]

            created = IssueWatcher(config, client=client).run_once()

            self.assertEqual(2, len(created))
            first_text = created[0].read_text(encoding="utf-8")
            second_text = created[1].read_text(encoding="utf-8")
            self.assertNotIn("두 번째 요청", first_text)
            self.assertIn("첫 요청", second_text)
            self.assertIn("두 번째 요청", second_text)

    def test_comment_task_keeps_issue_and_previous_comment_images_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root / "pending")
            config.done_tasks_dir.mkdir(parents=True)
            (config.done_tasks_dir / "issue_42.md").write_text("done", encoding="utf-8")
            issue_image = root / "attachments" / "issue.png"
            previous_image = root / "attachments" / "previous.png"
            issue_image.parent.mkdir(parents=True)
            issue_image.write_bytes(b"image")
            previous_image.write_bytes(b"image")
            first = make_comment(123, "![이전](https://github.com/user-attachments/assets/a)")
            second = make_comment(
                124,
                "아까 이미지 기준으로 수정해줘.",
                created_at="2026-08-10T02:00:00Z",
            )
            client = Mock()
            client.fetch_open_issues.return_value = [
                {**make_issue(), "body": "![최초](https://github.com/user-attachments/assets/b)"}
            ]
            client.fetch_issue_comments.return_value = [first, second]
            attachment_store = Mock()

            def collect(_issue_number, source, _markdown):
                if source == "issue":
                    return [Attachment(issue_image.resolve())]
                if source == "comment_123":
                    return [Attachment(previous_image.resolve())]
                return []

            attachment_store.collect.side_effect = collect

            created = IssueWatcher(
                config,
                client=client,
                attachment_store=attachment_store,
            ).run_once()

            current_task = next(path for path in created if path.name.endswith("_124.md"))
            content = current_task.read_text(encoding="utf-8")
            self.assertIn(f"- 이미지 1: {issue_image.resolve()}", content)
            self.assertIn(f"- 이미지 2: {previous_image.resolve()}", content)
            self.assertEqual(2, content.count("[첨부 이미지]"))
            self.assertNotIn("첨부 이미지:", content)
            self.assertLess(content.index("이미지 1"), content.index("이미지 2"))
            self.assertIn("아까 이미지 기준으로 수정해줘.", content)


if __name__ == "__main__":
    unittest.main()
