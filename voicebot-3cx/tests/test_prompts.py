# tests/test_prompts.py
import unittest
import sys
import os

# Add the project root directory to the Python path
# This allows us to import modules from the 'bot' package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.prompts import get_system_prompt, PERSONA_PROMPTS

class TestPrompts(unittest.TestCase):
    """
    Unit tests for the prompt generation logic in bot/prompts.py.
    """

    def test_get_generic_prompt(self):
        """Tests that a generic prompt is generated correctly with default settings."""
        config = {
            "persona": {
                "industry": "generic",
                "max_reply_sentences": 2
            }
        }
        prompt_messages = get_system_prompt(config)

        self.assertEqual(len(prompt_messages), 1, "Should return a single message object")
        self.assertEqual(prompt_messages[0]["role"], "system", "Message role should be 'system'")

        content = prompt_messages[0]["content"]
        self.assertIn(PERSONA_PROMPTS["generic"]["prompt"], content, "Should contain the base generic prompt")
        self.assertIn("under 2 sentences", content, "Should respect the max_reply_sentences config")
        self.assertIn("speak to a human", content, "Should include safety rail about human handoff")
        self.assertIn("medical, legal, or financial advice", content, "Should include safety rail about advice")

    def test_get_specific_persona_prompt(self):
        """Tests that a specific persona prompt (e.g., ecommerce) is generated correctly."""
        config = {
            "persona": {
                "industry": "ecommerce",
                "max_reply_sentences": 3
            }
        }
        prompt_messages = get_system_prompt(config)

        self.assertEqual(len(prompt_messages), 1)
        self.assertEqual(prompt_messages[0]["role"], "system")

        content = prompt_messages[0]["content"]
        self.assertIn(PERSONA_PROMPTS["ecommerce"]["prompt"], content, "Should contain the ecommerce base prompt")
        self.assertIn("under 3 sentences", content, "Should use the specified max_reply_sentences")

    def test_fallback_to_generic_persona(self):
        """Tests that the system falls back to the generic prompt if the persona is invalid."""
        config = {
            "persona": {
                "industry": "non_existent_persona",
                "max_reply_sentences": 2
            }
        }
        # This should log a warning, but we'll just test the output
        prompt_messages = get_system_prompt(config)

        self.assertEqual(len(prompt_messages), 1)
        content = prompt_messages[0]["content"]
        self.assertIn(PERSONA_PROMPTS["generic"]["prompt"], content, "Should fall back to the generic prompt")

    def test_missing_persona_config(self):
        """Tests that the system handles a missing persona configuration gracefully by using defaults."""
        config = {}  # No 'persona' key at all
        prompt_messages = get_system_prompt(config)

        self.assertEqual(len(prompt_messages), 1)
        content = prompt_messages[0]["content"]
        self.assertIn(PERSONA_PROMPTS["generic"]["prompt"], content, "Should default to generic prompt")
        # Check that it uses the default sentence limit (2)
        self.assertIn("under 2 sentences", content, "Should use the default sentence limit")

if __name__ == '__main__':
    # This allows running the tests directly from the command line
    unittest.main(verbosity=2)
