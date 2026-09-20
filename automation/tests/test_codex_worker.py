import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from automation.codex_worker import (
    CodexWorker,
    CodexCliExecutionError,
    PROMPT_PREAMBLE,
    RealCodexProcessor,
    TaskQueue,
    WorkerConfig,
    WorkerConfigurationError,
)


def make_config(root: Path) -> WorkerConfig:
    return WorkerConfig(
        pending_dir=root / "pending",
        processing_dir=root / "processing",
        done_dir=root / "done",
        project_root=root,
        logs_dir=root / "logs",
        attachments_dir=root / "automation" / "attachments",
        codex_command="codex.cmd",
        task_timeout_seconds=300,
        poll_interval_seconds=5,
        log_level="INFO",
        github_token="token",
        github_owner="owner",
        github_repo="repo",
        github_api_url="https://api.github.test",
        github_api_version="2022-11-28",
        request_timeout_seconds=15,
        reasoning_effort="high",
    )


class WorkerConfigTests(unittest.TestCase):
    def test_loads_and_resolves_environment_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = WorkerConfig.from_env(
                {
                    "TASKS_PENDING_DIR": "tasks/pending",
                    "TASKS_PROCESSING_DIR": "tasks/processing",
                    "TASKS_DONE_DIR": "tasks/done",
                    "CODEX_WORKER_LOGS_DIR": "automation/logs",
                    "AUTOMATION_ATTACHMENTS_DIR": "automation/attachments",
                    "CODEX_CLI_COMMAND": "codex.cmd",
                    "CODEX_TASK_TIMEOUT_SECONDS": "300",
                    "CODEX_WORKER_POLL_INTERVAL_SECONDS": "5",
                    "CODEX_WORKER_LOG_LEVEL": "info",
                    "GITHUB_TOKEN": "token",
                    "GITHUB_OWNER": "owner",
                    "GITHUB_REPO": "repo",
                    "GITHUB_API_URL": "https://api.github.test/",
                    "GITHUB_API_VERSION": "2022-11-28",
                    "GITHUB_REQUEST_TIMEOUT_SECONDS": "15",
                    "CODEX_REASONING_EFFORT": "high",
                },
                base_dir=root,
            )
            self.assertEqual(root / "tasks" / "pending", config.pending_dir)
            self.assertEqual(root.resolve(), config.project_root)
            self.assertEqual(root / "automation" / "logs", config.logs_dir)
            self.assertEqual(300, config.task_timeout_seconds)
            self.assertEqual("INFO", config.log_level)
            self.assertEqual("https://api.github.test", config.github_api_url)

    def test_rejects_duplicate_directories(self):
        environment = {
            "TASKS_PENDING_DIR": "tasks",
            "TASKS_PROCESSING_DIR": "tasks",
            "TASKS_DONE_DIR": "done",
            "CODEX_WORKER_LOGS_DIR": "logs",
            "AUTOMATION_ATTACHMENTS_DIR": "automation/attachments",
            "CODEX_CLI_COMMAND": "codex.cmd",
            "CODEX_TASK_TIMEOUT_SECONDS": "300",
            "CODEX_WORKER_POLL_INTERVAL_SECONDS": "5",
            "CODEX_WORKER_LOG_LEVEL": "INFO",
            "GITHUB_TOKEN": "token",
            "GITHUB_OWNER": "owner",
            "GITHUB_REPO": "repo",
            "GITHUB_API_URL": "https://api.github.test",
            "GITHUB_API_VERSION": "2022-11-28",
            "GITHUB_REQUEST_TIMEOUT_SECONDS": "15",
            "CODEX_REASONING_EFFORT": "high",
        }
        with self.assertRaisesRegex(WorkerConfigurationError, "must be different"):
            WorkerConfig.from_env(environment)

    def test_requires_github_comment_settings(self):
        environment = {
            "TASKS_PENDING_DIR": "pending",
            "TASKS_PROCESSING_DIR": "processing",
            "TASKS_DONE_DIR": "done",
            "CODEX_WORKER_LOGS_DIR": "logs",
            "AUTOMATION_ATTACHMENTS_DIR": "automation/attachments",
            "CODEX_CLI_COMMAND": "codex.cmd",
            "CODEX_TASK_TIMEOUT_SECONDS": "300",
            "CODEX_WORKER_POLL_INTERVAL_SECONDS": "5",
            "CODEX_WORKER_LOG_LEVEL": "INFO",
            "GITHUB_OWNER": "owner",
            "GITHUB_REPO": "repo",
            "GITHUB_API_URL": "https://api.github.test",
            "GITHUB_API_VERSION": "2022-11-28",
            "GITHUB_REQUEST_TIMEOUT_SECONDS": "15",
            "CODEX_REASONING_EFFORT": "high",
        }
        with self.assertRaisesRegex(WorkerConfigurationError, "GITHUB_TOKEN"):
            WorkerConfig.from_env(environment, base_dir=Path("project"))


