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
            patch.object(main, "load_seen", return_value={}), \
            patch.object(main, "collect", return_value=[raw_item]), \
            patch.object(main.digest_mod, "build_markdown", return_value="# digest"), \
            patch.object(main.site_builder, "build"), \
            patch.object(main.mailer, "send", side_effect=RuntimeError("smtp auth failed")), \
            patch.object(main, "save_seen", side_effect=lambda seen: saved_seen.append(set(seen))), \
            patch.dict(os.environ, {"SMTP_USER": "sender@example.com"}, clear=False):
            main.main()

        self.assertEqual(saved_seen, [{"item-1"}])

    def test_force_reprocess_includes_seen_items_for_manual_rerun(self):
        raw_item = {
            "id": "item-1",
            "title": "Policy update",
            "url": "https://example.com/policy",
            "source": "Example",
            "summary": "A short policy update.",
            "section": "宏观/政策",
        }

        with patch.object(main, "load_config", return_value={"digest": {}, "ai": {"enabled": False}}), \
            patch.object(main, "load_seen", return_value={"item-1": None}), \
            patch.object(main, "collect", return_value=[raw_item]), \
            patch.object(main.digest_mod, "build_markdown", return_value="# digest") as build_markdown, \
            patch.object(main.site_builder, "build") as build_site, \
            patch.object(main, "save_seen"), \
            patch.dict(os.environ, {"FORCE_REPROCESS": "1"}, clear=True):
            main.main()

        build_markdown.assert_called_once()
        build_site.assert_called_once()
