"""Poll GitHub issues and persist unseen issues as Markdown tasks."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import requests
from dotenv import load_dotenv

if __package__:
    from .attachments import Attachment, GitHubAttachmentStore, render_attachment_lines
else:
    from attachments import Attachment, GitHubAttachmentStore, render_attachment_lines

LOGGER = logging.getLogger("automation.issue_watcher")
Issue = Mapping[str, object]
Comment = Mapping[str, object]
IssueHandler = Callable[[Path, Issue], None]


class ConfigurationError(ValueError):
    """Raised when a required environment setting is invalid or missing."""


@dataclass(frozen=True)
class WatcherConfig:
    github_token: str
    github_owner: str
    github_repo: str
    github_api_url: str
    github_api_version: str
    tasks_dir: Path
    processing_tasks_dir: Path
    done_tasks_dir: Path
    logs_dir: Path
    state_dir: Path
    attachments_dir: Path
    attachment_max_bytes: int
    poll_interval_seconds: float
    request_timeout_seconds: float
    log_level: str

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, base_dir: Path | None = None
    ) -> "WatcherConfig":
        values = os.environ if env is None else env
        required = (
            "GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO", "GITHUB_API_URL",
            "GITHUB_API_VERSION",
            "TASKS_PENDING_DIR", "TASKS_PROCESSING_DIR", "TASKS_DONE_DIR",
            "CODEX_WORKER_LOGS_DIR", "AUTOMATION_STATE_DIR",
            "AUTOMATION_ATTACHMENTS_DIR", "AUTOMATION_ATTACHMENT_MAX_BYTES",
            "ISSUE_POLL_INTERVAL_SECONDS",
            "GITHUB_REQUEST_TIMEOUT_SECONDS", "ISSUE_WATCHER_LOG_LEVEL",
        )
        missing = [name for name in required if not values.get(name, "").strip()]
        if missing:
            raise ConfigurationError(f"Missing required .env settings: {', '.join(missing)}")

        poll_interval = cls._positive_float(
            values["ISSUE_POLL_INTERVAL_SECONDS"], "ISSUE_POLL_INTERVAL_SECONDS"
        )
        request_timeout = cls._positive_float(
            values["GITHUB_REQUEST_TIMEOUT_SECONDS"], "GITHUB_REQUEST_TIMEOUT_SECONDS"
        )
        attachment_max_bytes = cls._positive_int(
            values["AUTOMATION_ATTACHMENT_MAX_BYTES"],
            "AUTOMATION_ATTACHMENT_MAX_BYTES",
        )
        log_level = values["ISSUE_WATCHER_LOG_LEVEL"].upper()
        if log_level not in logging.getLevelNamesMapping():
            raise ConfigurationError(f"Invalid ISSUE_WATCHER_LOG_LEVEL: {log_level}")

        task_directories = [
            cls._resolve_path(values[name], base_dir)
            for name in ("TASKS_PENDING_DIR", "TASKS_PROCESSING_DIR", "TASKS_DONE_DIR")
        ]
        if len(set(task_directories)) != len(task_directories):
            raise ConfigurationError("Issue task directories must be different")

        return cls(
            github_token=values["GITHUB_TOKEN"],
            github_owner=values["GITHUB_OWNER"],
            github_repo=values["GITHUB_REPO"],
            github_api_url=values["GITHUB_API_URL"].rstrip("/"),
            github_api_version=values["GITHUB_API_VERSION"],
            tasks_dir=task_directories[0],
            processing_tasks_dir=task_directories[1],
            done_tasks_dir=task_directories[2],
            logs_dir=cls._resolve_path(values["CODEX_WORKER_LOGS_DIR"], base_dir),
            state_dir=cls._resolve_path(values["AUTOMATION_STATE_DIR"], base_dir),
            attachments_dir=cls._resolve_path(
                values["AUTOMATION_ATTACHMENTS_DIR"], base_dir
            ),
            attachment_max_bytes=attachment_max_bytes,
            poll_interval_seconds=poll_interval,
            request_timeout_seconds=request_timeout,
            log_level=log_level,
        )

    @staticmethod
    def _resolve_path(raw_path: str, base_dir: Path | None) -> Path:
        path = Path(raw_path).expanduser()
        if base_dir is not None and not path.is_absolute():
            path = base_dir / path
        return path

    @staticmethod
    def _positive_float(raw_value: str, setting_name: str) -> float:
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise ConfigurationError(f"{setting_name} must be a number") from exc
        if value <= 0:
            raise ConfigurationError(f"{setting_name} must be greater than zero")
        return value

    @staticmethod
    def _positive_int(raw_value: str, setting_name: str) -> int:
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ConfigurationError(f"{setting_name} must be an integer") from exc
        if value <= 0:
            raise ConfigurationError(f"{setting_name} must be greater than zero")
        return value


class GitHubIssueClient:
    """GitHub API adapter that owns HTTP and pagination concerns."""

    def __init__(self, config: WatcherConfig, session: requests.Session | None = None):
        self._config = config
        self._session = session or requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {config.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": config.github_api_version,
        })

    @property
    def session(self) -> requests.Session:
        return self._session

    def fetch_open_issues(self) -> list[Issue]:
        url: str | None = (
            f"{self._config.github_api_url}/repos/"
            f"{self._config.github_owner}/{self._config.github_repo}/issues"
        )
        params: dict[str, object] | None = {"state": "open", "per_page": 100}
        issues: list[Issue] = []
        while url:
            try:
                response = self._session.get(
                    url, params=params, timeout=self._config.request_timeout_seconds
                )
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                raise RuntimeError(f"GitHub API request failed: {exc}") from exc
            except ValueError as exc:
                raise RuntimeError("GitHub API returned invalid JSON") from exc
            if not isinstance(payload, list):
                raise RuntimeError("GitHub API returned an unexpected response")
            issues.extend(issue for issue in payload if "pull_request" not in issue)
            url = response.links.get("next", {}).get("url")
            params = None
        return issues

    def fetch_issue_comments(
        self, issue_number: int, since: str | None = None
    ) -> list[Comment]:
        if issue_number <= 0:
            raise ValueError("GitHub issue number must be greater than zero")
        url: str | None = (
            f"{self._config.github_api_url}/repos/"
            f"{self._config.github_owner}/{self._config.github_repo}/issues/"
            f"{issue_number}/comments"
        )
        params: dict[str, object] | None = {"per_page": 100}
        if since is not None:
            params["since"] = since
        comments: list[Comment] = []
        while url:
            try:
                response = self._session.get(
                    url,
                    params=params,
                    timeout=self._config.request_timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                raise RuntimeError(
                    "GitHub issue comments request failed "
                    f"| issue={issue_number} | error={type(exc).__name__}"
                ) from None
            except ValueError as exc:
                raise RuntimeError(
                    f"GitHub issue comments returned invalid JSON | issue={issue_number}"
                ) from exc
            if not isinstance(payload, list):
                raise RuntimeError(
                    f"GitHub issue comments returned an unexpected response | issue={issue_number}"
                )
            comments.extend(payload)
            url = response.links.get("next", {}).get("url")
            params = None
        return comments

    def create_issue_comment(self, issue_number: int, body: str) -> int:
        if issue_number <= 0:
            raise ValueError("GitHub issue number must be greater than zero")
        if not body.strip():
            raise ValueError("GitHub issue comment must not be empty")

        url = (
            f"{self._config.github_api_url}/repos/"
            f"{self._config.github_owner}/{self._config.github_repo}/issues/"
            f"{issue_number}/comments"
        )
        try:
            response = self._session.post(
                url,
                json={"body": body},
                timeout=self._config.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else "network"
            raise RuntimeError(
                "GitHub issue comment request failed "
                f"| issue={issue_number} | status={status} "
                f"| error={type(exc).__name__}"
            ) from None
        except ValueError as exc:
            raise RuntimeError(
                f"GitHub issue comment returned invalid JSON | issue={issue_number}"
            ) from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("id"), int):
            raise RuntimeError(
                f"GitHub issue comment returned an unexpected response | issue={issue_number}"
            )
        return payload["id"]


class MarkdownTaskStore:
    """Persist issues idempotently; an existing task is the processed marker."""

    def __init__(self, tasks_dir: Path, history_dirs: tuple[Path, ...] = ()):
        self.tasks_dir = tasks_dir
        self.history_dirs = history_dirs

    def save_if_new(
        self, issue: Issue, attachments: list[Attachment] | None = None
    ) -> Path | None:
        issue_number = int(issue["number"])
        path = self.tasks_dir / f"issue_{issue_number}.md"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        if self.is_processed(issue_number):
            return None
        try:
            with path.open("x", encoding="utf-8", newline="\n") as task_file:
                task_file.write(self._render(issue, attachments or []))
        except FileExistsError:
            return None
        return path

    def is_processed(self, issue_number: int) -> bool:
        filename = f"issue_{issue_number}.md"
        return (self.tasks_dir / filename).exists() or any(
            (directory / filename).exists() for directory in self.history_dirs
        )

    @staticmethod
    def _render(issue: Issue, attachments: list[Attachment]) -> str:
        content = (
            f"# Issue {issue['number']}\n\n"
            f"{issue.get('title', '')}\n\n"
            f"{issue.get('body') or ''}\n"
        )
        lines, _, _ = render_attachment_lines(attachments, 1)
        if lines:
            content += "\n[첨부 이미지]\n" + "\n".join(lines) + "\n"
        return content


class CommentCursorStore:
    """Persist per-Issue comment cursors with atomic file replacement."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir

    def read(self, issue_number: int) -> str | None:
        path = self._path(issue_number)
        if not path.exists():
            return None
        value = path.read_text(encoding="utf-8").strip()
        return value or None

    def write(self, issue_number: int, cursor: str) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(issue_number)
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(f"{cursor}\n", encoding="utf-8")
        temporary_path.replace(path)

    def _path(self, issue_number: int) -> Path:
        return self.state_dir / f"issue_{issue_number}.cursor"


