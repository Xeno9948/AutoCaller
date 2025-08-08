# bot/audio_io.py
import asyncio
import logging
import sounddevice as sd
import numpy as np
from typing import Dict, Any, Optional
import soundfile as sf
import io

log = logging.getLogger(__name__)

class AudioInput:
    """
    Handles capturing audio from an input device and putting it into an asyncio queue.
    """
    def __init__(self, config: Dict[str, Any], loop: asyncio.AbstractEventLoop):
        self.config = config.get("audio", {})
        self.loop = loop
        self.queue = asyncio.Queue(maxsize=50)  # Max 50 chunks to prevent memory overflow
        self.stream: Optional[sd.InputStream] = None

        self.device = self.config.get("input_device")
        self.sample_rate = self.config.get("sample_rate", 16000)
        self.channels = self.config.get("channels", 1)
        # VAD requires 16-bit PCM, so we'll use int16
        self.dtype = 'int16'

        # Frame size for VAD is typically 10, 20, or 30 ms
        frame_ms = config.get("vad", {}).get("frame_ms", 20)
        self.block_size = int(self.sample_rate * (frame_ms / 1000.0))

        log.info(f"AudioInput initialized. Block size set to {self.block_size} frames for {frame_ms}ms duration.")

    def _callback(self, indata: np.ndarray, frames: int, time, status: sd.CallbackFlags):
        """This is called from a separate thread for each audio block."""
        if status:
            log.warning(f"Audio input status: {status}")

        try:
            # Convert numpy array to raw bytes and put it in the queue
            self.loop.call_soon_threadsafe(self.queue.put_nowait, indata.tobytes())
        except asyncio.QueueFull:
            log.warning("Audio input queue is full. Dropping frame.")

    def start(self):
        log.info(f"Starting audio input stream on device '{self.device}'...")
        log.debug(f"  - Sample Rate: {self.sample_rate} Hz, Channels: {self.channels}, DType: {self.dtype}")
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                device=self.device,
                channels=self.channels,
                dtype=self.dtype,
                callback=self._callback
            )
            self.stream.start()
            log.info("Audio input stream started successfully.")
        except Exception as e:
            log.error(f"Failed to open audio input stream on device '{self.device}': {e}", exc_info=True)
            log.error("Use 'python scripts/list_audio_devices.py' to see available devices and check your config.yaml.")
            raise

    def stop(self):
        if self.stream:
            log.info("Stopping audio input stream...")
            self.stream.stop()
            self.stream.close()
            self.stream = None
            log.info("Audio input stream stopped.")
            # Clear the queue
            while not self.queue.empty():
                self.queue.get_nowait()
            log.debug("Audio input queue cleared.")

class AudioOutput:
    """
    Handles playing audio to an output device. Supports interruption for barge-in.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("audio", {})
        self.device = self.config.get("output_device")
        self.sample_rate = self.config.get("sample_rate", 16000)
        self.channels = self.config.get("channels", 1)
        self.dtype = 'float32' # Sounddevice works well with float32 for output
        log.info("AudioOutput initialized.")

    async def play_wav_bytes(self, wav_bytes: bytes, stop_event: asyncio.Event):
        """
        Plays WAV audio bytes. This call is async and returns when playback is finished or interrupted.
        """
        log.info(f"Starting playback of {len(wav_bytes)} bytes of WAV data on device '{self.device}'.")

        try:
            data, samplerate = sf.read(io.BytesIO(wav_bytes), dtype=self.dtype)

            if samplerate != self.sample_rate:
                log.warning(f"Audio data sample rate ({samplerate}) differs from output device rate ({self.sample_rate}). Playback quality may be affected.")

            # Apply gain adjustment
            gain_db = self.config.get("output_gain_db", 0)
            if gain_db != 0:
                log.debug(f"Applying output gain of {gain_db} dB.")
                gain_factor = 10 ** (gain_db / 20.0)
                data *= gain_factor
                np.clip(data, -1.0, 1.0, out=data)

            current_frame = 0

            def callback(outdata: np.ndarray, frames: int, time, status: sd.CallbackFlags):
                nonlocal current_frame
                if status:
                    log.warning(f"Playback status: {status}")

                if stop_event.is_set():
                    log.info("Playback interrupted by stop event (barge-in).")
                    outdata.fill(0)
                    raise sd.CallbackStop

                remaining_frames = len(data) - current_frame
                chunk_size = min(remaining_frames, frames)

                # Ensure outdata has the same number of channels as data
                out_channels = outdata.shape[1]
                data_channels = data.shape[1] if data.ndim > 1 else 1

                if out_channels == data_channels:
                    outdata[:chunk_size] = data[current_frame:current_frame + chunk_size]
                elif out_channels > 1 and data_channels == 1: # mono to stereo
                    outdata[:chunk_size] = data[current_frame:current_frame + chunk_size].reshape(-1, 1)
                else: # other cases not handled, just fill with zeros
                     outdata.fill(0)

                outdata[chunk_size:] = 0
                if chunk_size < frames:
                    raise sd.CallbackStop
                current_frame += chunk_size

            with sd.OutputStream(
                samplerate=self.sample_rate,
                device=self.device,
                channels=self.channels,
                dtype=self.dtype,
                callback=callback
            ) as stream:
                while stream.active and not stop_event.is_set():
                    await asyncio.sleep(0.02) # check for stop event every 20ms

                if stop_event.is_set() and stream.active:
                    stream.stop()

            log.info("Playback finished or was interrupted.")

        except Exception as e:
            log.error(f"Failed to play audio on device '{self.device}': {e}", exc_info=True)
            raise

    def stop_all_playback(self):
        """
        Force-stops any and all sounddevice playback.
        """
        log.info("Stopping all active playback streams.")
        sd.stop()
