# bot/playback.py
import asyncio
import logging
from typing import Dict, Any

from bot.audio_io import AudioOutput

log = logging.getLogger(__name__)

class PlaybackManager:
    """
    A high-level manager for audio playback that coordinates with the audio output device
    and handles barge-in events through a shared asyncio.Event.
    """
    def __init__(self, config: Dict[str, Any], audio_out: AudioOutput):
        self.config = config
        self.audio_out = audio_out
        self._is_playing = False
        self.stop_event = asyncio.Event()
        self._playback_task: asyncio.Task = None

    @property
    def is_playing(self) -> bool:
        """Returns True if audio is currently playing."""
        return self._is_playing

    async def play_audio(self, audio_bytes: bytes, content_type: str = "wav"):
        """
        Plays audio bytes. This method manages the playback lifecycle, including interruption.
        It starts the playback in a background task.
        """
        if self._is_playing:
            log.warning("Playback requested while another playback is already in progress. Ignoring.")
            return

        if content_type != "wav":
            log.error(f"Unsupported audio content type for playback: {content_type}")
            return

        self._is_playing = True
        self.stop_event.clear()

        log.info(f"PlaybackManager: Starting to play {len(audio_bytes)} bytes of audio.")

        async def playback_task_wrapper():
            try:
                await self.audio_out.play_wav_bytes(audio_bytes, self.stop_event)
            except Exception as e:
                log.error(f"Audio playback task failed: {e}", exc_info=True)
            finally:
                self._is_playing = False
                log.info("PlaybackManager: Playback task finished.")

        self._playback_task = asyncio.create_task(playback_task_wrapper())
        await self._playback_task # Wait for the playback to complete or be interrupted

    def interrupt(self):
        """
        Triggers an interruption of the current playback.
        This is the primary method for enabling barge-in. It is safe to call from any thread.
        """
        if self._is_playing:
            log.info("PlaybackManager: Interrupting playback (barge-in).")
            # This is thread-safe
            self.audio_out.loop.call_soon_threadsafe(self.stop_event.set)
        else:
            log.debug("PlaybackManager: Interrupt called but nothing is playing.")

    async def wait_for_completion(self):
        """
        Waits for the current playback task to complete, if one exists.
        """
        if self._playback_task and not self._playback_task.done():
            log.debug("Waiting for playback to complete...")
            await self._playback_task
            log.debug("Playback completed.")

# Note: The original request mentioned helper functions for gain normalization
# and MP3-to-WAV conversion. This functionality has been integrated directly
# into `bot.audio_io.AudioOutput` and `bot.ai_client.AIClient` respectively,
# as it's more contextually appropriate there.
#
# - Gain is applied just before playback in `AudioOutput.play_wav_bytes`.
# - MP3 decoding is handled after TTS generation in `AIClient._tts_openai`.
#
# This keeps the PlaybackManager focused on its core responsibility:
# managing the lifecycle (play, stop, interrupt) of a playback session.
