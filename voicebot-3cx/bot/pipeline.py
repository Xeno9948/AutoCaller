# bot/pipeline.py
import asyncio
import logging
from typing import Dict, Any, List
import time

from bot.audio_io import AudioInput
from bot.vad import VadSegmenter
from bot.ai_client import AIClient
from bot.playback import PlaybackManager
from bot.prompts import get_system_prompt
from bot.status_server import StatusServer
from bot.knowledge_base import KnowledgeBase

log = logging.getLogger(__name__)
turn_logger = logging.getLogger("turn_logger")

class BotPipeline:
    """
    The main pipeline that orchestrates the bot's operations:
    listening, processing (STT, LLM, TTS), and responding with playback.
    Manages the conversation state and handles barge-in.
    """
    def __init__(self,
                 config: Dict[str, Any],
                 audio_in: AudioInput,
                 vad: VadSegmenter,
                 ai_client: AIClient,
                 playback_manager: PlaybackManager,
                 status_server: StatusServer,
                 knowledge_base: KnowledgeBase,
                 sales_goal: str = ""):
        self.config = config
        self.audio_in = audio_in
        self.vad = vad
        self.ai_client = ai_client
        self.playback_manager = playback_manager
        self.status_server = status_server
        self.knowledge_base = knowledge_base
        self.sales_goal = sales_goal

        self.is_running = False
        self.conversation_history: List[Dict[str, str]] = []
        self.system_prompt = get_system_prompt(self.config.get("persona", {}), self.sales_goal)
        self.reset_history()

    def reset_history(self):
        log.info("Resetting conversation history to system prompt.")
        self.conversation_history = self.system_prompt.copy()

    async def run(self):
        self.is_running = True
        log.info("Bot pipeline started. Waiting for user to speak...")

        try:
            while self.is_running:
                utterance_bytes = await self._listen_for_utterance()
                if not utterance_bytes:
                    if not self.is_running: break
                    continue

                await self._process_and_respond(utterance_bytes)

        except asyncio.CancelledError:
            log.info("Pipeline run task was cancelled.")
        finally:
            self.is_running = False
            log.info("Bot pipeline has stopped.")

    async def _listen_for_utterance(self) -> bytes:
        """Listens for a single complete utterance from the VAD."""
        log.debug("Listening for user utterance...")
        self.vad.reset()
        while self.is_running:
            try:
                audio_chunk = await asyncio.wait_for(self.audio_in.queue.get(), timeout=0.1)
                for utterance in self.vad.segment(audio_chunk):
                    return utterance
            except asyncio.TimeoutError:
                continue
        return None

    async def _process_and_respond(self, utterance_bytes: bytes):
        """Handles a single conversation turn."""
        turn_data = { "ts": datetime.utcnow().isoformat(), "errors": [] }
        turn_timer_start = time.perf_counter()

        try:
            # STT
            asr_text, stt_ms, _ = await self.ai_client.transcribe(utterance_bytes)
            turn_data["stt_ms"] = round(stt_ms)
            if not asr_text or len(asr_text.strip()) < 2:
                log.info(f"Skipping empty/short transcription: '{asr_text}'")
                return
            log.info(f"User said: '{asr_text}'")
            turn_data["asr_text"] = asr_text

            # --- RAG Integration ---
            # 1. Query Knowledge Base for context
            context = self.knowledge_base.query(asr_text)

            # 2. Prepare messages for LLM
            messages_for_llm = self.conversation_history.copy()
            messages_for_llm.append({"role": "user", "content": asr_text})

            # 3. Inject context if found
            if context:
                log.info("Injecting context from knowledge base into prompt.")
                context_prompt = (
                    "Use the following information from your knowledge base to help answer the user's question. "
                    "Do not mention the knowledge base directly, just use the information. "
                    "If the context does not contain the answer, say you don't have that information.\n\n"
                    f"<context>\n{context}\n</context>"
                )
                # Insert the context as a system message before the user's question
                messages_for_llm.insert(-1, {"role": "system", "content": context_prompt})

            # LLM Call
            llm_text, llm_ms, _ = await self.ai_client.chat(messages_for_llm)
            turn_data["llm_ms"] = round(llm_ms)
            turn_data["llm_text"] = llm_text
            log.info(f"Bot reply: '{llm_text}'")

            # 4. Update conversation history *after* the turn is complete
            self.conversation_history.append({"role": "user", "content": asr_text})
            self.conversation_history.append({"role": "assistant", "content": llm_text})

            # TTS
            tts_bytes, tts_ms, _ = await self.ai_client.tts(llm_text)
            turn_data["tts_ms"] = round(tts_ms)

            # Playback with barge-in
            await self._playback_with_barge_in(tts_bytes)

        except Exception as e:
            log.error(f"Error during turn processing: {e}", exc_info=True)
            turn_data["errors"].append(str(e))
        finally:
            turn_data["turn_ms"] = round((time.perf_counter() - turn_timer_start) * 1000)
            turn_data["errors"] = "; ".join(turn_data["errors"])
            turn_logger.info("Turn processed", extra={'turn_data': turn_data})
            if self.status_server:
                self.status_server.add_turn_data(turn_data)

    async def _playback_with_barge_in(self, tts_bytes: bytes):
        log.debug("Starting playback with barge-in detection.")

        playback_task = asyncio.create_task(self.playback_manager.play_audio(tts_bytes))
        barge_in_task = asyncio.create_task(self._detect_barge_in())

        done, pending = await asyncio.wait({playback_task, barge_in_task}, return_when=asyncio.FIRST_COMPLETED)

        if barge_in_task in done:
            log.info("Barge-in detected. Interrupting playback.")
            self.playback_manager.interrupt()

        for task in pending:
            task.cancel()

        try:
            await playback_task
        except asyncio.CancelledError:
            pass

    async def _detect_barge_in(self):
        barge_in_vad = VadSegmenter(self.config)

        await asyncio.sleep(0.2) # Grace period for playback to start and echo to settle
        while not self.audio_in.queue.empty():
            self.audio_in.queue.get_nowait()
        log.debug("Audio queue cleared for barge-in detection.")

        while self.playback_manager.is_playing:
            try:
                audio_chunk = await asyncio.wait_for(self.audio_in.queue.get(), timeout=0.1)
                for _ in barge_in_vad.segment(audio_chunk):
                    log.info("Barge-in VAD detected speech.")
                    return
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def stop(self):
        log.info("Stopping bot pipeline...")
        self.is_running = False
        if final_utterance := self.vad.flush():
            log.info(f"Processing final flushed utterance of {len(final_utterance)} bytes.")
            # In a real scenario, you might want to process this
            pass
from datetime import datetime
