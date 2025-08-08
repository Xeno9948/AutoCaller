# Real-Time AI Voicebot for 3CX on macOS

This repository contains a complete, ready-to-run project for a real-time AI voicebot that integrates with the 3CX Desktop App on macOS. It uses a virtual audio device (BlackHole) to intercept audio, and OpenAI's APIs for speech-to-text (STT), language model (LLM), and text-to-speech (TTS).

The bot is designed for real-time, low-latency conversation and features voice activity detection (VAD) and barge-in capabilities, allowing users to interrupt the bot naturally.

## Features

- **Real-Time Pipeline**: Asynchronous audio processing for low-latency interaction.
- **VAD & Barge-In**: Detects when the user is speaking and allows them to interrupt the bot's response.
- **3CX Integration**: Automatically controls the 3CX Desktop App to place calls.
- **macOS Native**: Uses AppleScript and shell scripts for seamless macOS orchestration.
- **Configurable Persona**: Easily change the bot's personality and instructions via YAML configuration.
- **Provider Flexibility**: Supports OpenAI for AI services with optional, guarded fallbacks for local STT/TTS.
- **Rich Debugging**: Extensive logging, including console, file, and structured turn-by-turn logs in CSV and JSONL formats.
- **Status Server**: A built-in Flask server to monitor the bot's health and recent conversations.

## Quickstart Guide for macOS

Follow these steps to get the bot up and running on your Mac.

### 1. Prerequisite: Install BlackHole

The bot requires a virtual audio device to capture and send audio to/from the 3CX softphone. We recommend BlackHole.

- Download and install the **BlackHole 2ch** driver from [their official GitHub releases](https://github.com/ExistentialAudio/BlackHole/releases).
- Follow the installation instructions. After installation, "BlackHole 2ch" will appear as an available audio device on your system.

### 2. Prerequisite: Configure 3CX for `tel:` links

To allow the script to dial numbers, the 3CX Desktop App must be set as the default handler for `tel:` URLs.

- Open the **FaceTime** app on your Mac.
- In the menu bar, go to `FaceTime` > `Settings...`.
- At the bottom of the settings window, change the **"Default for calls:"** dropdown from "FaceTime" to **"3CXDesktopApp"**.

### 3. Run the Automated Installation Script

This project includes a script that installs all necessary software dependencies.

- Open your terminal.
- Clone this repository and navigate into the project directory.
- Run the installation script:
  ```bash
  ./scripts/install_mac.sh
  ```
This script will use Homebrew to install `python@3.11`, `ffmpeg`, `portaudio`, and `switchaudio-osx`. It will then create a Python virtual environment (`.venv/`) and install all required Python packages.

### 4. Configure Environment Variables

You need to provide your OpenAI API key for the bot to work.

- Copy the example `.env` file:
  ```bash
  cp .env.example .env
  ```
- Edit the new `.env` file and paste your OpenAI API key:
  ```
  OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  LOG_LEVEL=DEBUG # Optional: Keep DEBUG for verbose logs
  ```

### 5. Configure the Bot

The `config.yaml` file controls the bot's behavior. You need to tell it which audio devices to use.

- First, find the name or index of your BlackHole device:
  ```bash
  python scripts/list_audio_devices.py
  ```
- Look for `BlackHole 2ch` in the output. Note its name or index number.
- Open `config.yaml` and update the `audio` section. It should look like this:
  ```yaml
  audio:
    input_device: "BlackHole 2ch"
    output_device: "BlackHole 2ch"
    # ... other settings
  ```
  You can use the device name (string) or its index (integer).

### 6. Run Sanity Checks (Recommended)

Before making a live call, run these helper scripts to ensure everything is configured correctly.

- **Test Text-to-Speech (TTS):**
  ```bash
  python scripts/sanity_tts_test.py
  ```
  You should hear a test sentence played through your default speakers.

- **Test Audio Input:**
  ```bash
  python scripts/sanity_input_monitor.py
  ```
  This will record 5 seconds of audio from the configured input device (`BlackHole 2ch`) and save it to `tmp/monitor.wav`.

### 7. Place a Call with the Bot!

You are now ready to run the full orchestration script.

- Provide an E.164 formatted phone number as an argument:
  ```bash
  ./mac/call_with_bot.sh +15551234567
  ```
- The script will:
  1. Switch your system audio to BlackHole.
  2. Open the 3CX app and dial the number.
  3. Start the Python bot, which will take over the call.
- To end the call, press **`Ctrl+C`** in the terminal. The script will automatically restore your original audio devices.

## Troubleshooting

- **`tel:` links not working / 3CX doesn't dial:**
  - Ensure you completed Step 2 of the quickstart. If it still fails, you can try dialing manually from the 3CX app and then running the bot script directly: `source .venv/bin/activate && python -m bot.run`.

- **No audio, or you hear an echo:**
  - **Device Routing**: Double-check that `config.yaml` points to `BlackHole 2ch`.
  - **3CX Settings**: In the 3CX Desktop App, go to `Settings` > `Audio/Video`. Ensure your **Headset** (not BlackHole) is selected for `Speaker` and `Ringer`. This ensures you hear ringing and the other party through your headphones, while the bot handles the main call audio via BlackHole.
  - **Echo Cancellation**: Enable echo cancellation in the 3CX app settings if available.
  - **Gain**: If the bot is too loud or quiet, adjust `audio.output_gain_db` in `config.yaml`.

- **High Latency:**
  - **Concise Prompts**: Reduce `persona.max_reply_sentences` in `config.yaml` to make the bot's responses shorter.
  - **Local Models**: For advanced users, switch `stt.provider` to `local` to use `faster-whisper` for transcription, which can be faster than the API. This requires a powerful machine.
  - **Network**: Use a wired network connection for lower network latency to OpenAI's servers.

- **`Device not found` errors:**
  - Run `python scripts/list_audio_devices.py` again to verify the device name or index. macOS can sometimes change device indexes. Using the full name (e.g., `"BlackHole 2ch"`) in `config.yaml` is more reliable.

- **OpenAI API Errors:**
  - Check that your `OPENAI_API_KEY` in `.env` is correct and has available credit.
  - Check your internet connection.
  - The logs in `logs/voicebot.log` will contain detailed error messages from the OpenAI API.

## Safety & Responsibility

This bot is a demonstration and should be used responsibly.
- **No Guarantees**: The bot can misunderstand or provide incorrect information. Do not use it for sensitive applications involving medical, legal, or financial advice.
- **Human Handoff**: The default prompts instruct the bot to offer a connection to a human agent if the user is frustrated or asks for a manager. This is a critical safety feature for any real-world deployment.
- **Polite Termination**: The bot is designed to respect "goodbye" or "stop" keywords to end the session politely.
