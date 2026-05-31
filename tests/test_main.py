import os
import unittest
from unittest.mock import patch

import main


class MainWorkflowTests(unittest.TestCase):
    def test_smtp_failure_does_not_block_state_persistence(self):
        raw_item = {
            "id": "item-1",
            "title": "AI infrastructure update",
            "url": "https://example.com/ai-infra",
            "source": "Example",
            "summary": "A short AI update.",
        }

        saved_seen = []

        with patch.object(main, "load_config", return_value={"digest": {}, "ai": {"enabled": False}}), \
            patch.object(main, "load_seen", return_value=set()), \
            patch.object(main, "collect", return_value=[raw_item]), \
            patch.object(main.digest_mod, "build_markdown", return_value="# digest"), \
            patch.object(main.site_builder, "build"), \
            patch.object(main.mailer, "send", side_effect=RuntimeError("smtp auth failed")), \
            patch.object(main, "save_seen", side_effect=lambda seen: saved_seen.append(set(seen))), \
            patch.dict(os.environ, {"SMTP_USER": "sender@example.com"}, clear=False):
            main.main()

        self.assertEqual(saved_seen, [{"item-1"}])
