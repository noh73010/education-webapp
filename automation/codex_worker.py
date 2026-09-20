"""Consume Markdown tasks from a filesystem-backed task queue."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from dotenv import load_dotenv

if __package__:
    from .issue_watcher import GitHubIssueClient
else:
    from issue_watcher import GitHubIssueClient


LOGGER = logging.getLogger("automation.codex_worker")
PROMPT_PREAMBLE = (
    "\ub108\ub294 \uc774 \ud504\ub85c\uc81d\ud2b8\ub97c \ud568\uaed8 \uac1c\ubc1c\ud558\ub294 \uac1c\ubc1c \ud30c\ud2b8\ub108\ub2e4.\n"
    "PROJECT_CONTEXT.md\ub97c \uba3c\uc800 \uc77d\uace0 \ud504\ub85c\uc81d\ud2b8\ub97c \uc774\ud574\ud55c\ub2e4.\n"
    "AGENTS.md\uac00 \uc788\uc73c\uba74 \uba3c\uc800 \uc77d\uace0 \uadf8 \uaddc\uce59\uc744 \ub530\ub978\ub2e4.\n"
    "\uc544\ub798 GitHub Issue\ub294 \uc0ac\uc6a9\uc790\uac00 \ubcf4\ub0b8 \uc790\uc5f0\uc5b4 \uba54\uc2dc\uc9c0\ub2e4. "
    "\uc815\ud574\uc9c4 \ud15c\ud50c\ub9bf\uc774\ub098 \ud56d\ubaa9\uc744 \uac00\uc815\ud558\uc9c0 \ub9d0\uace0, \uc81c\ubaa9\uacfc \ubcf8\ubb38\uc758 \ub9e5\ub77d\uc744 "
    "\ud568\uaed8 \uc774\ud574\ud574 \uc758\ub3c4\uc5d0 \ub9de\uac8c \ub300\ud654\ud558\uac70\ub098 \uc791\uc5c5\ud55c\ub2e4.\n"
    "\uc815\ubcf4\uac00 \ucda9\ubd84\ud558\uba74 \ubc14\ub85c \uc9c4\ud589\ud558\uace0, \ud575\uc2ec \uc815\ubcf4\uac00 \ubd80\uc871\ud558\uba74 \uc9e7\uac8c \uc9c8\ubb38\ud55c\ub2e4.\n"
    "첨부 이미지가 있으면 이미지 번호와 대화 속 연결 관계를 함께 이해한다. "
    "다운로드 실패로 표시된 이미지는 본 척하지 말고 필요한 경우 사용자에게 알린다. "
    "응답에는 첨부 URL이나 PC의 로컬 절대경로를 불필요하게 반복하지 않고 "
    "'이미지 1' 같은 논리적 이름을 사용한다.\n"
    "질문·기획·설계·원인 분석 요청은 사용자가 구현을 명시하지 않았다면 코드를 변경하지 않는다. "
    "구현 요청만 현재 구조를 분석한 뒤 수정한다.\n"
    "이미지, traceback, 로그, 파일, 설정, DB 상태처럼 작업에 필수인 증거는 실제로 확인한다. "
    "필수 증거가 없거나 이미지 다운로드가 실패했고 이미지가 요청의 기준이라면 추측해서 코드를 수정하지 말고, "
    "확인하지 못한 내용과 필요한 자료를 명확히 보고한다. 이미지와 무관한 독립적인 텍스트 요청은 계속 처리할 수 있다.\n"
    "코드를 변경했다면 변경 범위에 맞는 검증 명령을 실제로 실행한다. Django 변경은 가능한 경우 manage.py check와 관련 테스트, "
    "Python 변경은 필요한 py_compile, automation 변경은 automation 테스트를 선택한다. "
    "프로젝트 Python은 Windows에서 `.venv\\Scripts\\python.exe`, Linux/macOS에서 `.venv/bin/python`을 최우선으로 사용한다. "
    "Django 변경은 가능한 경우 `.venv\\Scripts\\python.exe manage.py check`와 관련 테스트를 실행하고, "
    "automation 변경은 `.venv\\Scripts\\python.exe -m unittest discover -s automation\\tests -v`를 실행한다. "
    ".venv 실행 파일이 없을 때만 Worker preflight에서 확인된 Python fallback을 사용한다. "
    "검증 명령이 실패하면 validation=failed로 보고한다. 모든 작업에 같은 명령을 기계적으로 적용하지 않는다. "
    "실행하지 않은 검증을 통과했다고 말하지 않고 실패를 완료로 표현하지 않는다.\n"
    "최종 응답 전에 요구사항, 증거, 회귀 위험, 하드코딩, 불필요한 변경, 실제 테스트 결과, PROJECT_CONTEXT.md 갱신 필요성을 스스로 검토한다. "
    "응답 마지막 줄에는 반드시 다음 형식을 쓴다: "
    "AUTOMATION_RESULT: code_changed=yes|no; validation=passed|failed|not_run|not_required\n"
    "\uae30\uc874 \ud504\ub85c\uc81d\ud2b8 \uad6c\uc870\ub97c \uc720\uc9c0\ud558\uace0 \ud558\ub4dc\ucf54\ub529\uc744 \ud53c\ud558\uba70, "
    "\uc791\uc5c5 \ud6c4 \ubcc0\uacbd\uacfc \uac80\uc99d \uacb0\uacfc\ub97c \uc694\uc57d\ud55c\ub2e4."
)


class WorkerConfigurationError(ValueError):
    """Raised when a required worker setting is missing or invalid."""


class CodexCliExecutionError(RuntimeError):
    """Raised when Codex CLI cannot start or returns a non-zero exit code."""


@dataclass(frozen=True)
class WorkerPreflightResult:
    python_command: tuple[str, ...]
    python_source: str
    python_version: str
    django_version: str
    codex_executable: str
    codex_version: str


def _venv_python(project_root: Path) -> Path | None:
    candidates = (
        project_root / ".venv" / "Scripts" / "python.exe",
        project_root / ".venv" / "bin" / "python",
    )
    return next((path for path in candidates if path.is_file()), None)


def _worker_subprocess_environment(project_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    candidate_directories: list[Path] = []
    venv_python = _venv_python(project_root)
    if venv_python is not None:
        candidate_directories.append(venv_python.parent)
        environment["VIRTUAL_ENV"] = str(venv_python.parent.parent)
    candidate_directories.append(Path(sys.executable).resolve().parent)
    launcher = shutil.which("py", path=environment.get("PATH"))
    if launcher:
        candidate_directories.append(Path(launcher).resolve().parent)
    if os.name == "nt" and environment.get("LOCALAPPDATA"):
        candidate_directories.append(
            Path(environment["LOCALAPPDATA"])
            / "Programs"
            / "Python"
            / "Launcher"
        )
    existing_path = [
        item for item in environment.get("PATH", "").split(os.pathsep) if item
    ]
    priority: list[str] = []
    priority_keys: set[str] = set()
    for path in candidate_directories:
        value = str(path)
        key = value.lower()
        if path.is_dir() and key not in priority_keys:
            priority.append(value)
            priority_keys.add(key)
    remaining = [item for item in existing_path if item.lower() not in priority_keys]
    environment["PATH"] = os.pathsep.join([*priority, *remaining])
    return environment


@dataclass(frozen=True)
class WorkerConfig:
    pending_dir: Path
    processing_dir: Path
    done_dir: Path
    project_root: Path
    logs_dir: Path
    attachments_dir: Path
    codex_command: str
    task_timeout_seconds: float
    poll_interval_seconds: float
    log_level: str
    github_token: str
    github_owner: str
    github_repo: str
    github_api_url: str
    github_api_version: str
    request_timeout_seconds: float
    reasoning_effort: str

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, base_dir: Path | None = None
    ) -> "WorkerConfig":
        values = os.environ if env is None else env
        required = (
            "TASKS_PENDING_DIR",
            "TASKS_PROCESSING_DIR",
            "TASKS_DONE_DIR",
            "CODEX_WORKER_LOGS_DIR",
            "AUTOMATION_ATTACHMENTS_DIR",
            "CODEX_CLI_COMMAND",
            "CODEX_TASK_TIMEOUT_SECONDS",
            "CODEX_WORKER_POLL_INTERVAL_SECONDS",
            "CODEX_WORKER_LOG_LEVEL",
            "GITHUB_TOKEN",
            "GITHUB_OWNER",
            "GITHUB_REPO",
            "GITHUB_API_URL",
            "GITHUB_API_VERSION",
            "GITHUB_REQUEST_TIMEOUT_SECONDS",
            "CODEX_REASONING_EFFORT",
        )
        missing = [name for name in required if not values.get(name, "").strip()]
        if missing:
            raise WorkerConfigurationError(
                f"Missing required .env settings: {', '.join(missing)}"
            )

        directories = [
            cls._resolve_path(values[name], base_dir)
            for name in ("TASKS_PENDING_DIR", "TASKS_PROCESSING_DIR", "TASKS_DONE_DIR")
        ]
        if len(set(directories)) != len(directories):
            raise WorkerConfigurationError("Worker task directories must be different")
        if base_dir is None:
            raise WorkerConfigurationError("Worker project root is required")

        poll_interval = cls._positive_float(
            values["CODEX_WORKER_POLL_INTERVAL_SECONDS"],
            "CODEX_WORKER_POLL_INTERVAL_SECONDS",
        )
        task_timeout = cls._positive_float(
            values["CODEX_TASK_TIMEOUT_SECONDS"],
            "CODEX_TASK_TIMEOUT_SECONDS",
        )
        request_timeout = cls._positive_float(
            values["GITHUB_REQUEST_TIMEOUT_SECONDS"],
            "GITHUB_REQUEST_TIMEOUT_SECONDS",
        )

        log_level = values["CODEX_WORKER_LOG_LEVEL"].upper()
        if log_level not in logging.getLevelNamesMapping():
            raise WorkerConfigurationError(
                f"Invalid CODEX_WORKER_LOG_LEVEL: {log_level}"
            )
        reasoning_effort = values["CODEX_REASONING_EFFORT"].lower()
        if reasoning_effort != "high":
            raise WorkerConfigurationError(
                "CODEX_REASONING_EFFORT must be high for automation"
            )

        return cls(
            pending_dir=directories[0],
            processing_dir=directories[1],
            done_dir=directories[2],
            project_root=base_dir.resolve(),
            logs_dir=cls._resolve_path(values["CODEX_WORKER_LOGS_DIR"], base_dir),
            attachments_dir=cls._resolve_path(
                values["AUTOMATION_ATTACHMENTS_DIR"], base_dir
            ),
            codex_command=values["CODEX_CLI_COMMAND"],
            task_timeout_seconds=task_timeout,
            poll_interval_seconds=poll_interval,
            log_level=log_level,
            github_token=values["GITHUB_TOKEN"],
            github_owner=values["GITHUB_OWNER"],
            github_repo=values["GITHUB_REPO"],
            github_api_url=values["GITHUB_API_URL"].rstrip("/"),
            github_api_version=values["GITHUB_API_VERSION"],
            request_timeout_seconds=request_timeout,
            reasoning_effort=reasoning_effort,
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
            raise WorkerConfigurationError(f"{setting_name} must be a number") from exc
        if value <= 0:
            raise WorkerConfigurationError(
                f"{setting_name} must be greater than zero"
            )
        return value


class TaskProcessor(Protocol):
    """Extension point for the future Codex-backed task processor."""

    def process(self, task_path: Path) -> None:
        """Process one task or raise an exception when processing fails."""


class IssueCommentPublisher(Protocol):
    """Publish one user-facing response to its source GitHub Issue."""

    def create_issue_comment(self, issue_number: int, body: str) -> int:
        """Return the created GitHub comment ID or raise on failure."""


class RealCodexProcessor:
    """Run Markdown tasks through the official Codex CLI."""

    def __init__(
        self,
        project_root: Path,
        logs_dir: Path,
        codex_command: str,
        timeout_seconds: float,
        attachments_dir: Path | None = None,
        reasoning_effort: str = "high",
    ):
        self.project_root = project_root
        self.logs_dir = logs_dir
        self.codex_command = codex_command
        self.timeout_seconds = timeout_seconds
        self.attachments_dir = attachments_dir or project_root / "automation" / "attachments"
        self.reasoning_effort = reasoning_effort

    def process(self, task_path: Path) -> None:
        issue_markdown = task_path.read_text(encoding="utf-8")
        task_prompt = self._build_prompt(issue_markdown)
        prompt_path, stdout_path, stderr_path, response_path = self._log_paths(
            task_path
        )
        prompt_path.write_text(task_prompt, encoding="utf-8")
        response_path.unlink(missing_ok=True)
        image_paths = self._attachment_paths(issue_markdown)
        command = self._build_command(response_path, image_paths)

        LOGGER.info("Codex CLI started | task=%s | prompt=%s", task_path, prompt_path)
        process_env, python_environment = self._subprocess_environment()
        LOGGER.info(
            "Codex execution | cwd=project_root | mode=exec | sandbox=workspace-write "
            "| reasoning=%s | images=%d | config=user-default | profile=user-default "
            "| python_environment=%s",
            self.reasoning_effort,
            len(image_paths),
            python_environment,
        )
        try:
            result = subprocess.run(
                command,
                cwd=self.project_root,
                input=task_prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.timeout_seconds,
                shell=False,
                env=process_env,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._as_text(exc.stdout)
            stderr = self._as_text(exc.stderr)
            timeout_message = (
                f"Codex CLI timed out after {self.timeout_seconds} seconds"
            )
            stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message
            self._write_logs(stdout_path, stderr_path, stdout, stderr)
            raise CodexCliExecutionError(
                f"{timeout_message}; stdout={stdout_path}; stderr={stderr_path}"
            ) from exc
        except OSError as exc:
            self._write_logs(stdout_path, stderr_path, "", str(exc))
            raise CodexCliExecutionError(
                f"Codex CLI could not start; see {stderr_path}"
            ) from exc

        self._write_logs(stdout_path, stderr_path, result.stdout, result.stderr)
        LOGGER.info(
            "Codex CLI finished | task=%s | exit_code=%d",
            task_path,
            result.returncode,
        )
        if result.returncode != 0:
            raise CodexCliExecutionError(
                "Codex CLI failed "
                f"with exit code {result.returncode}; "
                f"stdout={stdout_path}; stderr={stderr_path}"
            )
        self._validate_response(response_path)
        self._write_quality_result(task_path, response_path)

    def _build_command(
        self, response_path: Path, image_paths: list[Path] | None = None
    ) -> list[str]:
        command = [
            self.codex_command,
            "exec",
            "--sandbox",
            "workspace-write",
            "--config",
            f'model_reasoning_effort="{self.reasoning_effort}"',
        ]
        if image_paths:
            command.extend(["--image", *(str(path) for path in image_paths)])
        command.extend([
            "--output-last-message",
            str(response_path),
            "-",
        ])
        return command

    def _attachment_paths(self, issue_markdown: str) -> list[Path]:
        paths: list[Path] = []
        root = self.attachments_dir.resolve()
        lines = issue_markdown.splitlines()
        metadata_headers = {"[첨부 이미지]", "첨부 이미지:"}
        for index, line in enumerate(lines):
            if line.strip() not in metadata_headers:
                continue
            for metadata_line in lines[index + 1:]:
                match = re.fullmatch(
                    r"- 이미지 [1-9]\d*: (.+)", metadata_line.strip()
                )
                if match is None:
                    break
                if match.group(1).startswith("다운로드 실패"):
                    continue
                path = Path(match.group(1))
                try:
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(root)
                except (OSError, ValueError) as exc:
                    raise CodexCliExecutionError(
                        f"Invalid task image attachment path: {path.name}"
                    ) from exc
                if resolved.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                    raise CodexCliExecutionError(
                        f"Unsupported task image attachment: {resolved.name}"
                    )
                if resolved not in paths:
                    paths.append(resolved)
        return paths

    def _subprocess_environment(self) -> tuple[dict[str, str], str]:
        environment = _worker_subprocess_environment(self.project_root)
        venv_python = _venv_python(self.project_root)
        if venv_python is not None:
            return environment, str(venv_python)
        launcher = shutil.which("py", path=environment.get("PATH"))
        return environment, launcher or "unavailable"

    def _write_quality_result(self, task_path: Path, response_path: Path) -> None:
        response = response_path.read_text(encoding="utf-8")
        matches = re.findall(
            r"^AUTOMATION_RESULT:\s*code_changed=(yes|no);\s*"
            r"validation=(passed|failed|not_run|not_required)\s*$",
            response,
            flags=re.MULTILINE,
        )
        result = (
            {"code_changed": matches[-1][0], "validation": matches[-1][1]}
            if matches
            else {"code_changed": "unknown", "validation": "unknown"}
        )
        result_path = self.logs_dir / f"{task_path.stem}.quality.json"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _build_prompt(issue_markdown: str) -> str:
        return f"{PROMPT_PREAMBLE}\n\n{issue_markdown}"

    def _log_paths(self, task_path: Path) -> tuple[Path, Path, Path, Path]:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        return (
            self.logs_dir / f"{task_path.stem}.prompt.md",
            self.logs_dir / f"{task_path.stem}.stdout.log",
            self.logs_dir / f"{task_path.stem}.stderr.log",
            self.logs_dir / f"{task_path.stem}.response.md",
        )

    @staticmethod
    def _validate_response(response_path: Path) -> None:
        try:
            response = response_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise CodexCliExecutionError(
                f"Codex CLI did not create a readable response; response={response_path}"
            ) from exc
        if not response.strip():
            raise CodexCliExecutionError(
                f"Codex CLI created an empty response; response={response_path}"
            )

    @staticmethod
    def _write_logs(
        stdout_path: Path,
        stderr_path: Path,
        stdout: str,
        stderr: str,
    ) -> None:
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")

    @staticmethod
    def _as_text(output: str | bytes | None) -> str:
        if output is None:
            return ""
        if isinstance(output, bytes):
            return output.decode("utf-8", errors="replace")
        return output


class TaskQueue:
    """Manage pending -> processing -> done filesystem transitions."""

    def __init__(self, config: WorkerConfig):
        self.config = config
        for directory in (
            config.pending_dir,
            config.processing_dir,
            config.done_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def pending_tasks(self) -> list[Path]:
        return sorted(
            path
            for path in self.config.pending_dir.glob("*.md")
            if path.is_file()
        )

    def claim(self, pending_path: Path) -> Path:
        self._ensure_parent(pending_path, self.config.pending_dir)
        processing_path = self.config.processing_dir / pending_path.name
        if processing_path.exists():
            raise FileExistsError(f"Processing task already exists: {processing_path}")
        pending_path.rename(processing_path)
        return processing_path

    def complete(self, processing_path: Path) -> Path:
        self._ensure_parent(processing_path, self.config.processing_dir)
        done_path = self.config.done_dir / processing_path.name
        if done_path.exists():
            raise FileExistsError(f"Completed task already exists: {done_path}")
        processing_path.rename(done_path)
        return done_path

    @staticmethod
    def _ensure_parent(path: Path, expected_parent: Path) -> None:
        if path.parent.resolve() != expected_parent.resolve():
            raise ValueError(f"Task is outside the expected queue directory: {path}")


class CodexWorker:
    """Poll a task queue and delegate each claimed task to a processor."""

    def __init__(
        self,
        config: WorkerConfig,
        queue: TaskQueue | None = None,
        processor: TaskProcessor | None = None,
        comment_publisher: IssueCommentPublisher | None = None,
    ):
        self.config = config
        self.queue = queue or TaskQueue(config)
        self.processor = processor or RealCodexProcessor(
            project_root=config.project_root,
            logs_dir=config.logs_dir,
            codex_command=config.codex_command,
            timeout_seconds=config.task_timeout_seconds,
            attachments_dir=config.attachments_dir,
            reasoning_effort=config.reasoning_effort,
        )
        self.comment_publisher = comment_publisher or GitHubIssueClient(config)
        self._preflight_result: WorkerPreflightResult | None = None

    def preflight(self) -> WorkerPreflightResult:
        if self._preflight_result is not None:
            return self._preflight_result
        project_root = self.config.project_root.resolve()
        if not project_root.is_dir():
            raise WorkerConfigurationError(
                f"Worker project root does not exist: {project_root}"
            )

        environment = _worker_subprocess_environment(project_root)
        venv_python = _venv_python(project_root)
        if venv_python is not None:
            python_command = (str(venv_python.resolve()),)
            python_source = "project-.venv"
        else:
            launcher = shutil.which("py", path=environment.get("PATH"))
            if launcher:
                python_command = (launcher, "-3")
                python_source = "py-3-fallback"
            else:
                python = shutil.which("python3", path=environment.get("PATH"))
                if python is None:
                    python = shutil.which("python", path=environment.get("PATH"))
                if python is None:
                    raise WorkerConfigurationError(
                        "Worker preflight found neither project .venv Python "
                        "nor a Python fallback"
                    )
                python_command = (python,)
                python_source = "python-fallback"

        python_version = self._preflight_command(
            [*python_command, "--version"], environment, "Python version"
        )
        django_version = self._preflight_command(
            [
                *python_command,
                "-c",
                "import django; print(django.get_version())",
            ],
            environment,
            "Django import",
        )
        codex_executable = shutil.which(
            self.config.codex_command, path=environment.get("PATH")
        )
        if codex_executable is None:
            explicit_codex = Path(self.config.codex_command)
            if explicit_codex.is_file():
                codex_executable = str(explicit_codex.resolve())
            else:
                raise WorkerConfigurationError(
                    f"Worker preflight could not find Codex CLI: "
                    f"{self.config.codex_command}"
                )
        codex_version = self._preflight_command(
            [codex_executable, "--version"], environment, "Codex CLI"
        )
        self._preflight_result = WorkerPreflightResult(
            python_command=python_command,
            python_source=python_source,
            python_version=python_version,
            django_version=django_version,
            codex_executable=codex_executable,
            codex_version=codex_version,
        )
        LOGGER.info(
            "Worker preflight passed | project_root=%s | python_source=%s "
            "| python=%s | python_version=%s | django=%s | codex=%s "
            "| codex_version=%s",
            project_root,
            python_source,
            " ".join(python_command),
            python_version,
            django_version,
            codex_executable,
            codex_version,
        )
        return self._preflight_result

    def _preflight_command(
        self,
        command: list[str],
        environment: Mapping[str, str],
        label: str,
    ) -> str:
        try:
            result = subprocess.run(
                command,
                cwd=self.config.project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=30,
                shell=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkerConfigurationError(
                f"Worker preflight failed to run {label}: {type(exc).__name__}"
            ) from exc
        output = (result.stdout or result.stderr).strip()
        if result.returncode != 0:
            raise WorkerConfigurationError(
                f"Worker preflight failed {label} "
                f"with exit code {result.returncode}: {output or 'no output'}"
            )
        return output

    def run_once(self) -> list[Path]:
        completed: list[Path] = []
        pending_tasks = self.queue.pending_tasks()
        LOGGER.info("Pending task check complete | pending=%d", len(pending_tasks))

        for pending_path in pending_tasks:
            try:
                processing_path = self.queue.claim(pending_path)
            except (OSError, ValueError) as exc:
                LOGGER.error("Task claim failed | file=%s | error=%s", pending_path, exc)
                continue

            LOGGER.info("Task claimed | file=%s", processing_path)
            try:
                self.processor.process(processing_path)
                issue_number = self._issue_number(processing_path)
                response_body = self._response_body(processing_path)
                marker_path = self._comment_marker_path(processing_path)
                comment_id = self._comment_id_from_marker(marker_path)
                if comment_id is None:
                    comment_id = self.comment_publisher.create_issue_comment(
                        issue_number,
                        response_body,
                    )
                    marker_path.write_text(f"{comment_id}\n", encoding="utf-8")
                    LOGGER.info(
                        "GitHub comment created | issue=%d | comment_id=%d",
                        issue_number,
                        comment_id,
                    )
                else:
                    LOGGER.info(
                        "GitHub comment already recorded | issue=%d | comment_id=%d",
                        issue_number,
                        comment_id,
                    )
                done_path = self.queue.complete(processing_path)
            except Exception:
                LOGGER.exception(
                    "Task processing failed; task remains in processing | file=%s",
                    processing_path,
                )
                continue

            completed.append(done_path)
            LOGGER.info("Task completed | file=%s", done_path)

        return completed

    @staticmethod
    def _issue_number(task_path: Path) -> int:
        filename_match = re.fullmatch(
            r"issue_([1-9]\d*)(?:_comment_([1-9]\d*))?\.md",
            task_path.name,
        )
        if filename_match is None:
            raise ValueError(f"Invalid GitHub issue task filename: {task_path.name}")
        issue_number = int(filename_match.group(1))

        try:
            lines = task_path.read_text(encoding="utf-8").splitlines()
            first_line = lines[0].strip()
        except (OSError, UnicodeError, IndexError) as exc:
            raise ValueError(f"Unreadable GitHub issue task: {task_path}") from exc
        header_match = re.fullmatch(r"# Issue ([1-9]\d*)", first_line)
        if header_match is None or int(header_match.group(1)) != issue_number:
            raise ValueError(
                f"GitHub issue number mismatch in task: {task_path.name}"
            )
        expected_comment_id = filename_match.group(2)
        if expected_comment_id is not None:
            comment_header = next(
                (line.strip() for line in lines[1:] if line.strip()),
                "",
            )
            if comment_header != f"# Comment {expected_comment_id}":
                raise ValueError(
                    f"GitHub comment number mismatch in task: {task_path.name}"
                )
        return issue_number

    def _response_body(self, task_path: Path) -> str:
        response_path = self.config.logs_dir / f"{task_path.stem}.response.md"
        try:
            response_body = response_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(
                f"GitHub comment response is not readable: {response_path}"
            ) from exc
        if not response_body.strip():
            raise RuntimeError(f"GitHub comment response is empty: {response_path}")
        response_body = re.sub(
            r"\n?AUTOMATION_RESULT:\s*code_changed=(?:yes|no);\s*"
            r"validation=(?:passed|failed|not_run|not_required)\s*\n?",
            "\n",
            response_body,
        ).strip() + "\n"
        quality_path = self.config.logs_dir / f"{task_path.stem}.quality.json"
        if not quality_path.exists():
            return response_body
        try:
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise RuntimeError(
                f"Invalid automation quality result: {quality_path}"
            ) from exc
        if (
            quality.get("code_changed") == "yes"
            and quality.get("validation") == "failed"
        ):
            return (
                "⚠️ 코드 변경 후 검증이 실패했습니다. 아래 결과를 완료로 간주하지 마세요.\n\n"
                + response_body
            )
        if (
            quality.get("code_changed") == "yes"
            and quality.get("validation") == "not_run"
        ):
            return (
                "⚠️ 코드 변경 후 검증을 실행하지 못했습니다. 신뢰 수준이 제한적입니다.\n\n"
                + response_body
            )
        if quality.get("code_changed") == "unknown":
            return "⚠️ 자동화 검증 상태를 확인할 수 없습니다.\n\n" + response_body
        return response_body

    def _comment_marker_path(self, task_path: Path) -> Path:
        return self.config.logs_dir / f"{task_path.stem}.commented"

    @staticmethod
    def _comment_id_from_marker(marker_path: Path) -> int | None:
        if not marker_path.exists():
            return None
        try:
            comment_id = int(marker_path.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeError, ValueError) as exc:
            raise RuntimeError(f"Invalid GitHub comment marker: {marker_path}") from exc
        if comment_id <= 0:
            raise RuntimeError(f"Invalid GitHub comment marker: {marker_path}")
        return comment_id

    def run_forever(self) -> None:
        self.preflight()
        LOGGER.info(
            "Codex worker started | pending=%s | interval=%ss",
            self.config.pending_dir,
            self.config.poll_interval_seconds,
        )
        while True:
            try:
                self.run_once()
            except Exception:
                LOGGER.exception("Unexpected worker cycle failure")
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
    config = WorkerConfig.from_env(base_dir=project_root)
    configure_logging(config.log_level)
    CodexWorker(config).run_forever()


if __name__ == "__main__":
    main()
