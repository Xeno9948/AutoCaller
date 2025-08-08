# scripts/sanity_tts_test.py
import asyncio
import os
import sys
from dotenv import load_dotenv
import sounddevice as sd
import soundfile as sf
import io
import logging

# Add project root to path to allow absolute imports from bot module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Setup minimal logging for this script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Suppress noisy loggers
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

from bot.ai_client import AIClient
from bot.utils import Timer

async def main():
    print("--- Sanity TTS Test ---")
    print("This script will test the Text-to-Speech functionality using your configuration.")

    # 1. Load environment variables
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        logging.error("❌ OPENAI_API_KEY not found in .env file. Please create one and add your key.")
        return

    # 2. A minimal config for the AIClient, assuming OpenAI provider
    # This avoids needing the full config.yaml for a simple test.
    config = {
        "tts": {"provider": "openai"},
        "openai": {"tts_model": "tts-1", "voice": "onyx"},
        # OpenAI TTS default sample rate is 24kHz. AIClient handles resampling.
        "audio": {"sample_rate": 16000, "channels": 1}
    }

    try:
        # 3. Initialize AI Client
        print("\nInitializing AI client...")
        ai_client = AIClient(config)

        # 4. Synthesize speech
        test_text = "Hello, this is a test of the text-to-speech system. If you can hear this, it's working."
        print(f"Synthesizing speech for: '{test_text}'")

        with Timer("TTS_Generation", logging.getLogger()) as t:
            # The tts method returns (wav_bytes, duration_ms, metadata)
            wav_bytes, _, meta = await ai_client.tts(test_text)

        if not wav_bytes:
            logging.error("❌ TTS returned no audio data. Check AIClient logs for errors.")
            return

        logging.info(f"✅ TTS generation successful in {t.elapsed_ms:.2f} ms. (Provider: {meta.get('provider')})")

        # 5. Play back audio
        print("\nPlaying back synthesized audio...")
        try:
            data, samplerate = sf.read(io.BytesIO(wav_bytes))
            logging.info(f"Audio details: {len(data)} samples, {samplerate}Hz sample rate.")

            sd.play(data, samplerate)

            with Timer("Playback", logging.getLogger()) as pt:
                sd.wait() # Wait for playback to finish

            logging.info(f"✅ Playback finished successfully.")
            print("\n--- Test Successful ---")

        except Exception as e:
            logging.error(f"❌ Failed to play audio: {e}", exc_info=True)
            print("\nTroubleshooting:")
            print("- Is your default audio output device (speakers/headphones) working correctly?")
            print("- Check your system's volume levels.")

    except Exception as e:
        logging.error(f"❌ An unexpected error occurred: {e}", exc_info=True)
        print("\nTroubleshooting:")
        print("- Is your OpenAI API key valid and does it have credit?")
        print("- Do you have a stable internet connection?")
        print("- Have you run 'scripts/install_mac.sh' to install all dependencies?")

if __name__ == "__main__":
    # Ensure we run in an asyncio event loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest cancelled by user.")
