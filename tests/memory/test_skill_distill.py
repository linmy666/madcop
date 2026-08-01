"""Tests for skill_distill auto-distill heuristic (Sprint 1)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add the project root so we can import the module under test
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from madcop.memory.skill_distill import (
    _is_valuable_skill,
    _extract_topic_from_response,
    _looks_like_teaching_request,
    auto_distill_if_valuable,
    force_distill_skill,
)


class TestIsValuableSkill(unittest.TestCase):
    """Heuristic for whether an exchange is worth saving as a skill."""

    def test_empty_inputs_return_none(self):
        self.assertIsNone(_is_valuable_skill("", ""))
        self.assertIsNone(_is_valuable_skill("hi", ""))
        self.assertIsNone(_is_valuable_skill("", "x" * 500))

    def test_short_response_rejected(self):
        long_q = "how do I deploy a python project"
        self.assertIsNone(_is_valuable_skill(long_q, "short answer"))

    def test_long_response_without_markers_rejected(self):
        q = "how do I deploy a python project"
        body = "x" * 500  # long but no code block, no list, no heading
        self.assertIsNone(_is_valuable_skill(q, body))

    def test_long_response_with_code_block_accepted(self):
        q = "how do I deploy a python project"
        body = "Use this command:\n```bash\nkubectl apply -f deployment.yaml\n```\n" + "x" * 400
        topic = _is_valuable_skill(q, body)
        self.assertIsNotNone(topic)
        self.assertIn("deploy", topic.lower())

    def test_long_response_with_list_accepted(self):
        q = "how do I configure nginx"
        body = "Steps:\n- Step 1\n- Step 2\n- Step 3\n" + "y" * 400
        topic = _is_valuable_skill(q, body)
        self.assertIsNotNone(topic)

    def test_long_response_with_heading_accepted(self):
        # The heading must be on its own line followed by another line
        # for the `\n## ` marker pattern to match.
        q = "how do I write a custom event emitter"
        body = "\n## Overview\nUse a simple class.\n" + ("z" * 50 + "\n") * 8
        topic = _is_valuable_skill(q, body)
        self.assertIsNotNone(topic)


class TestExtractTopicFromResponse(unittest.TestCase):

    def test_simple_topic(self):
        self.assertEqual(
            _extract_topic_from_response("how to deploy a python project", ""),
            "how to deploy a python project",
        )

    def test_chinese_topic(self):
        self.assertEqual(
            _extract_topic_from_response("怎么部署一个 python 项目", ""),
            "怎么部署一个 python 项目",
        )

    def test_short_query_skipped(self):
        self.assertIsNone(_extract_topic_from_response("hi", ""))

    def test_social_question_excluded(self):
        self.assertIsNone(
            _extract_topic_from_response("你好", "some long response body")
        )

    def test_long_query_with_social_word_kept(self):
        topic = _extract_topic_from_response(
            "hi how do I configure nginx reverse proxy properly", ""
        )
        self.assertEqual(topic, "hi how do I configure nginx reverse proxy properly")


class TestLooksLikeTeachingRequest(unittest.TestCase):
    """Original 'teach me how to X' pattern detector still works."""

    def test_teach_me_zh(self):
        self.assertEqual(_looks_like_teaching_request("教我怎么部署 kubernetes"), "部署 kubernetes")

    def test_teach_me_en(self):
        self.assertEqual(_looks_like_teaching_request("teach me how to use docker"), "use docker")

    def test_no_match_returns_none(self):
        self.assertIsNone(_looks_like_teaching_request("hello world"))


class TestAutoDistillIfValuable(unittest.TestCase):

    def test_returns_none_for_thin_exchange(self):
        self.assertIsNone(
            auto_distill_if_valuable("how to deploy", "short")
        )

    def test_returns_skill_name_for_valuable_exchange(self):
        q = "how to deploy a kubernetes cluster"
        body = (
            "Run the following command to deploy:\n"
            "```bash\nkubectl apply -f deployment.yaml\n```\n"
            + "x" * 500
        )
        result = auto_distill_if_valuable(q, body)
        self.assertIsNotNone(result)
        # Skill name should be slugified from the topic
        self.assertIn("deploy", result.lower())

    def test_writes_skill_md_file(self):
        """End-to-end: auto_distill actually creates a SKILL.md file."""
        import shutil
        from madcop.memory.skill_distill import USER_SKILLS_DIR
        if USER_SKILLS_DIR.exists():
            shutil.rmtree(USER_SKILLS_DIR)
        # Use a code block so the valuable-skill heuristic accepts.
        q = "how to write a simple python script that prints world"
        body = (
            "## Steps\n"
            "- Step 1: import sys\n"
            "- Step 2: print('output')\n"
            "```python\nprint('output')\n```\n"
            + "more content to exceed 400 chars " * 10
        )
        result = auto_distill_if_valuable(q, body)
        self.assertIsNotNone(result)
        skill_file = USER_SKILLS_DIR / f"{result}.md"
        self.assertTrue(skill_file.exists())
        content = skill_file.read_text()
        self.assertIn('print(' + chr(39) + 'output' + chr(39) + ')', content)
        shutil.rmtree(USER_SKILLS_DIR)


if __name__ == "__main__":
    unittest.main()
