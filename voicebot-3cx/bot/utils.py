# bot/utils.py
import numpy as np
import io
import soundfile as sf
import time
import os
import logging
from typing import Union

log = logging.getLogger(__name__)

# --- Audio Utilities ---

def to_wav_bytes(audio_data: np.ndarray, sample_rate: int) -> bytes:
    """
    Encodes a NumPy array of audio data into WAV format as an in-memory byte buffer.
    The output is 16-bit PCM WAV, which is standard for many STT services.
    """
    log.debug(f"Encoding {len(audio_data)} float samples at {sample_rate}Hz to WAV bytes.")
    buffer = io.BytesIO()
    sf.write(buffer, audio_data, sample_rate, format='WAV', subtype='PCM_16')
    buffer.seek(0)
    wav_bytes = buffer.read()
    log.debug(f"WAV encoding complete. Output size: {len(wav_bytes)} bytes.")
    return wav_bytes

def calculate_rms(audio_chunk: np.ndarray) -> float:
    """
    Calculates the Root Mean Square (RMS) of an audio chunk.
    This is a measure of the power of the audio signal.
    Assumes audio_chunk is a numpy array of floats between -1.0 and 1.0.
    """
    if audio_chunk.size == 0:
        return 0.0
    rms = np.sqrt(np.mean(np.square(audio_chunk)))
    return float(rms)

def pcm_to_float(pcm_data: bytes, dtype=np.int16) -> np.ndarray:
    """
    Converts raw PCM audio data (bytes) to a NumPy array of floats in the range [-1.0, 1.0].
    """
    # Create a numpy array from the raw bytes
    data = np.frombuffer(pcm_data, dtype=dtype)
    # Normalize to float
    return data.astype(np.float32) / np.iinfo(dtype).max

# --- Time Utilities ---

class Timer:
    """
    A simple context manager for timing blocks of code and logging the duration.
    Example:
        with Timer("data_processing") as t:
            process_data()
        print(f"Processing took {t.elapsed_ms:.2f} ms")
    """
    def __init__(self, name: str, logger: logging.Logger = None):
        self.name = name
        self.logger = logger or logging.getLogger(__name__)
        self.start_time = None
        self.end_time = None
        self.elapsed_ms = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        self.logger.debug(f"Timer '{self.name}' started.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        self.elapsed_ms = (self.end_time - self.start_time) * 1000
        self.logger.debug(f"Timer '{self.name}' finished in {self.elapsed_ms:.2f} ms.")

    @staticmethod
    def get_timestamp_ms() -> int:
        """Returns the current time as milliseconds since the epoch."""
        return int(time.time() * 1000)

# --- Path Utilities ---

def safe_create_dir(path: Union[str, os.PathLike]):
    """
    Safely creates a directory if it does not already exist.
    """
    try:
        os.makedirs(path, exist_ok=True)
        log.debug(f"Directory '{path}' exists or was created.")
    except OSError as e:
        log.error(f"Failed to create directory '{path}': {e}", exc_info=True)
        raise

def resolve_path(path: str) -> str:
    """
    Resolves a path, expanding user (`~`) and environment variables.
    """
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
