"""Securely persist GitHub-hosted image attachments for Codex tasks."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

LOGGER = logging.getLogger("automation.attachments")

ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
GITHUB_ATTACHMENT_HOSTS = {
    "github.com": "/user-attachments/assets/",
    "user-images.githubusercontent.com": "/",
    "private-user-images.githubusercontent.com": "/",
    "github-production-user-asset-6210df.s3.amazonaws.com": "/",
}
GITHUB_S3_ASSET_PATH = re.compile(
    r"^/\d+/[A-Za-z0-9._-]+\.(?:png|jpe?g|webp)$", re.IGNORECASE
)
PLAIN_URL = re.compile(r"https://[^\s<>]+", re.IGNORECASE)
GITHUB_ONLY_HEADERS = (
    "Authorization",
    "Accept",
    "X-GitHub-Api-Version",
)


@dataclass(frozen=True)
class Attachment:
    path: Path | None
    error: str | None = None


def is_allowed_github_attachment_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    required_prefix = GITHUB_ATTACHMENT_HOSTS.get(host)
    allowed = bool(
        parsed.scheme == "https"
        and port in (None, 443)
        and parsed.username is None
        and parsed.password is None
        and required_prefix is not None
        and parsed.path.startswith(required_prefix)
    )
    if host == "github-production-user-asset-6210df.s3.amazonaws.com":
        allowed = allowed and GITHUB_S3_ASSET_PATH.fullmatch(parsed.path) is not None
    return allowed


def extract_github_attachment_urls(markdown: str) -> list[str]:
    """Extract supported GitHub attachment destinations in document order."""
    candidates: list[tuple[int, str]] = []
    cursor = 0
    while True:
        image_start = markdown.find("![", cursor)
        if image_start < 0:
            break
        destination_start = markdown.find("](", image_start + 2)
        if destination_start < 0:
            break
        position = destination_start + 2
        if position < len(markdown) and markdown[position] == "<":
            end = markdown.find(">", position + 1)
            destination = markdown[position + 1:end] if end >= 0 else ""
            cursor = end + 1 if end >= 0 else position + 1
        else:
            end = position
            while end < len(markdown) and markdown[end] not in ")\r\n\t ":
                end += 1
            destination = markdown[position:end]
            cursor = max(end + 1, position + 1)
        if destination:
            candidates.append((position, destination.replace("\\)", ")")))

    for match in PLAIN_URL.finditer(markdown):
        candidates.append((match.start(), match.group(0).rstrip(".,;:!?)]}")))

    urls: list[str] = []
    seen: set[str] = set()
    for _, candidate in sorted(candidates, key=lambda item: item[0]):
        if candidate not in seen and is_allowed_github_attachment_url(candidate):
            seen.add(candidate)
            urls.append(candidate)
    return urls


class GitHubAttachmentStore:
    """Download allowlisted images with bounded streaming and persistent dedupe."""

    def __init__(
        self,
        root_dir: Path,
        session: requests.Session,
        max_bytes: int,
        timeout_seconds: float,
    ):
        self.root_dir = root_dir
        self.session = session
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds

    def collect(
        self,
        issue_number: int,
        source: str,
        markdown: str,
    ) -> list[Attachment]:
        return [
            self._download(issue_number, source, url)
            for url in extract_github_attachment_urls(markdown)
        ]

    def _download(self, issue_number: int, source: str, url: str) -> Attachment:
        scope_dir = self.root_dir / f"issue_{issue_number}" / source
        url_key = hashlib.sha256(self._canonical_url(url).encode("utf-8")).hexdigest()
        existing = next(scope_dir.glob(f"{url_key}.*"), None) if scope_dir.exists() else None
        if existing is not None and existing.suffix in ALLOWED_IMAGE_TYPES.values():
            return Attachment(existing.resolve())

        stage = "request"
        current_host = (urlsplit(url).hostname or "").lower()
        status_code: int | None = None
        content_type: str | None = None
        try:
            current_url = url
            response = None
            for _ in range(6):
                request_options = {
                    "timeout": self.timeout_seconds,
                    "stream": True,
                    "allow_redirects": False,
                }
                isolated_headers = self._isolated_headers(current_url)
                if isolated_headers is not None:
                    request_options["headers"] = isolated_headers
                response = self.session.get(
                    current_url,
                    **request_options,
                )
                status_code = response.status_code
                content_type = (
                    response.headers.get("Content-Type", "")
                    .split(";", 1)[0]
                    .lower()
                    or None
                )
                if response.status_code not in {301, 302, 303, 307, 308}:
                    break
                stage = "redirect"
                redirected_url = urljoin(
                    current_url, response.headers.get("Location", "")
                )
                if not is_allowed_github_attachment_url(redirected_url):
                    raise ValueError(
                        "redirected outside the GitHub attachment allowlist"
                    )
                current_url = redirected_url
                current_host = (urlsplit(current_url).hostname or "").lower()
                stage = "request"
            else:
                raise ValueError("too many attachment redirects")
            if response is None:
                raise ValueError("attachment response is unavailable")
            stage = "http_status"
            response.raise_for_status()
            stage = "mime"
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            expected_extension = ALLOWED_IMAGE_TYPES.get(content_type)
            if expected_extension is None:
                raise ValueError("unsupported image content type")
            source_extension = Path(urlsplit(current_url).path).suffix.lower()
            stage = "extension"
            if source_extension in {".png", ".jpg", ".jpeg", ".webp"}:
                matching_extensions = (
                    {".jpg", ".jpeg"}
                    if expected_extension == ".jpg"
                    else {expected_extension}
                )
                if source_extension not in matching_extensions:
                    raise ValueError("image extension and content type do not match")
            content_length = response.headers.get("Content-Length")
            stage = "size"
            if content_length and int(content_length) > self.max_bytes:
                raise ValueError("image exceeds configured size limit")

            data = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                data.extend(chunk)
                if len(data) > self.max_bytes:
                    raise ValueError("image exceeds configured size limit")
            stage = "signature"
            self._validate_image(bytes(data), content_type)

            stage = "write"
            scope_dir.mkdir(parents=True, exist_ok=True)
            destination = scope_dir / f"{url_key}{expected_extension}"
            temporary = scope_dir / f"{url_key}.part"
            temporary.write_bytes(data)
            temporary.replace(destination)
            stage = "manifest"
            self._write_manifest(scope_dir, url_key, url, destination, content_type)
            return Attachment(destination.resolve())
        except (requests.RequestException, OSError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            LOGGER.warning(
                "Attachment download failed | issue=%d | source=%s | stage=%s "
                "| host=%s | status_code=%s | content_type=%s | reason=%s",
                issue_number,
                source,
                stage,
                current_host,
                status_code if status_code is not None else "none",
                content_type or "none",
                reason,
            )
            return Attachment(None, f"{stage}: {reason}")

    @staticmethod
    def _isolated_headers(url: str) -> dict[str, None] | None:
        """Remove GitHub API credentials from non-GitHub attachment requests."""
        host = (urlsplit(url).hostname or "").lower()
        if host == "github.com":
            return None
        return {name: None for name in GITHUB_ONLY_HEADERS}

    @staticmethod
    def _validate_image(data: bytes, content_type: str) -> None:
        valid = False
        if content_type == "image/png":
            valid = len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n")
        elif content_type == "image/jpeg":
            valid = GitHubAttachmentStore._is_valid_jpeg(data)
        elif content_type == "image/webp":
            valid = len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        if not valid:
            raise ValueError("response body is not a valid supported image")

    @staticmethod
    def _is_valid_jpeg(data: bytes) -> bool:
        """Validate JPEG marker structure while allowing metadata after EOI."""
        if len(data) < 4 or data[:2] != b"\xff\xd8":
            return False

        start_of_frame_markers = {
            0xC0, 0xC1, 0xC2, 0xC3,
            0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB,
            0xCD, 0xCE, 0xCF,
        }
        position = 2
        saw_frame = False
        saw_scan = False
        in_scan = False

        while position < len(data):
            marker_start = data.find(b"\xff", position)
            if marker_start < 0:
                return False
            if not in_scan and marker_start != position:
                return False

            marker_position = marker_start + 1
            while marker_position < len(data) and data[marker_position] == 0xFF:
                marker_position += 1
            if marker_position >= len(data):
                return False
            marker = data[marker_position]

            if in_scan:
                if marker == 0x00 or 0xD0 <= marker <= 0xD7:
                    position = marker_position + 1
                    continue
                in_scan = False

            if marker == 0xD9:
                return saw_frame and saw_scan
            if marker == 0xD8:
                return False
            if marker == 0x01 or 0xD0 <= marker <= 0xD7:
                position = marker_position + 1
                continue

            length_position = marker_position + 1
            if length_position + 2 > len(data):
                return False
            segment_length = int.from_bytes(
                data[length_position:length_position + 2], "big"
            )
            if segment_length < 2:
                return False
            segment_end = length_position + segment_length
            if segment_end > len(data):
                return False

            if marker in start_of_frame_markers:
                saw_frame = True
            elif marker == 0xDA:
                if not saw_frame:
                    return False
                saw_scan = True
                in_scan = True
            position = segment_end

        return False

    @classmethod
    def _write_manifest(
        cls,
        scope_dir: Path,
        url_key: str,
        source_url: str,
        destination: Path,
        content_type: str,
    ) -> None:
        manifest_path = scope_dir / "attachments.json"
        manifest = {}
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest[url_key] = {
            "source": cls._canonical_url(source_url),
            "file": destination.name,
            "content_type": content_type,
        }
        temporary = manifest_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(manifest_path)

    @staticmethod
    def _canonical_url(url: str) -> str:
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", ""))


def render_attachment_lines(
    attachments: Iterable[Attachment],
    start_index: int,
) -> tuple[list[str], list[Path], int]:
    """Render logical labels while preserving CLI image order."""
    lines: list[str] = []
    paths: list[Path] = []
    next_index = start_index
    for attachment in attachments:
        label = f"이미지 {next_index}"
        if attachment.path is not None:
            lines.append(f"- {label}: {attachment.path}")
            paths.append(attachment.path)
        else:
            lines.append(f"- {label}: 다운로드 실패 ({attachment.error or 'unknown'})")
        next_index += 1
    return lines, paths, next_index