class WorkerPreflightTests(unittest.TestCase):
    def test_prefers_project_venv_and_runs_preflight_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv_python = root / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_bytes(b"launcher")
            config = make_config(root)
            worker = CodexWorker(
                config,
                processor=Mock(),
                comment_publisher=Mock(),
            )
            completed = [
                Mock(returncode=0, stdout="Python 3.13.13\n", stderr=""),
                Mock(returncode=0, stdout="6.0.8\n", stderr=""),
                Mock(returncode=0, stdout="codex-cli 0.147.0\n", stderr=""),
            ]

            def find_command(name, path=None):
                if name == "codex.cmd":
                    return str(root / "tools" / "codex.cmd")
                return None

            with (
                patch("automation.codex_worker.shutil.which", side_effect=find_command),
                patch("automation.codex_worker.subprocess.run", side_effect=completed) as run,
            ):
                first = worker.preflight()
                second = worker.preflight()

            self.assertIs(first, second)
            self.assertEqual((str(venv_python.resolve()),), first.python_command)
            self.assertEqual("project-.venv", first.python_source)
            self.assertEqual("Python 3.13.13", first.python_version)
            self.assertEqual("6.0.8", first.django_version)
            self.assertEqual(3, run.call_count)
            self.assertEqual(
                [str(venv_python.resolve()), "--version"],
                run.call_args_list[0].args[0],
            )
            self.assertTrue(all(not call.kwargs["shell"] for call in run.call_args_list))

    def test_uses_py_3_only_when_project_venv_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root)
            worker = CodexWorker(
                config,
                processor=Mock(),
                comment_publisher=Mock(),
            )

            def find_command(name, path=None):
                return {
                    "py": "C:\\Windows\\py.exe",
                    "codex.cmd": "C:\\tools\\codex.cmd",
                }.get(name)

            completed = [
                Mock(returncode=0, stdout="Python 3.13.13\n", stderr=""),
                Mock(returncode=0, stdout="6.0.8\n", stderr=""),
                Mock(returncode=0, stdout="codex-cli 0.147.0\n", stderr=""),
            ]
            with (
                patch("automation.codex_worker.shutil.which", side_effect=find_command),
                patch("automation.codex_worker.subprocess.run", side_effect=completed),
            ):
                result = worker.preflight()

            self.assertEqual(("C:\\Windows\\py.exe", "-3"), result.python_command)
            self.assertEqual("py-3-fallback", result.python_source)

    def test_fails_preflight_when_django_is_not_importable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv_python = root / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_bytes(b"launcher")
            worker = CodexWorker(
                make_config(root),
                processor=Mock(),
                comment_publisher=Mock(),
            )
            completed = [
                Mock(returncode=0, stdout="Python 3.13.13\n", stderr=""),
                Mock(returncode=1, stdout="", stderr="No module named django"),
            ]
            with patch(
                "automation.codex_worker.subprocess.run", side_effect=completed
            ):
                with self.assertRaisesRegex(
                    WorkerConfigurationError, "Django import"
                ):
                    worker.preflight()

    def test_codex_subprocess_path_starts_with_project_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv_python = root / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_bytes(b"launcher")
            processor = RealCodexProcessor(
                root, root / "logs", "codex", timeout_seconds=300
            )

            inherited_path = os.pathsep.join(
                [str(root / "other-tools"), str(venv_python.parent)]
            )
            with patch.dict(os.environ, {"PATH": inherited_path}):
                environment, selected = processor._subprocess_environment()

            self.assertEqual(
                str(venv_python.parent), environment["PATH"].split(os.pathsep)[0]
            )
            self.assertEqual(str(root / ".venv"), environment["VIRTUAL_ENV"])
            self.assertEqual(str(venv_python), selected)


