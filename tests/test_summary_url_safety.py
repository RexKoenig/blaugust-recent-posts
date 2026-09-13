from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from scripts import build_summary_prototype as summary


class PublicUrlValidationTests(unittest.TestCase):
    def test_rejects_non_http_scheme_without_dns(self) -> None:
        with patch.object(summary.socket, "getaddrinfo") as resolver:
            with self.assertRaisesRegex(ValueError, "unsupported URL scheme"):
                summary.validate_public_url("file:///etc/passwd")
            resolver.assert_not_called()

    def test_rejects_embedded_credentials_without_dns(self) -> None:
        with patch.object(summary.socket, "getaddrinfo") as resolver:
            with self.assertRaisesRegex(ValueError, "credentials embedded"):
                summary.validate_public_url("https://user:password@example.com/post")
            resolver.assert_not_called()

    def test_rejects_literal_loopback_without_dns(self) -> None:
        with patch.object(summary.socket, "getaddrinfo") as resolver:
            with self.assertRaisesRegex(ValueError, "non-public address"):
                summary.validate_public_url("http://127.0.0.1/private")
            resolver.assert_not_called()

    def test_rejects_literal_ipv6_loopback_without_dns(self) -> None:
        with patch.object(summary.socket, "getaddrinfo") as resolver:
            with self.assertRaisesRegex(ValueError, "non-public address"):
                summary.validate_public_url("http://[::1]/private")
            resolver.assert_not_called()

    def test_allows_public_literal_ip(self) -> None:
        with patch.object(summary.socket, "getaddrinfo") as resolver:
            validated = summary.validate_public_url("https://8.8.8.8/example#fragment")
            self.assertEqual(validated, "https://8.8.8.8/example")
            resolver.assert_not_called()

    def test_allows_hostname_when_all_dns_answers_are_public(self) -> None:
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0)),
        ]
        with patch.object(summary.socket, "getaddrinfo", return_value=answers):
            validated = summary.validate_public_url("https://example.com/post#comments")
        self.assertEqual(validated, "https://example.com/post")

    def test_rejects_hostname_with_mixed_public_private_dns(self) -> None:
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.7", 443)),
        ]
        with patch.object(summary.socket, "getaddrinfo", return_value=answers):
            with self.assertRaisesRegex(ValueError, "non-public address"):
                summary.validate_public_url("https://example.com/post")

    def test_rejects_numeric_hostname_that_resolves_to_loopback(self) -> None:
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 80)),
        ]
        with patch.object(summary.socket, "getaddrinfo", return_value=answers):
            with self.assertRaisesRegex(ValueError, "non-public address"):
                summary.validate_public_url("http://2130706433/private")


if __name__ == "__main__":
    unittest.main()