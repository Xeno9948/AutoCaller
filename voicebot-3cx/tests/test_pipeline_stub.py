# tests/test_pipeline_stub.py
import unittest
import asyncio
import sys
import os
import time
import numpy as np
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.pipeline import BotPipeline
from bot.audio_io import AudioInput, AudioOutput
from bot.vad import VadSegmenter
from bot.ai_client import AIClient
from bot.playback import PlaybackManager
from bot.status_server import StatusServer

# --- Helper to generate audio ---
def generate_audio(is_speech: bool, duration_ms: int, sample_rate: int) -> bytes:
    num_samples = int(sample_rate * duration_ms / 1000)
    dtype = np.int16
    frame = np.random.randint(-1000, 1000, size=num_samples, dtype=dtype) if is_speech else np.zeros(num_samples, dtype=dtype)
    return frame.tobytes()

# --- Stub/Mock Classes for testing the pipeline ---

class StubAIClient(AIClient):
    """A stub AIClient that returns canned responses without making real API calls."""
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.last_chat_messages: List[Dict[str, str]] = None

    async def transcribe(self, audio_wav_bytes: bytes) -> tuple:
        return "test transcription", 100, {"provider": "stub"}

    async def chat(self, messages: List[Dict[str, str]]) -> tuple:
        self.last_chat_messages = messages
        return "canned response", 200, {"model": "stub_model"}

    async def tts(self, text: str) -> tuple:
        # Generate 1 second of silent WAV audio
        sample_rate = self.config.get("audio", {}).get("sample_rate", 16000)
        audio_data = np.zeros(sample_rate, dtype=np.float32)
        import io, soundfile as sf
        buffer = io.BytesIO()
        sf.write(buffer, audio_data, sample_rate, format='WAV')
        return buffer.getvalue(), 150, {"provider": "stub"}

class StubAudioOutput(AudioOutput):
    """A stub AudioOutput that simulates playback and signals events."""
    def __init__(self, config: Dict[str, Any], loop: asyncio.AbstractEventLoop):
        self.config = config.get("audio", {})
        self.loop = loop
        self.playback_started = asyncio.Event()
        self.playback_stopped = asyncio.Event()
        self.was_interrupted = False

    async def play_wav_bytes(self, wav_bytes: bytes, stop_event: asyncio.Event):
        self.playback_started.set()
        try:
            # Simulate a 1-second playback, but listen for the stop_event
            await asyncio.wait_for(stop_event.wait(), timeout=1.0)
            # If we get here, it means stop_event was set
            self.was_interrupted = True
        except asyncio.TimeoutError:
            # This is the normal case: playback finished without interruption
            self.was_interrupted = False
        finally:
            self.playback_stopped.set()

class TestPipelineBargeIn(unittest.TestCase):

    def setUp(self):
        """Set up the test environment and asyncio loop."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.config = {
            "audio": {"sample_rate": 16000},
            "vad": {"frame_ms": 20, "min_speech_ms": 60, "max_silence_ms": 300},
            "persona": {}, "server": {}
        }

        # Components for the test
        self.audio_in = AudioInput(self.config, self.loop)
        self.audio_out_stub = StubAudioOutput(self.config, self.loop)
        self.ai_client_stub = StubAIClient(self.config)
        self.vad = VadSegmenter(self.config)
        self.playback_manager = PlaybackManager(self.config, self.audio_out_stub)
        self.status_server_stub = StatusServer(self.config)

        self.pipeline = BotPipeline(
            self.config, self.audio_in, self.vad, self.ai_client_stub,
            self.playback_manager, self.status_server_stub
        )

    def tearDown(self):
        """Clean up the asyncio loop."""
        self.loop.close()

    def test_barge_in_interrupts_playback(self):
        """
        Integration test: Verifies that new speech during playback triggers an interruption
        within the required time frame.
        """
        async def test_runner():
            pipeline_task = self.loop.create_task(self.pipeline.run())

            # --- 1. Inject initial user utterance to start a turn ---
            initial_utterance = generate_audio(True, 200, 16000)
            await self.audio_in.queue.put(initial_utterance)
            silence_to_end_utterance = generate_audio(False, 400, 16000)
            await self.audio_in.queue.put(silence_to_end_utterance)

            # --- 2. Wait for playback to start ---
            try:
                await asyncio.wait_for(self.audio_out_stub.playback_started.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self.fail("Playback did not start within the 2s timeout.")

            self.assertTrue(self.playback_manager.is_playing, "PlaybackManager should be in a playing state.")

            # --- 3. Inject barge-in speech while playback is active ---
            start_time = time.perf_counter()
            barge_in_speech = generate_audio(True, 200, 16000)
            await self.audio_in.queue.put(barge_in_speech)

            # --- 4. Assert that playback stops quickly ---
            try:
                await asyncio.wait_for(self.audio_out_stub.playback_stopped.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                self.fail("Playback did not stop within 500ms after barge-in speech was sent.")

            stop_time = time.perf_counter()
            interruption_latency_ms = (stop_time - start_time) * 1000

            # The prompt requires interruption within 300ms. We add a buffer for test overhead.
            self.assertLess(interruption_latency_ms, 350, f"Barge-in interruption took too long ({interruption_latency_ms:.2f}ms)")
            self.assertTrue(self.audio_out_stub.was_interrupted, "The audio output stub should confirm it was interrupted.")
            print(f"\nBarge-in interruption latency test passed: {interruption_latency_ms:.2f} ms")

            # --- Cleanup ---
            pipeline_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pipeline_task

        self.loop.run_until_complete(test_runner())

if __name__ == '__main__':
    unittest.main(verbosity=2)
