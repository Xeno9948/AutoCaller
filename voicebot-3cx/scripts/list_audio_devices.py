# scripts/list_audio_devices.py
import sounddevice as sd
import json
import argparse
import sys

def list_devices():
    """Prints a human-readable, formatted list of available audio devices."""
    print("🔎 Querying available audio devices...")
    try:
        devices = sd.query_devices()
        default_input_idx, default_output_idx = sd.default.device

        if not devices:
            print("\n❌ No audio devices found. This is unusual.")
            print("Please check your system's audio settings and ensure microphones/speakers are connected.")
            return

        print("\n--- Audio Devices ---")
        for i, device in enumerate(devices):
            in_ch = device.get('max_input_channels', 0)
            out_ch = device.get('max_output_channels', 0)

            direction = []
            if in_ch > 0: direction.append(f"{in_ch}ch IN")
            if out_ch > 0: direction.append(f"{out_ch}ch OUT")
            direction_str = ' / '.join(direction) if direction else "No I/O"

            default_marker = ""
            if i == default_input_idx: default_marker += " [Default Input]"
            if i == default_output_idx: default_marker += " [Default Output]"

            print(f"  [{i}] {device['name']} ({direction_str}){default_marker}")

        print("\n💡 Tip: In your config.yaml, use the device name (e.g., 'BlackHole 2ch') or its index (e.g., 2).")
        print("   The bot needs a device that is both Input and Output capable, like 'BlackHole 2ch'.")

    except Exception as e:
        print(f"\n❌ Error: Could not query audio devices: {e}")
        print("   Please ensure PortAudio is installed (`brew install portaudio`) and functional.")

def list_devices_json():
    """Prints the list of audio devices in JSON format for programmatic use."""
    try:
        devices = sd.query_devices()
        # The device object itself isn't directly JSON serializable, so we create a list of dicts
        device_list = []
        for i, device in enumerate(devices):
            # Create a serializable copy of the device dictionary
            device_info = {
                'index': i,
                'name': device['name'],
                'hostapi': device['hostapi'],
                'max_input_channels': device['max_input_channels'],
                'max_output_channels': device['max_output_channels'],
                'default_low_input_latency': device['default_low_input_latency'],
                'default_low_output_latency': device['default_low_output_latency'],
                'default_high_input_latency': device['default_high_input_latency'],
                'default_high_output_latency': device['default_high_output_latency'],
                'default_samplerate': device['default_samplerate'],
            }
            device_list.append(device_info)

        print(json.dumps(device_list, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))

def main():
    parser = argparse.ArgumentParser(
        description="List available audio devices for the voicebot.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the device list in JSON format."
    )
    args = parser.parse_args()

    # Check if sounddevice is available
    try:
        import sounddevice
    except Exception as e:
        print(f"❌ Error: Failed to import 'sounddevice'.\n   {e}", file=sys.stderr)
        print("   Please run 'scripts/install_mac.sh' to install dependencies.", file=sys.stderr)
        sys.exit(1)

    if args.json:
        list_devices_json()
    else:
        list_devices()

if __name__ == "__main__":
    main()
