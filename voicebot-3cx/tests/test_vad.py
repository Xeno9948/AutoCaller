# tests/test_vad.py
import unittest
import numpy as np
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.vad import VadSegmenter

def generate_audio(is_speech: bool, duration_ms: int, sample_rate: int) -> bytes:
    """
    Generates a raw audio frame of silence or fake speech (random noise).
    Audio is 16-bit PCM, as required by webrtcvad.
    """
    num_samples = int(sample_rate * duration_ms / 1000)
    dtype = np.int16

    if is_speech:
        # Simple random noise to simulate speech
        frame = np.random.randint(-5000, 5000, size=num_samples, dtype=dtype)
    else:
        # Zeros for silence
        frame = np.zeros(num_samples, dtype=dtype)

    return frame.tobytes()

class TestVadSegmenter(unittest.TestCase):
    """
    Unit tests for the VAD segmenter logic.
    """

    def setUp(self):
        """Set up a VAD segmenter with test-friendly settings."""
        self.config = {
            "audio": {"sample_rate": 16000},
            "vad": {
                "aggressiveness": 1,
                "frame_ms": 20,       # Each frame is 20ms
                "min_speech_ms": 80,  # Must have 4+ speech frames
                "max_silence_ms": 100 # End utterance after 5 silent frames
            }
        }
        self.segmenter = VadSegmenter(self.config)
        self.sample_rate = self.config["audio"]["sample_rate"]
        self.frame_bytes = self.segmenter.frame_bytes

    def test_pure_silence(self):
        """Tests that no utterance is detected in a stream of pure silence."""
        silence = generate_audio(is_speech=False, duration_ms=500, sample_rate=self.sample_rate)
        utterances = list(self.segmenter.segment(silence))
        self.assertEqual(len(utterances), 0, "Should not detect any utterances in silence")
        self.assertIsNone(self.segmenter.flush(), "Flushing silence should yield nothing")

    def test_continuous_speech_then_flush(self):
        """Tests that continuous speech is emitted only when flushed."""
        speech = generate_audio(is_speech=True, duration_ms=500, sample_rate=self.sample_rate)
        utterances = list(self.segmenter.segment(speech))
        # No utterance should be detected yet because there's no trailing silence
        self.assertEqual(len(utterances), 0)

        # Flushing should return the buffered speech
        final_utterance = self.segmenter.flush()
        self.assertIsNotNone(final_utterance)

        expected_bytes = len(speech)
        # The segmenter works in frames, so the length should be a multiple of frame_bytes
        self.assertAlmostEqual(len(final_utterance), expected_bytes, delta=self.frame_bytes)

    def test_simple_utterance_detection(self):
        """Tests detection of a single, clean utterance surrounded by silence."""
        # Composition: 40ms silence + 200ms speech + 120ms silence
        # 200ms speech > min_speech_ms (80ms) -> should trigger start
        # 120ms silence > max_silence_ms (100ms) -> should trigger end
        silence1 = generate_audio(False, 40, self.sample_rate)
        speech = generate_audio(True, 200, self.sample_rate)
        silence2 = generate_audio(False, 120, self.sample_rate)

        full_audio = silence1 + speech + silence2

        utterances = list(self.segmenter.segment(full_audio))

        self.assertEqual(len(utterances), 1, "Should detect exactly one utterance")

        # The detected utterance should contain the speech part.
        # The VAD may buffer a few initial speech frames, so the result can be slightly different.
        expected_len_bytes = len(speech)
        self.assertAlmostEqual(len(utterances[0]), expected_len_bytes, delta=self.frame_bytes * self.segmenter.min_speech_frames)

    def test_speech_too_short_is_ignored(self):
        """Tests that a burst of speech shorter than min_speech_ms is ignored."""
        # 60ms speech is less than our 80ms minimum
        short_speech = generate_audio(True, 60, self.sample_rate)
        silence = generate_audio(False, 120, self.sample_rate)

        full_audio = short_speech + silence
        utterances = list(self.segmenter.segment(full_audio))
        self.assertEqual(len(utterances), 0, "Should not detect an utterance shorter than min_speech_ms")

    def test_multiple_utterances(self):
        """Tests that two separate utterances are detected correctly."""
        speech1 = generate_audio(True, 200, self.sample_rate)
        long_silence = generate_audio(False, 120, self.sample_rate) # Triggers end of first utterance
        speech2 = generate_audio(True, 300, self.sample_rate)

        audio = speech1 + long_silence + speech2

        utterances = list(self.segmenter.segment(audio))
        self.assertEqual(len(utterances), 1, "Should detect the first utterance")

        # Now add final silence to trigger the end of the second utterance
        final_silence = generate_audio(False, 120, self.sample_rate)
        utterances += list(self.segmenter.segment(final_silence))

        self.assertEqual(len(utterances), 2, "Should detect two utterances in total")
        self.assertAlmostEqual(len(utterances[0]), len(speech1), delta=self.frame_bytes)
        self.assertAlmostEqual(len(utterances[1]), len(speech2), delta=self.frame_bytes)

if __name__ == '__main__':
    unittest.main(verbosity=2)
