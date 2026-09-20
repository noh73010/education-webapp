import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from automation.attachments import (
    GitHubAttachmentStore,
    extract_github_attachment_urls,
    is_allowed_github_attachment_url,
)


ASSET = "https://github.com/user-attachments/assets/12345678-abcd"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16
WEBP = b"RIFF" + b"\x04\x00\x00\x00" + b"WEBP"


def jpeg_segment(marker, payload):
    return b"\xff" + bytes([marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def jpeg_bytes(app_marker=None, app_payload=b"", progressive=False, trailing=b""):
    data = bytearray(b"\xff\xd8")
    if app_marker is not None:
        data.extend(jpeg_segment(app_marker, app_payload))
    frame_payload = b"\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    data.extend(jpeg_segment(0xC2 if progressive else 0xC0, frame_payload))
    data.extend(jpeg_segment(0xDA, b"\x01\x01\x00\x00\x3f\x00"))
    data.extend(b"\x11\xff\x00\x22\xff\xd9")
    data.extend(trailing)
    return bytes(data)


def image_response(data=PNG, content_type="image/png"):
    response = Mock()
    response.status_code = 200
    response.headers = {
        "Content-Type": content_type,
        "Content-Length": str(len(data)),
    }
    response.iter_content.return_value = [data]
    return response


class AttachmentUrlTests(unittest.TestCase):
    def test_extracts_issue_comment_multiple_and_mixed_images_in_order(self):
        second = "https://user-images.githubusercontent.com/1/second.png"
        markdown = f"설명\n![첫 화면]({ASSET})\n텍스트 {second}"

        self.assertEqual(
            [ASSET, second],
            extract_github_attachment_urls(markdown),
        )

    def test_image_free_and_malformed_markdown_are_safe(self):
        self.assertEqual([], extract_github_attachment_urls("텍스트만"))
        self.assertEqual([], extract_github_attachment_urls("![broken](not-a-url"))

    def test_only_allowlisted_https_github_attachment_urls_are_accepted(self):
        allowed = (
            ASSET,
            "https://user-images.githubusercontent.com/1/image.png",
            "https://private-user-images.githubusercontent.com/1/image.png",
            "https://github-production-user-asset-6210df.s3.amazonaws.com/290238612/example.jpg",
        )
        blocked = (
            "http://github.com/user-attachments/assets/1",
            "http://localhost/image.png",
            "http://127.0.0.1/image.png",
            "file:///tmp/image.png",
            "ftp://github.com/image.png",
            "https://example.com/image.png",
            "https://github.com/owner/repo/image.png",
            "https://github-production-user-asset-6210df.s3.amazonaws.com/not-an-asset",
        )
        self.assertTrue(all(is_allowed_github_attachment_url(url) for url in allowed))
        self.assertFalse(any(is_allowed_github_attachment_url(url) for url in blocked))


class GitHubAttachmentStoreTests(unittest.TestCase):
    def test_preserves_png_jpeg_and_webp_signature_validation(self):
        supported = (
            (PNG, "image/png"),
            (jpeg_bytes(), "image/jpeg"),
            (WEBP, "image/webp"),
        )

        for data, content_type in supported:
            with self.subTest(content_type=content_type):
                GitHubAttachmentStore._validate_image(data, content_type)

    def test_accepts_jfif_exif_progressive_and_samsung_seft_jpeg(self):
        variants = {
            "jfif": jpeg_bytes(0xE0, b"JFIF\x00" + b"\x00" * 9),
            "exif": jpeg_bytes(0xE1, b"Exif\x00\x00" + b"MM\x00*"),
            "progressive": jpeg_bytes(progressive=True),
            "samsung_seft": jpeg_bytes(
                0xE1,
                b"Exif\x00\x00" + b"MM\x00*",
                trailing=b"\x00" * 187 + b"SEFT",
            ),
        }

        for name, data in variants.items():
            with self.subTest(name=name):
                GitHubAttachmentStore._validate_image(data, "image/jpeg")

    def test_rejects_truncated_jpeg_html_and_mime_mismatch(self):
        rejected = (
            (jpeg_bytes()[:-2], "image/jpeg"),
            (b"<!doctype html><html>error</html>", "image/jpeg"),
            (PNG, "image/jpeg"),
            (jpeg_bytes(), "image/png"),
        )

        for data, content_type in rejected:
            with self.subTest(content_type=content_type, head=data[:8]):
                with self.assertRaisesRegex(ValueError, "valid supported image"):
                    GitHubAttachmentStore._validate_image(data, content_type)

    def test_stores_by_issue_and_comment_and_deduplicates_download(self):
        with tempfile.TemporaryDirectory(prefix="한글-첨부-") as directory:
            session = Mock(spec=requests.Session)
            session.get.return_value = image_response()
            store = GitHubAttachmentStore(Path(directory), session, 1024, 15)

            first = store.collect(12, "comment_123", f"![화면]({ASSET})")[0]
            second = store.collect(12, "comment_123", f"![화면]({ASSET})")[0]

            self.assertEqual(first.path, second.path)
            self.assertIsNotNone(first.path)
            self.assertEqual("comment_123", first.path.parent.name)
            self.assertEqual("issue_12", first.path.parent.parent.name)
            self.assertTrue((first.path.parent / "attachments.json").exists())
            session.get.assert_called_once()

    def test_rejects_redirect_before_requesting_non_github_target(self):
        with tempfile.TemporaryDirectory() as directory:
            redirect = Mock(status_code=302, headers={"Location": "http://127.0.0.1/a"})
            session = Mock(spec=requests.Session)
            session.get.return_value = redirect
            store = GitHubAttachmentStore(Path(directory), session, 1024, 15)

            attachment = store.collect(1, "issue", f"![x]({ASSET})")[0]

            self.assertIsNone(attachment.path)
            self.assertIn("redirect:", attachment.error)
            session.get.assert_called_once()

    def test_rejects_content_type_mismatch_and_oversized_image(self):
        with tempfile.TemporaryDirectory() as directory:
            for response in (
                image_response(content_type="text/html"),
                image_response(data=PNG + b"x" * 100),
            ):
                with self.subTest(content_type=response.headers["Content-Type"]):
                    session = Mock(spec=requests.Session)
                    session.get.return_value = response
                    store = GitHubAttachmentStore(Path(directory), session, 32, 15)
                    attachment = store.collect(1, "issue", f"![x]({ASSET})")[0]
                    self.assertIsNone(attachment.path)
                    self.assertIsNotNone(attachment.error)

    def test_rejects_invalid_image_bytes_and_http_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            bad_image = image_response(data=b"not an image")
            http_error = image_response()
            http_error.raise_for_status.side_effect = requests.HTTPError("404")
            for response in (bad_image, http_error):
                session = Mock(spec=requests.Session)
                session.get.return_value = response
                store = GitHubAttachmentStore(Path(directory), session, 1024, 15)
                attachment = store.collect(1, "issue", f"![x]({ASSET})")[0]
                self.assertIsNone(attachment.path)

    def test_network_timeout_does_not_raise_or_leak_url(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Mock(spec=requests.Session)
            session.get.side_effect = requests.Timeout("secret query")
            store = GitHubAttachmentStore(Path(directory), session, 1024, 15)

            attachment = store.collect(1, "issue", f"![x]({ASSET}?token=secret)")[0]

            self.assertIsNone(attachment.path)
            self.assertEqual("request: Timeout", attachment.error)

    def test_accepts_current_github_s3_redirect_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = (
                "https://github-production-user-asset-6210df.s3.amazonaws.com/"
                "290238612/example.jpg?X-Amz-Signature=signed-value"
            )
            redirect = Mock(status_code=302, headers={"Location": target})
            jpeg = image_response(
                data=jpeg_bytes(),
                content_type="image/jpeg",
            )
            session = Mock(spec=requests.Session)
            session.get.side_effect = [redirect, jpeg]
            store = GitHubAttachmentStore(Path(directory), session, 1024, 15)

            attachment = store.collect(10, "comment_1", f"![x]({ASSET})")[0]

            self.assertIsNotNone(attachment.path)
            self.assertEqual(".jpg", attachment.path.suffix)
            self.assertEqual(2, session.get.call_count)
            self.assertNotIn("headers", session.get.call_args_list[0].kwargs)
            self.assertEqual(target, session.get.call_args_list[1].args[0])
            self.assertEqual(
                {
                    "Authorization": None,
                    "Accept": None,
                    "X-GitHub-Api-Version": None,
                },
                session.get.call_args_list[1].kwargs["headers"],
            )

    def test_s3_request_removes_github_session_headers_when_prepared(self):
        target = (
            "https://github-production-user-asset-6210df.s3.amazonaws.com/"
            "290238612/example.png?X-Amz-Signature=secret"
        )
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": "Bearer secret-token",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        headers = GitHubAttachmentStore._isolated_headers(target)

        prepared = session.prepare_request(
            requests.Request("GET", target, headers=headers)
        )

        self.assertNotIn("Authorization", prepared.headers)
        self.assertNotIn("Accept", prepared.headers)
        self.assertNotIn("X-GitHub-Api-Version", prepared.headers)
        self.assertIn("X-Amz-Signature=secret", prepared.url)

    def test_validates_every_redirect_and_strips_headers_after_github(self):
        with tempfile.TemporaryDirectory() as directory:
            second_github = (
                "https://github.com/user-attachments/assets/"
                "87654321-dcba"
            )
            target = (
                "https://github-production-user-asset-6210df.s3.amazonaws.com/"
                "290238612/example.png?X-Amz-Signature=signed"
            )
            first = Mock(status_code=302, headers={"Location": second_github})
            second = Mock(status_code=302, headers={"Location": target})
            session = Mock(spec=requests.Session)
            session.get.side_effect = [first, second, image_response()]
            store = GitHubAttachmentStore(Path(directory), session, 1024, 15)

            attachment = store.collect(12, "issue", f"![x]({ASSET})")[0]

            self.assertIsNotNone(attachment.path)
            self.assertNotIn("headers", session.get.call_args_list[0].kwargs)
            self.assertNotIn("headers", session.get.call_args_list[1].kwargs)
            self.assertEqual(target, session.get.call_args_list[2].args[0])
            self.assertIsNone(
                session.get.call_args_list[2].kwargs["headers"]["Authorization"]
            )

    def test_http_status_log_contains_safe_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            target = (
                "https://github-production-user-asset-6210df.s3.amazonaws.com/"
                "290238612/example.png?X-Amz-Signature=secret"
            )
            redirect = Mock(status_code=302, headers={"Location": target})
            denied = Mock(
                status_code=400,
                headers={"Content-Type": "application/xml; charset=utf-8"},
            )
            denied.raise_for_status.side_effect = requests.HTTPError(
                "signed query secret", response=denied
            )
            session = Mock(spec=requests.Session)
            session.get.side_effect = [redirect, denied]
            store = GitHubAttachmentStore(Path(directory), session, 1024, 15)

            with self.assertLogs("automation.attachments", level="WARNING") as logs:
                attachment = store.collect(12, "issue", f"![x]({ASSET})")[0]

            message = "\n".join(logs.output)
            self.assertIsNone(attachment.path)
            self.assertIn("stage=http_status", message)
            self.assertIn("status_code=400", message)
            self.assertIn("content_type=application/xml", message)
            self.assertIn(
                "host=github-production-user-asset-6210df.s3.amazonaws.com",
                message,
            )
            self.assertNotIn("X-Amz-Signature", message)
            self.assertNotIn("secret-token", message)
            self.assertNotIn("signed query secret", message)

    def test_rejects_jpg_extension_with_png_body_and_text_plain(self):
        with tempfile.TemporaryDirectory() as directory:
            target = (
                "https://github-production-user-asset-6210df.s3.amazonaws.com/"
                "290238612/example.jpg?X-Amz-Signature=signed"
            )
            for response in (
                image_response(PNG, "image/png"),
                image_response(b"plain error", "text/plain"),
            ):
                with self.subTest(content_type=response.headers["Content-Type"]):
                    redirect = Mock(status_code=302, headers={"Location": target})
                    session = Mock(spec=requests.Session)
                    session.get.side_effect = [redirect, response]
                    store = GitHubAttachmentStore(Path(directory), session, 1024, 15)

                    attachment = store.collect(12, "issue", f"![x]({ASSET})")[0]

                    self.assertIsNone(attachment.path)

    def test_rejects_content_length_above_ten_mibibytes(self):
        with tempfile.TemporaryDirectory() as directory:
            response = image_response()
            response.headers["Content-Length"] = str(10 * 1024 * 1024 + 1)
            session = Mock(spec=requests.Session)
            session.get.return_value = response
            store = GitHubAttachmentStore(
                Path(directory), session, 10 * 1024 * 1024, 15
            )

            attachment = store.collect(12, "issue", f"![x]({ASSET})")[0]

            self.assertIsNone(attachment.path)
            self.assertIn("size:", attachment.error)


if __name__ == "__main__":
    unittest.main()