class TaskQueueTests(unittest.TestCase):
    def test_creates_queue_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            TaskQueue(config)
            self.assertTrue(config.pending_dir.is_dir())
            self.assertTrue(config.processing_dir.is_dir())
            self.assertTrue(config.done_dir.is_dir())

    def test_claim_and_complete_move_task_through_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            queue = TaskQueue(config)
            pending = config.pending_dir / "task.md"
            pending.write_text("task", encoding="utf-8")
            processing = queue.claim(pending)
            self.assertFalse(pending.exists())
            self.assertEqual(config.processing_dir / "task.md", processing)
            self.assertTrue(processing.exists())
            done = queue.complete(processing)
            self.assertFalse(processing.exists())
            self.assertEqual(config.done_dir / "task.md", done)
            self.assertTrue(done.exists())


class CodexWorkerTests(unittest.TestCase):
    def test_processes_pending_task_and_moves_it_to_done(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            queue = TaskQueue(config)
            task_name = "issue_42.md"
            (config.pending_dir / task_name).write_text(
                "# Issue 42\n\nquestion\n", encoding="utf-8"
            )
            config.logs_dir.mkdir()
            (config.logs_dir / "issue_42.response.md").write_text(
                "Codex response\n", encoding="utf-8"
            )
            processor = Mock()
            publisher = Mock()
            publisher.create_issue_comment.return_value = 1234
            worker = CodexWorker(
                config,
                queue=queue,
                processor=processor,
                comment_publisher=publisher,
            )
            completed = worker.run_once()
            processor.process.assert_called_once_with(
                config.processing_dir / task_name
            )
            publisher.create_issue_comment.assert_called_once_with(
                42, "Codex response\n"
            )
            self.assertEqual([config.done_dir / task_name], completed)
            self.assertTrue((config.done_dir / task_name).exists())
            self.assertEqual(
                "1234\n",
                (config.logs_dir / "issue_42.commented").read_text(
                    encoding="utf-8"
                ),
            )

    def test_failed_task_stays_in_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            queue = TaskQueue(config)
            (config.pending_dir / "issue_42.md").write_text(
                "# Issue 42\n\nquestion\n", encoding="utf-8"
            )
            processor = Mock()
            processor.process.side_effect = RuntimeError("failed")
            publisher = Mock()
            worker = CodexWorker(
                config,
                queue=queue,
                processor=processor,
                comment_publisher=publisher,
            )
            self.assertEqual([], worker.run_once())
            publisher.create_issue_comment.assert_not_called()
            self.assertTrue((config.processing_dir / "issue_42.md").exists())
            self.assertFalse((config.done_dir / "issue_42.md").exists())

    def test_missing_codex_response_keeps_task_in_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            queue = TaskQueue(config)
            (config.pending_dir / "task.md").write_text("task", encoding="utf-8")
            publisher = Mock()
            worker = CodexWorker(
                config, queue=queue, comment_publisher=publisher
            )
            completed = Mock(returncode=0, stdout="completed", stderr="")

            with patch(
                "automation.codex_worker.subprocess.run", return_value=completed
            ):
                self.assertEqual([], worker.run_once())

            publisher.create_issue_comment.assert_not_called()
            self.assertTrue((config.processing_dir / "task.md").exists())
            self.assertFalse((config.done_dir / "task.md").exists())

    def test_comment_failure_keeps_task_in_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            queue = TaskQueue(config)
            task = config.pending_dir / "issue_42.md"
            task.write_text("# Issue 42\n\nquestion\n", encoding="utf-8")
            config.logs_dir.mkdir()
            (config.logs_dir / "issue_42.response.md").write_text(
                "Codex response", encoding="utf-8"
            )
            processor = Mock()
            publisher = Mock()
            publisher.create_issue_comment.side_effect = RuntimeError("API failed")
            worker = CodexWorker(
                config,
                queue=queue,
                processor=processor,
                comment_publisher=publisher,
            )

            self.assertEqual([], worker.run_once())

            publisher.create_issue_comment.assert_called_once_with(
                42, "Codex response\n"
            )
            self.assertTrue((config.processing_dir / "issue_42.md").exists())
            self.assertFalse((config.done_dir / "issue_42.md").exists())

    def test_comment_marker_prevents_duplicate_post(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            queue = TaskQueue(config)
            task = config.pending_dir / "issue_42.md"
            task.write_text("# Issue 42\n\nquestion\n", encoding="utf-8")
            config.logs_dir.mkdir()
            (config.logs_dir / "issue_42.response.md").write_text(
                "Codex response", encoding="utf-8"
            )
            (config.logs_dir / "issue_42.commented").write_text(
                "1234\n", encoding="utf-8"
            )
            processor = Mock()
            publisher = Mock()
            worker = CodexWorker(
                config,
                queue=queue,
                processor=processor,
                comment_publisher=publisher,
            )

            completed = worker.run_once()

            publisher.create_issue_comment.assert_not_called()
            self.assertEqual([config.done_dir / "issue_42.md"], completed)

    def test_invalid_issue_filename_does_not_publish_comment(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            queue = TaskQueue(config)
            task = config.pending_dir / "task.md"
            task.write_text("# Issue 42\n\nquestion\n", encoding="utf-8")
            config.logs_dir.mkdir()
            (config.logs_dir / "task.response.md").write_text(
                "Codex response", encoding="utf-8"
            )
            publisher = Mock()
            worker = CodexWorker(
                config,
                queue=queue,
                processor=Mock(),
                comment_publisher=publisher,
            )

            self.assertEqual([], worker.run_once())

            publisher.create_issue_comment.assert_not_called()
            self.assertTrue((config.processing_dir / "task.md").exists())

    def test_comment_task_posts_response_to_original_issue_and_moves_to_done(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            queue = TaskQueue(config)
            task_name = "issue_42_comment_555.md"
            (config.pending_dir / task_name).write_text(
                "# Issue 42\n\n# Comment 555\n\n후속 요청\n",
                encoding="utf-8",
            )
            config.logs_dir.mkdir()
            (config.logs_dir / "issue_42_comment_555.response.md").write_text(
                "후속 응답\n",
                encoding="utf-8",
            )
            publisher = Mock()
            publisher.create_issue_comment.return_value = 777
            worker = CodexWorker(
                config,
                queue=queue,
                processor=Mock(),
                comment_publisher=publisher,
            )

            completed = worker.run_once()

            publisher.create_issue_comment.assert_called_once_with(42, "후속 응답\n")
            self.assertEqual([config.done_dir / task_name], completed)
            self.assertEqual(
                "777\n",
                (config.logs_dir / "issue_42_comment_555.commented").read_text(
                    encoding="utf-8"
                ),
            )


class RealCodexProcessorTests(unittest.TestCase):
    @staticmethod
    def _processor(root):
        return RealCodexProcessor(
            root,
            root / "logs",
            "codex",
            timeout_seconds=300,
            attachments_dir=root / "automation" / "attachments",
        )

    def test_parses_only_explicit_attachment_metadata_blocks(self):
        with tempfile.TemporaryDirectory(prefix="한글-프로젝트-") as directory:
            root = Path(directory)
            attachment_dir = (
                root / "automation" / "attachments" / "issue_42" / "한글 폴더"
            )
            attachment_dir.mkdir(parents=True)
            image = attachment_dir / "로그인 화면.jpg"
            image.write_bytes(b"jpeg")
            markdown = (
                "사용자:\n이미지 1: 본문 설명\n\n"
                "Codex:\n- 이미지 1: 「인포그래픽」 설명\n\n"
                "[첨부 이미지]\n"
                f"- 이미지 2: {image.resolve()}\n"
            )

            paths = self._processor(root)._attachment_paths(markdown)

            self.assertEqual([image.resolve()], paths)

    def test_ignores_download_failure_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown = (
                "[첨부 이미지]\n"
                "- 이미지 1: 다운로드 실패 (signature: invalid image)\n"
            )

            self.assertEqual([], self._processor(root)._attachment_paths(markdown))

    def test_preserves_multiple_and_legacy_history_image_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attachment_dir = root / "automation" / "attachments" / "issue_42"
            attachment_dir.mkdir(parents=True)
            first = attachment_dir / "first.png"
            second = attachment_dir / "second.webp"
            first.write_bytes(b"png")
            second.write_bytes(b"webp")
            markdown = (
                "사용자:\n이전 요청\n\n첨부 이미지:\n"
                f"- 이미지 1: {first.resolve()}\n\n"
                "Codex:\n- 이미지 1: 이전 이미지 설명\n\n"
                "사용자:\n현재 요청\n\n[첨부 이미지]\n"
                f"- 이미지 2: {second.resolve()}\n"
            )

            paths = self._processor(root)._attachment_paths(markdown)

            self.assertEqual([first.resolve(), second.resolve()], paths)

    def test_rejects_metadata_path_outside_attachment_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside.png"
            outside.write_bytes(b"png")
            markdown = f"[첨부 이미지]\n- 이미지 1: {outside.resolve()}\n"

            with self.assertRaisesRegex(
                CodexCliExecutionError, "Invalid task image attachment path"
            ):
                self._processor(root)._attachment_paths(markdown)

    def test_rejects_missing_path_inside_attachment_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "automation" / "attachments" / "missing.jpg"
            markdown = f"[첨부 이미지]\n- 이미지 1: {missing}\n"

            with self.assertRaisesRegex(
                CodexCliExecutionError, "Invalid task image attachment path"
            ):
                self._processor(root)._attachment_paths(markdown)

    def test_attaches_multiple_task_images_to_codex_in_metadata_order(self):
        with tempfile.TemporaryDirectory(prefix="한글-프로젝트-") as directory:
            root = Path(directory)
            attachments = root / "automation" / "attachments" / "issue_42" / "issue"
            attachments.mkdir(parents=True)
            first = attachments / "first.png"
            second = attachments / "second.webp"
            first.write_bytes(b"png")
            second.write_bytes(b"webp")
            task = root / "issue_42.md"
            task.write_text(
                f"# Issue 42\n\n화면 비교\n\n[첨부 이미지]\n"
                f"- 이미지 1: {first.resolve()}\n"
                f"- 이미지 2: {second.resolve()}\n",
                encoding="utf-8",
            )
            processor = RealCodexProcessor(
                root,
                root / "logs",
                "codex",
                timeout_seconds=300,
                attachments_dir=root / "automation" / "attachments",
            )
            response_path = root / "logs" / "issue_42.response.md"
            completed = Mock(returncode=0, stdout="done", stderr="")

            def run_codex(*args, **kwargs):
                response_path.write_text("이미지 분석 완료", encoding="utf-8")
                return completed

            with patch(
                "automation.codex_worker.subprocess.run", side_effect=run_codex
            ) as run:
                processor.process(task)

            command = run.call_args.args[0]
            image_index = command.index("--image")
            self.assertEqual(
                ["--image", str(first.resolve()), str(second.resolve())],
                command[image_index:image_index + 3],
            )
            self.assertIn("--sandbox", command)
            self.assertIn("workspace-write", command)
            self.assertIn("--output-last-message", command)
            self.assertEqual("-", command[-1])
            self.assertEqual(
                task.read_text(encoding="utf-8"),
                (root / "logs" / "issue_42.prompt.md")
                .read_text(encoding="utf-8")
                .removeprefix(f"{PROMPT_PREAMBLE}\n\n"),
            )

    def test_runs_codex_exec_with_markdown_prompt_and_saves_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "issue_42.md"
            issue_markdown = "# Issue 42\n\n\ud55c\uae00 \uc81c\ubaa9\n\n\ud55c\uae00 \ubcf8\ubb38\uc744 \ucc98\ub9ac\ud574 \uc918."
            task.write_text(issue_markdown, encoding="utf-8")
            processor = RealCodexProcessor(
                root,
                root / "logs",
                "codex",
                timeout_seconds=300,
            )
            completed = Mock(returncode=0, stdout="completed", stderr="progress")
            response_path = root / "logs" / "issue_42.response.md"

            def run_codex(*args, **kwargs):
                response_path.write_text("\uc791\uc5c5\uc744 \uc644\ub8cc\ud588\uc2b5\ub2c8\ub2e4.", encoding="utf-8")
                return completed

            with patch("automation.codex_worker.subprocess.run", side_effect=run_codex) as run:
                processor.process(task)

            prompt = f"{PROMPT_PREAMBLE}\n\n{issue_markdown}"
            command = run.call_args.args[0]
            self.assertEqual("codex", command[0])
            self.assertNotIn("--approve-for-me", command)
            self.assertIn('model_reasoning_effort="high"', command)
            self.assertEqual("-", command[-1])
            self.assertEqual(root, run.call_args.kwargs["cwd"])
            self.assertEqual(prompt, run.call_args.kwargs["input"])
            self.assertFalse(run.call_args.kwargs["shell"])
            self.assertIn("PATH", run.call_args.kwargs["env"])
            self.assertEqual(
                prompt,
                (root / "logs" / "issue_42.prompt.md").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertEqual(
                "completed",
                (root / "logs" / "issue_42.stdout.log").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "progress",
                (root / "logs" / "issue_42.stderr.log").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "\uc791\uc5c5\uc744 \uc644\ub8cc\ud588\uc2b5\ub2c8\ub2e4.",
                response_path.read_text(encoding="utf-8"),
            )

    def test_records_machine_readable_validation_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "issue_42.md"
            task.write_text("task", encoding="utf-8")
            response_path = root / "logs" / "issue_42.response.md"
            processor = RealCodexProcessor(
                root, root / "logs", "codex", timeout_seconds=300
            )
            completed = Mock(returncode=0, stdout="completed", stderr="")

            def run_codex(*args, **kwargs):
                response_path.write_text(
                    "검증 실패\n\n"
                    "AUTOMATION_RESULT: code_changed=yes; validation=failed\n",
                    encoding="utf-8",
                )
                return completed

            with patch("automation.codex_worker.subprocess.run", side_effect=run_codex):
                processor.process(task)

            self.assertEqual(
                '{\n  "code_changed": "yes",\n  "validation": "failed"\n}\n',
                (root / "logs" / "issue_42.quality.json").read_text(
                    encoding="utf-8"
                ),
            )

    def test_success_without_response_is_treated_as_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "issue_42.md"
            task.write_text("task", encoding="utf-8")
            processor = RealCodexProcessor(
                root, root / "logs", "codex", timeout_seconds=300
            )
            completed = Mock(returncode=0, stdout="completed", stderr="")

            with patch("automation.codex_worker.subprocess.run", return_value=completed):
                with self.assertRaisesRegex(
                    CodexCliExecutionError, "readable response"
                ):
                    processor.process(task)

    def test_success_with_empty_response_is_treated_as_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "issue_42.md"
            task.write_text("task", encoding="utf-8")
            response_path = root / "logs" / "issue_42.response.md"
            processor = RealCodexProcessor(
                root, root / "logs", "codex", timeout_seconds=300
            )
            completed = Mock(returncode=0, stdout="completed", stderr="")

            def run_codex(*args, **kwargs):
                response_path.write_text("  \n", encoding="utf-8")
                return completed

            with patch("automation.codex_worker.subprocess.run", side_effect=run_codex):
                with self.assertRaisesRegex(CodexCliExecutionError, "empty response"):
                    processor.process(task)

    def test_raises_after_saving_logs_when_codex_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "issue_42.md"
            task.write_text("task", encoding="utf-8")
            processor = RealCodexProcessor(
                root,
                root / "logs",
                "codex",
                timeout_seconds=300,
            )
            failed = Mock(returncode=7, stdout="partial", stderr="failure")

            with patch("automation.codex_worker.subprocess.run", return_value=failed):
                with self.assertRaisesRegex(CodexCliExecutionError, "exit code 7"):
                    processor.process(task)

            self.assertEqual(
                "failure",
                (root / "logs" / "issue_42.stderr.log").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                f"{PROMPT_PREAMBLE}\n\ntask",
                (root / "logs" / "issue_42.prompt.md").read_text(
                    encoding="utf-8"
                ),
            )

    def test_raises_and_logs_when_codex_cannot_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "issue_42.md"
            task.write_text("task", encoding="utf-8")
            processor = RealCodexProcessor(
                root,
                root / "logs",
                "codex",
                timeout_seconds=300,
            )

            with patch(
                "automation.codex_worker.subprocess.run",
                side_effect=FileNotFoundError("missing"),
            ):
                with self.assertRaisesRegex(CodexCliExecutionError, "could not start"):
                    processor.process(task)

            self.assertIn(
                "missing",
                (root / "logs" / "issue_42.stderr.log").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                f"{PROMPT_PREAMBLE}\n\ntask",
                (root / "logs" / "issue_42.prompt.md").read_text(
                    encoding="utf-8"
                ),
            )

    def test_timeout_raises_and_saves_partial_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "issue_42.md"
            task.write_text("task", encoding="utf-8")
            processor = RealCodexProcessor(
                root,
                root / "logs",
                "codex",
                timeout_seconds=12,
            )
            timeout = subprocess.TimeoutExpired(
                cmd=["codex"],
                timeout=12,
                output=b"partial stdout",
                stderr=b"partial stderr",
            )

            with patch(
                "automation.codex_worker.subprocess.run",
                side_effect=timeout,
            ):
                with self.assertRaisesRegex(CodexCliExecutionError, "timed out"):
                    processor.process(task)

            self.assertEqual(
                "partial stdout",
                (root / "logs" / "issue_42.stdout.log").read_text(encoding="utf-8"),
            )
            stderr = (root / "logs" / "issue_42.stderr.log").read_text(
                encoding="utf-8"
            )
            self.assertIn("partial stderr", stderr)
            self.assertIn("timed out after 12 seconds", stderr)
            self.assertEqual(
                f"{PROMPT_PREAMBLE}\n\ntask",
                (root / "logs" / "issue_42.prompt.md").read_text(
                    encoding="utf-8"
                ),
            )

    def test_windows_and_linux_use_stdin_prompt_commands(self):
        root = Path("project")
        windows = RealCodexProcessor(
            root,
            root / "logs",
            "codex.cmd",
            timeout_seconds=300,
        )
        linux = RealCodexProcessor(
            root,
            root / "logs",
            "codex",
            timeout_seconds=300,
        )
        windows_response = root / "logs" / "issue_42.response.md"
        linux_response = root / "logs" / "issue_42.response.md"

        self.assertEqual(
            [
                "codex.cmd",
                "exec",
                "--sandbox",
                "workspace-write",
                "--config",
                'model_reasoning_effort="high"',
                "--output-last-message",
                str(windows_response),
                "-",
            ],
            windows._build_command(windows_response),
        )
        self.assertEqual(
            [
                "codex",
                "exec",
                "--sandbox",
                "workspace-write",
                "--config",
                'model_reasoning_effort="high"',
                "--output-last-message",
                str(linux_response),
                "-",
            ],
            linux._build_command(linux_response),
        )

    def test_prompt_uses_development_partner_preamble_and_preserves_message(self):
        issue_markdown = "# Issue 42\n\n\uc624\ub298 \ubc1c\uacac\ud55c \ubc84\uadf8 \uace0\uccd0\uc918.\n\n\ub85c\uadf8\uc778 \ud6c4 500\uc774 \ub098.\n"
        prompt = RealCodexProcessor._build_prompt(issue_markdown)

        self.assertTrue(prompt.startswith(PROMPT_PREAMBLE))
        self.assertIn("\uac1c\ubc1c \ud30c\ud2b8\ub108", PROMPT_PREAMBLE)
        self.assertIn("\uc790\uc5f0\uc5b4 \uba54\uc2dc\uc9c0", PROMPT_PREAMBLE)
        self.assertIn("추측해서 코드를 수정하지 말고", PROMPT_PREAMBLE)
        self.assertIn("이미지와 무관한 독립적인 텍스트 요청", PROMPT_PREAMBLE)
        self.assertIn(".venv\\Scripts\\python.exe", PROMPT_PREAMBLE)
        self.assertIn("validation=failed", PROMPT_PREAMBLE)
        self.assertIn("AUTOMATION_RESULT:", PROMPT_PREAMBLE)
        self.assertTrue(prompt.endswith(issue_markdown))


if __name__ == "__main__":
    unittest.main()