class ConversationTaskStore:
    """Create one queue task for each user comment and render its conversation."""

    def __init__(
        self,
        pending_dir: Path,
        history_dirs: tuple[Path, ...],
        logs_dir: Path,
    ):
        self.pending_dir = pending_dir
        self.history_dirs = history_dirs
        self.logs_dir = logs_dir

    def published_comment_ids(self) -> set[int]:
        published: set[int] = set()
        if not self.logs_dir.exists():
            return published
        for marker_path in self.logs_dir.glob("*.commented"):
            try:
                comment_id = int(marker_path.read_text(encoding="utf-8").strip())
            except (OSError, UnicodeError, ValueError) as exc:
                raise RuntimeError(
                    f"Invalid published comment marker: {marker_path}"
                ) from exc
            if comment_id <= 0:
                raise RuntimeError(
                    f"Invalid published comment marker: {marker_path}"
                )
            published.add(comment_id)
        return published

    def is_user_comment(self, comment: Comment, published_ids: set[int]) -> bool:
        comment_id = self._positive_int(comment.get("id"), "comment id")
        if comment_id in published_ids:
            return False
        user = comment.get("user")
        return not (isinstance(user, Mapping) and user.get("type") == "Bot")

    def save_if_new(
        self,
        issue: Issue,
        comment: Comment,
        conversation: list[Comment],
        published_ids: set[int],
        issue_attachments: list[Attachment] | None = None,
        comment_attachments: Mapping[int, list[Attachment]] | None = None,
    ) -> Path | None:
        issue_number = self._positive_int(issue.get("number"), "issue number")
        comment_id = self._positive_int(comment.get("id"), "comment id")
        filename = f"issue_{issue_number}_comment_{comment_id}.md"
        if any((directory / filename).exists() for directory in self.history_dirs):
            return None
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        path = self.pending_dir / filename
        try:
            with path.open("x", encoding="utf-8", newline="\n") as task_file:
                task_file.write(
                    self._render(
                        issue,
                        comment_id,
                        conversation,
                        published_ids,
                        issue_attachments or [],
                        comment_attachments or {},
                    )
                )
        except FileExistsError:
            return None
        return path

    @classmethod
    def _render(
        cls,
        issue: Issue,
        current_comment_id: int,
        conversation: list[Comment],
        published_ids: set[int],
        issue_attachments: list[Attachment],
        comment_attachments: Mapping[int, list[Attachment]],
    ) -> str:
        issue_number = cls._positive_int(issue.get("number"), "issue number")
        title = str(issue.get("title") or "")
        body = str(issue.get("body") or "")
        issue_section = f"사용자:\n{title}\n\n{body}".rstrip()
        image_index = 1
        issue_lines, _, image_index = render_attachment_lines(
            issue_attachments, image_index
        )
        if issue_lines:
            issue_section += "\n\n[첨부 이미지]\n" + "\n".join(issue_lines)
        sections = [
            f"# Issue {issue_number}",
            f"# Comment {current_comment_id}",
            "[GitHub Issue 대화]",
            issue_section,
        ]
        ordered_comments = sorted(
            conversation,
            key=lambda item: (
                str(item.get("created_at") or ""),
                cls._positive_int(item.get("id"), "comment id"),
            ),
        )
        for item in ordered_comments:
            comment_id = cls._positive_int(item.get("id"), "comment id")
            user = item.get("user")
            if comment_id not in published_ids and (
                isinstance(user, Mapping) and user.get("type") == "Bot"
            ):
                continue
            role = "Codex" if comment_id in published_ids else "사용자"
            comment_body = str(item.get("body") or "")
            comment_section = f"{role}:\n{comment_body}".rstrip()
            attachment_lines, _, image_index = render_attachment_lines(
                comment_attachments.get(comment_id, []), image_index
            )
            if attachment_lines:
                comment_section += "\n\n[첨부 이미지]\n" + "\n".join(
                    attachment_lines
                )
            sections.append(comment_section)
        sections.extend(
            (
                "[현재 요청]",
                "위 대화의 맥락을 이어서 마지막 사용자 메시지를 처리한다.",
            )
        )
        return "\n\n".join(sections) + "\n"

    @staticmethod
    def _positive_int(value: object, label: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"Invalid {label}")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {label}") from exc
        if number <= 0:
            raise ValueError(f"Invalid {label}")
        return number


