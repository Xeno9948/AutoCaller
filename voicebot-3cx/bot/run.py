# bot/run.py
import asyncio
import logging
import argparse
import yaml
import os
import sys
from dotenv import load_dotenv
import sounddevice as sd

# Add project root to path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.logging_util import setup_logging
from bot.utils import resolve_path
from bot.audio_io import AudioInput, AudioOutput
from bot.vad import VadSegmenter
from bot.ai_client import AIClient
from bot.playback import PlaybackManager
from bot.pipeline import BotPipeline
from bot.status_server import StatusServer
from bot.knowledge_base import KnowledgeBase

log = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(description="AI Voicebot for 3CX")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to the configuration file.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging, overrides LOG_LEVEL in .env.")
    parser.add_argument("--list-devices", action="store_true", help="List available audio devices and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Run a synthetic loop to test AI connectivity without audio.")
    parser.add_argument("--sales-goal", type=str, default="", help="A specific sales goal or objective for the bot to follow.")
    return parser.parse_args()

def load_config(config_path: str) -> dict:
    try:
        with open(resolve_path(config_path), 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        log.error(f"Configuration file not found at '{config_path}'.")
        sys.exit(1)
    except yaml.YAMLError as e:
        log.error(f"Error parsing YAML configuration file: {e}")
        sys.exit(1)

def list_audio_devices():
    """Prints a list of available audio devices."""
    print("Available audio devices:")
    try:
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            # Show device index, name, and direction (in/out)
            direction = ""
            if device['max_input_channels'] > 0:
                direction += "IN"
            if device['max_output_channels'] > 0:
                direction += "/OUT" if direction else "OUT"
            print(f"  {i}: {device['name']} ({direction})")
    except Exception as e:
        print(f"  Could not list audio devices: {e}")

def resolve_device_indices(config: dict):
    """
    Resolves audio device names in the config to their corresponding indices.
    If a device is not found, it logs an error but tries to proceed with the default.
    """
    devices = sd.query_devices()
    device_names = [d['name'] for d in devices]

    for key in ['input_device', 'output_device']:
        device_val = config['audio'].get(key)
        if isinstance(device_val, str):
            try:
                index = device_names.index(device_val)
                config['audio'][key] = index
                log.debug(f"Resolved device '{device_val}' to index {index}.")
            except ValueError:
                log.error(f"Audio device '{device_val}' not found. Using default device.")
                config['audio'][key] = None # Use sounddevice default
    return config

async def dry_run_loop(ai_client: AIClient, prompts: list):
    """A simple loop to test AI services without audio hardware."""
    log.info("--- Starting Dry Run ---")
    log.info("This will test STT (with fake audio), LLM, and TTS services.")

    try:
        # 1. Test LLM
        log.info("Testing LLM with a simple prompt...")
        history = prompts + [{"role": "user", "content": "Hello, who are you?"}]
        reply, _, _ = await ai_client.chat(history)
        log.info(f"LLM replied: '{reply}'")
        if not reply: raise ValueError("LLM returned empty response.")

        # 2. Test TTS
        log.info("Testing TTS with the LLM response...")
        tts_bytes, _, _ = await ai_client.tts(reply)
        log.info(f"TTS generated {len(tts_bytes)} bytes of audio data.")
        if not tts_bytes: raise ValueError("TTS returned empty audio.")

        # 3. Test STT (with the generated TTS audio)
        log.info("Testing STT by transcribing the generated TTS audio...")
        text, _, _ = await ai_client.transcribe(tts_bytes)
        log.info(f"STT transcribed: '{text}'")
        if not text: raise ValueError("STT returned empty transcription.")

        log.info("--- Dry Run Successful ---")
    except Exception as e:
        log.error(f"Dry run failed: {e}", exc_info=True)
        log.error("Please check your API keys, network connection, and configurations.")
    finally:
        log.info("--- Dry Run Finished ---")


async def main():
    load_dotenv()
    args = parse_args()
    setup_logging(args.debug)

    if args.list_devices:
        list_audio_devices()
        return

    config = load_config(args.config)
    config = resolve_device_indices(config)

    # Initialize components
    try:
        ai_client = AIClient(config)
    except (ValueError, ImportError) as e:
        log.error(f"Failed to initialize AI Client: {e}")
        return

    if args.dry_run:
        system_prompts = get_system_prompt(config.get("persona", {}))
        await dry_run_loop(ai_client, system_prompts)
        return

    # --- Full bot startup ---
    loop = asyncio.get_running_loop()

    # Initialize components
    knowledge_base = KnowledgeBase()
    audio_in = AudioInput(config, loop)
    audio_out = AudioOutput(config)
    vad = VadSegmenter(config)
    playback_manager = PlaybackManager(config, audio_out)
    status_server = StatusServer(config)
    pipeline = BotPipeline(
        config=config,
        audio_in=audio_in,
        vad=vad,
        ai_client=ai_client,
        playback_manager=playback_manager,
        status_server=status_server,
        knowledge_base=knowledge_base,
        sales_goal=args.sales_goal
    )

    main_task = None
    try:
        # Start services
        status_server.start()
        audio_in.start()

        # Start the main pipeline
        main_task = asyncio.create_task(pipeline.run())
        await main_task

    except KeyboardInterrupt:
        log.info("Keyboard interrupt received. Shutting down...")
    except Exception as e:
        log.critical(f"An unhandled exception occurred: {e}", exc_info=True)
    finally:
        log.info("Starting graceful shutdown...")
        if main_task:
            main_task.cancel()

        pipeline.stop()
        audio_in.stop()
        audio_out.stop_all_playback()
        status_server.stop()

        # Wait for pipeline task to finish cancelling
        if main_task:
            await asyncio.sleep(0.5)

        log.info("Shutdown complete. Exiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
