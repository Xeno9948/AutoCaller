# scripts/sanity_input_monitor.py
import sounddevice as sd
import numpy as np
import soundfile as sf
import yaml
import os
import sys
import time
import argparse

# Add project root to path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.utils import calculate_rms, resolve_path

def load_config(config_path: str) -> dict:
    """Loads the YAML configuration file."""
    try:
        with open(resolve_path(config_path), 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"⚠️  Warning: Could not load or parse config file at '{config_path}': {e}")
        print("    Will use default audio settings.")
        return {}

def resolve_device_index(device_name: str) -> int:
    """Resolves a device name to its index. Returns None if not found."""
    if not isinstance(device_name, str):
        return device_name # Assume it's already an index or None
    try:
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device['name'] == device_name:
                return i
        return None
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser(description="Record audio from the configured input device to test its functionality.")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to the configuration file.")
    args = parser.parse_args()

    print("--- Sanity Input Monitor ---")
    print(f"Loading configuration from '{args.config}'...")

    config = load_config(args.config)
    audio_config = config.get('audio', {})

    device_spec = audio_config.get('input_device', None)
    sample_rate = audio_config.get('sample_rate', 16000)
    channels = audio_config.get('channels', 1)
    duration = 5  # seconds

    # Resolve device name to index if necessary
    device_index = resolve_device_index(device_spec)

    print(f"\nConfiguration:")
    print(f"  - Device: '{device_spec}' (Resolved to index: {device_index if device_index is not None else 'default'})")
    print(f"  - Sample Rate: {sample_rate} Hz")
    print(f"  - Channels: {channels}")
    print(f"  - Duration: {duration} seconds")

    try:
        # Start recording in a non-blocking way
        recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=channels, dtype='float32', device=device_index)

        print("\n🎙️  Say something into your microphone...")
        for i in range(duration, 0, -1):
            print(f"    Recording... {i}s left", end='\r')
            time.sleep(1)

        print("\n\nFinished recording. Waiting for buffer to finalize...")
        sd.wait()  # Wait for the recording to complete

        # --- Analysis ---
        print("\n--- Analysis ---")
        # Calculate RMS
        rms = calculate_rms(recording)
        print(f"  - RMS (volume): {rms:.6f}")
        if rms < 0.001:
            print("  - ⚠️  WARNING: Input level is very low. Is the correct microphone selected and unmuted?")
        elif rms > 0.5:
            print("  - ⚠️  WARNING: Input level is very high. Clipping may occur.")
        else:
            print("  - ✅ Input level seems reasonable.")

        # --- Save to file ---
        output_dir = "tmp"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "monitor.wav")

        print(f"\nSaving recording to '{output_path}'...")
        sf.write(output_path, recording, sample_rate)

        print("\n--- Test Successful ---")
        print(f"You can now listen to '{output_path}' to verify the audio quality.")

    except Exception as e:
        print(f"\n❌ ERROR: An error occurred during recording: {e}")
        print("\nTroubleshooting:")
        print("  - Have you run 'scripts/install_mac.sh'?")
        print(f"  - Does the device '{device_spec}' exist? Run 'python scripts/list_audio_devices.py' to check.")
        print("  - Check your system's microphone permissions for your terminal.")

if __name__ == "__main__":
    main()
