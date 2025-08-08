# bot/vad.py
import logging
import webrtcvad
from typing import Dict, Any, Optional, Generator

log = logging.getLogger(__name__)

class VadSegmenter:
    """
    Uses webrtcvad to segment a stream of raw audio bytes into utterances.
    This class processes audio frames and yields complete speech segments.
    """
    def __init__(self, config: Dict[str, Any]):
        vad_config = config.get("vad", {})
        audio_config = config.get("audio", {})

        self.aggressiveness = vad_config.get("aggressiveness", 2)
        self.frame_ms = vad_config.get("frame_ms", 20)
        self.min_speech_ms = vad_config.get("min_speech_ms", 300)
        self.max_silence_ms = vad_config.get("max_silence_ms", 500)
        self.sample_rate = audio_config.get("sample_rate", 16000)

        if self.frame_ms not in [10, 20, 30]:
            raise ValueError("VAD frame_ms must be 10, 20, or 30.")

        self.vad = webrtcvad.Vad(self.aggressiveness)

        # webrtcvad requires 16-bit PCM audio. 1 sample = 2 bytes.
        self.frame_size = (self.sample_rate * self.frame_ms // 1000)
        self.frame_bytes = self.frame_size * 2

        # Number of frames to meet time thresholds
        self.min_speech_frames = self.min_speech_ms // self.frame_ms
        self.max_silence_frames = self.max_silence_ms // self.frame_ms

        self.reset()
        log.info("VAD Segmenter initialized.")
        log.debug(f"VAD params: aggressiveness={self.aggressiveness}, frame_ms={self.frame_ms}, "
                  f"min_speech_frames={self.min_speech_frames}, max_silence_frames={self.max_silence_frames}")

    def reset(self):
        """Resets the internal state of the segmenter."""
        log.debug("Resetting VAD state.")
        self.buffer = b''
        self.speech_frames_count = 0
        self.silence_frames_count = 0
        self.is_speaking = False
        self.speech_buffer = []

    def segment(self, audio_chunk: bytes) -> Generator[bytes, None, None]:
        """
        Processes a chunk of audio data and yields full utterances as bytes when detected.
        This is a generator function.
        """
        self.buffer += audio_chunk

        while len(self.buffer) >= self.frame_bytes:
            frame = self.buffer[:self.frame_bytes]
            self.buffer = self.buffer[self.frame_bytes:]

            try:
                is_speech = self.vad.is_speech(frame, self.sample_rate)
            except Exception as e:
                log.warning(f"webrtcvad failed to process a frame: {e}")
                continue

            if self.is_speaking:
                self.speech_buffer.append(frame)
                if is_speech:
                    self.silence_frames_count = 0  # Reset silence counter on speech
                else:
                    self.silence_frames_count += 1
                    if self.silence_frames_count >= self.max_silence_frames:
                        log.debug(f"End of speech detected after {self.silence_frames_count * self.frame_ms}ms of silence.")
                        utterance = self._finalize_utterance()
                        if utterance:
                            yield utterance
                        self.reset()
            else:  # Not currently speaking
                if is_speech:
                    self.speech_frames_count += 1
                    self.speech_buffer.append(frame) # Start buffering immediately
                    if self.speech_frames_count >= self.min_speech_frames:
                        log.debug(f"Start of speech detected after {self.speech_frames_count * self.frame_ms}ms of speech.")
                        self.is_speaking = True
                        self.silence_frames_count = 0
                else:
                    # Still silence, reset speech counter and clear buffer
                    self.speech_frames_count = 0
                    self.speech_buffer.clear()

    def _finalize_utterance(self) -> Optional[bytes]:
        """
        Combines the buffered speech frames into a single byte string.
        Returns None if the utterance is too short.
        """
        if not self.speech_buffer:
            return None

        # We check the total length of the speech buffer against the minimum speech time
        # This is a secondary check to ensure we don't return tiny audio snippets
        total_frames = len(self.speech_buffer)
        if total_frames < self.min_speech_frames:
            log.debug(f"Discarding utterance, too short: {total_frames} frames < {self.min_speech_frames} frames.")
            return None

        utterance_bytes = b''.join(self.speech_buffer)
        duration_ms = total_frames * self.frame_ms
        log.info(f"Finalized utterance of {len(utterance_bytes)} bytes ({duration_ms}ms).")
        return utterance_bytes

    def flush(self) -> Optional[bytes]:
        """
        Flushes any remaining audio in the buffer as a final utterance.
        Useful for the end of a call.
        """
        if self.is_speaking and self.speech_buffer:
            log.info("Flushing remaining VAD buffer at end of stream.")
            utterance = self._finalize_utterance()
            self.reset()
            if utterance:
                return utterance
        return None