class IssueWatcher:
    """Coordinate polling and dispatch newly-created task files."""

    def __init__(self, config: WatcherConfig, client: GitHubIssueClient | None = None,
                 store: MarkdownTaskStore | None = None,
                 comment_store: ConversationTaskStore | None = None,
                 cursor_store: CommentCursorStore | None = None,
                 attachment_store: GitHubAttachmentStore | None = None,
                 on_new_issue: IssueHandler | None = None):
        self.config = config
        self.client = client or GitHubIssueClient(config)
        self.store = store or MarkdownTaskStore(
            config.tasks_dir,
            (config.processing_tasks_dir, config.done_tasks_dir),
        )
        self.comment_store = comment_store or ConversationTaskStore(
            config.tasks_dir,
            (config.processing_tasks_dir, config.done_tasks_dir),
            config.logs_dir,
        )
        self.cursor_store = cursor_store or CommentCursorStore(config.state_dir)
        self.attachment_store = attachment_store or GitHubAttachmentStore(
            config.attachments_dir,
            self.client.session,
            config.attachment_max_bytes,
            config.request_timeout_seconds,
        )
        self.on_new_issue = on_new_issue

    def run_once(self) -> list[Path]:
        issues = self.client.fetch_open_issues()
        LOGGER.info("GitHub check complete | open_issues=%d", len(issues))
        created: list[Path] = []
        for issue in issues:
            try:
                issue_number = ConversationTaskStore._positive_int(
                    issue.get("number"), "issue number"
                )
                if self.store.is_processed(issue_number):
                    path = None
                else:
                    issue_attachments = self.attachment_store.collect(
                        issue_number, "issue", str(issue.get("body") or "")
                    )
                    path = self.store.save_if_new(issue, issue_attachments)
            except (KeyError, TypeError, ValueError, OSError) as exc:
                LOGGER.error("Issue processing failed | issue=%s | error=%s", issue.get("number"), exc)
                continue
            if path is None:
                LOGGER.debug("Issue already processed | issue=%s", issue.get("number"))
            else:
                created.append(path)
                LOGGER.info("New task saved | issue=%s | file=%s", issue.get("number"), path)
                if self.on_new_issue is not None:
                    try:
                        self.on_new_issue(path, issue)
                    except Exception:
                        LOGGER.exception("New-issue handler failed | issue=%s", issue.get("number"))
            try:
                created.extend(self._save_new_comment_tasks(issue))
            except (KeyError, TypeError, ValueError, OSError) as exc:
                LOGGER.error(
                    "Issue comment processing failed | issue=%s | error=%s",
                    issue.get("number"),
                    exc,
                )
        LOGGER.info("Poll cycle finished | new_tasks=%d", len(created))
        return created

    def _save_new_comment_tasks(self, issue: Issue) -> list[Path]:
        issue_number = ConversationTaskStore._positive_int(
            issue.get("number"), "issue number"
        )
        cursor = self.cursor_store.read(issue_number)
        changed_comments = self.client.fetch_issue_comments(issue_number, since=cursor)
        if not changed_comments:
            return []

        published_ids = self.comment_store.published_comment_ids()
        candidates = [
            comment for comment in changed_comments
            if self.comment_store.is_user_comment(comment, published_ids)
        ]
        full_conversation = (
            changed_comments
            if cursor is None
            else self.client.fetch_issue_comments(issue_number)
        )
        ordered_conversation = sorted(
            full_conversation,
            key=self._comment_order_key,
        )
        issue_attachments = self.attachment_store.collect(
            issue_number,
            "issue",
            str(issue.get("body") or ""),
        )
        comment_attachments: dict[int, list[Attachment]] = {}
        for history_comment in ordered_conversation:
            history_comment_id = ConversationTaskStore._positive_int(
                history_comment.get("id"), "comment id"
            )
            if not self.comment_store.is_user_comment(
                history_comment, published_ids
            ):
                continue
            comment_attachments[history_comment_id] = self.attachment_store.collect(
                issue_number,
                f"comment_{history_comment_id}",
                str(history_comment.get("body") or ""),
            )
        created: list[Path] = []
        for comment in sorted(candidates, key=self._comment_order_key):
            current_key = self._comment_order_key(comment)
            conversation = [
                item for item in ordered_conversation
                if self._comment_order_key(item) <= current_key
            ]
            path = self.comment_store.save_if_new(
                issue,
                comment,
                conversation,
                published_ids,
                issue_attachments,
                comment_attachments,
            )
            if path is not None:
                created.append(path)
                LOGGER.info(
                    "New comment task saved | issue=%d | comment=%s | file=%s",
                    issue_number,
                    comment.get("id"),
                    path,
                )

        newest_cursor = max(self._comment_cursor(comment) for comment in changed_comments)
        self.cursor_store.write(issue_number, newest_cursor)
        return created

    @staticmethod
    def _comment_order_key(comment: Comment) -> tuple[str, int]:
        timestamp = str(comment.get("created_at") or "")
        if not timestamp:
            raise ValueError("GitHub comment is missing created_at")
        return (
            timestamp,
            ConversationTaskStore._positive_int(comment.get("id"), "comment id"),
        )

    @staticmethod
    def _comment_cursor(comment: Comment) -> str:
        cursor = str(comment.get("updated_at") or comment.get("created_at") or "")
        if not cursor:
            raise ValueError("GitHub comment is missing updated_at")
        return cursor

    def run_forever(self) -> None:
        LOGGER.info("Issue watcher started | repository=%s/%s | interval=%ss",
                    self.config.github_owner, self.config.github_repo,
                    self.config.poll_interval_seconds)
        while True:
            try:
                self.run_once()
            except RuntimeError as exc:
                LOGGER.error("Poll cycle failed | %s", exc)
            except Exception:
                LOGGER.exception("Unexpected poll cycle failure")
            time.sleep(self.config.poll_interval_seconds)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
    config = WatcherConfig.from_env(base_dir=project_root)
    configure_logging(config.log_level)
    IssueWatcher(config).run_forever()


if __name__ == "__main__":
    main()
