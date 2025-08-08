# bot/ai_client.py
import logging
import os
from typing import Dict, Any, Tuple, List, Optional
import io
import asyncio

import openai
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pydub import AudioSegment

from bot.utils import Timer

# --- Guarded imports for optional dependencies ---
try:
    from faster_whisper import WhisperModel
    _faster_whisper_available = True
except ImportError:
    _faster_whisper_available = False

try:
    import pyttsx3
    _pyttsx3_available = True
except ImportError:
    _pyttsx3_available = False

try:
    import torch
    _torch_available = True
except ImportError:
    _torch_available = False


log = logging.getLogger(__name__)

# Define what we consider a transient error for retries
TRANSIENT_ERRORS = (
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.InternalServerError,
)

class AIClient:
    """
    A client to interact with AI services for STT, LLM, and TTS.
    Handles provider selection (OpenAI vs. local) and robust API calls.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config

        if not os.getenv("OPENAI_API_KEY"):
            log.error("OPENAI_API_KEY environment variable not set!")
            raise ValueError("OPENAI_API_KEY is required for OpenAI services.")

        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=0) # We handle retries manually
        log.info("OpenAI client initialized.")

        self.stt_provider = self.config.get("stt", {}).get("provider", "openai")
        self.tts_provider = self.config.get("tts", {}).get("provider", "openai")

        self.local_stt_model: Optional[WhisperModel] = None
        if self.stt_provider == "local":
            self._init_local_stt()

        self.local_tts_engine: Optional[pyttsx3.Engine] = None
        if self.tts_provider == "local":
            self._init_local_tts()

    def _init_local_stt(self):
        if not _faster_whisper_available:
            raise ImportError("STT provider is 'local' but faster-whisper is not installed. Run 'pip install faster-whisper'.")

        model_size, device, compute_type = "base.en", "cpu", "int8"
        if _torch_available and torch.cuda.is_available():
            device, compute_type = "cuda", "float16"
            log.info("CUDA available, using GPU for local STT.")
        else:
            log.info("Using CPU for local STT.")

        log.info(f"Initializing local STT model '{model_size}' on {device}...")
        try:
            self.local_stt_model = WhisperModel(model_size, device=device, compute_type=compute_type)
            log.info("Local STT model loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load local STT model: {e}", exc_info=True)
            raise

    def _init_local_tts(self):
        if not _pyttsx3_available:
            raise ImportError("TTS provider is 'local' but pyttsx3 is not installed. Run 'pip install pyttsx3'.")

        log.info("Initializing local TTS engine (pyttsx3)...")
        try:
            self.local_tts_engine = pyttsx3.init()
            log.info("Local TTS engine initialized.")
        except Exception as e:
            log.error(f"Failed to initialize pyttsx3: {e}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(TRANSIENT_ERRORS))
    async def transcribe(self, audio_wav_bytes: bytes) -> Tuple[str, float, Dict[str, Any]]:
        log.debug(f"Starting transcription with provider: {self.stt_provider}")
        with Timer("transcribe", log) as t:
            if self.stt_provider == "local":
                text, meta = await self._transcribe_local(audio_wav_bytes)
            else:
                text, meta = await self._transcribe_openai(audio_wav_bytes)
        log.info(f"Transcription complete in {t.elapsed_ms:.2f}ms. Text: '{text}'")
        return text, t.elapsed_ms, meta

    async def _transcribe_openai(self, audio_wav_bytes: bytes) -> Tuple[str, Dict]:
        stt_model = self.config.get("openai", {}).get("stt_model", "whisper-1")
        log.debug(f"Transcribing {len(audio_wav_bytes)} bytes with OpenAI model '{stt_model}'")
        audio_file = io.BytesIO(audio_wav_bytes)
        audio_file.name = "input.wav"

        try:
            response = await self.openai_client.audio.transcriptions.create(model=stt_model, file=audio_file, language="en")
            log.debug(f"OpenAI transcription raw response size: {len(str(response))}")
            return response.text, {"provider": "openai"}
        except openai.APIError as e:
            log.error(f"OpenAI API error during transcription: {e.body}", exc_info=True)
            raise

    async def _transcribe_local(self, audio_wav_bytes: bytes) -> Tuple[str, Dict]:
        if not self.local_stt_model: raise RuntimeError("Local STT model not initialized.")
        log.debug(f"Transcribing {len(audio_wav_bytes)} bytes with local model.")

        def do_transcribe():
            audio_file = io.BytesIO(audio_wav_bytes)
            segments, info = self.local_stt_model.transcribe(audio_file, beam_size=5)
            text = " ".join([seg.text for seg in segments]).strip()
            return text, { "provider": "local", "language": info.language, "language_probability": info.language_probability }

        return await asyncio.to_thread(do_transcribe)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(TRANSIENT_ERRORS))
    async def chat(self, messages: List[Dict[str, str]]) -> Tuple[str, float, Dict[str, Any]]:
        log.debug(f"Starting chat completion with {len(messages)} messages.")
        with Timer("chat", log) as t:
            cfg = self.config.get("llm", {})
            try:
                response = await self.openai_client.chat.completions.create(
                    model=cfg.get("model", "gpt-4o-mini"),
                    messages=messages,
                    temperature=cfg.get("temperature", 0.6),
                    stream=False,
                )
                reply_text = response.choices[0].message.content
                usage = response.usage
                meta = { "model": response.model, "prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens, "total_tokens": usage.total_tokens }
                log.debug(f"Chat completion successful. Token usage: {usage}")
            except openai.APIError as e:
                log.error(f"OpenAI API error during chat completion: {e.body}", exc_info=True)
                raise
        log.info(f"Chat completion finished in {t.elapsed_ms:.2f}ms. Reply: '{reply_text[:50]}...'")
        return reply_text or "", t.elapsed_ms, meta

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(TRANSIENT_ERRORS))
    async def tts(self, text: str) -> Tuple[bytes, float, Dict[str, Any]]:
        log.debug(f"Starting TTS for text: '{text[:50]}...' with provider: {self.tts_provider}")
        with Timer("tts", log) as t:
            if self.tts_provider == "local":
                wav_bytes, meta = await self._tts_local(text)
            else:
                wav_bytes, meta = await self._tts_openai(text)
        log.info(f"TTS finished in {t.elapsed_ms:.2f}ms. Output size: {len(wav_bytes)} bytes.")
        return wav_bytes, t.elapsed_ms, meta

    async def _tts_openai(self, text: str) -> Tuple[bytes, Dict]:
        cfg = self.config.get("openai", {})
        audio_cfg = self.config.get("audio", {})
        log.debug(f"Synthesizing speech with OpenAI TTS model '{cfg.get('tts_model')}', voice '{cfg.get('voice')}'.")
        try:
            response = await self.openai_client.audio.speech.create(
                model=cfg.get("tts_model", "tts-1"),
                voice=cfg.get("voice", "onyx"),
                input=text,
                response_format="mp3"
            )
            mp3_bytes = response.content

            def do_convert():
                log.debug("Converting MP3 response to WAV...")
                segment = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
                segment = segment.set_frame_rate(audio_cfg.get("sample_rate", 16000)).set_channels(audio_cfg.get("channels", 1))
                buf = io.BytesIO()
                segment.export(buf, format="wav")
                return buf.getvalue()

            wav_bytes = await asyncio.to_thread(do_convert)
            log.debug(f"MP3 to WAV conversion complete. WAV size: {len(wav_bytes)} bytes.")
            return wav_bytes, {"provider": "openai"}
        except openai.APIError as e:
            log.error(f"OpenAI API error during TTS: {e.body}", exc_info=True)
            raise

    async def _tts_local(self, text: str) -> Tuple[bytes, Dict]:
        if not self.local_tts_engine: raise RuntimeError("Local TTS engine not initialized.")
        log.debug("Synthesizing speech with local pyttsx3 engine.")

        def do_synthesize():
            output_wav_file = f"temp_tts_{os.getpid()}.wav"
            try:
                self.local_tts_engine.save_to_file(text, output_wav_file)
                self.local_tts_engine.runAndWait()
                if os.path.exists(output_wav_file):
                    with open(output_wav_file, "rb") as f:
                        return f.read(), {"provider": "local"}
                else:
                    log.error("pyttsx3 failed to generate audio file.")
                    return b"", {"provider": "local", "error": "File not created"}
            finally:
                if os.path.exists(output_wav_file):
                    os.remove(output_wav_file)

        return await asyncio.to_thread(do_synthesize)
