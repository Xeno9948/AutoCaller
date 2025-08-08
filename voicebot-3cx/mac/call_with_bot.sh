#!/bin/bash

# Orchestrator script to place a call with the AI bot.
#
# This script automates the process of:
# 1. Saving your current audio device settings.
# 2. Switching audio to a virtual device (BlackHole) for the bot.
# 3. Launching 3CX, dialing a number, and starting the bot.
# 4. Restoring your original audio settings after the call.
#
# Usage:
#   ./mac/call_with_bot.sh +15551234567
#
# Prerequisites:
#   - Homebrew installed.
#   - `switchaudio-osx` installed (via `brew install switchaudio-osx`).
#   - BlackHole 2ch virtual audio device installed.
#   - A Python virtual environment created at `.venv` in the project root.

# --- Script Configuration ---
# Exit immediately if a command exits with a non-zero status.
set -e
# The return value of a pipeline is the status of the last command to exit with a non-zero status.
set -o pipefail

# --- Constants ---
TARGET_AUDIO_DEVICE="BlackHole 2ch"
VENV_PATH="./.venv"
BOT_MAIN_MODULE="bot.run" # Use python -m for robust imports
SCRIPT_DIR=$(dirname "$0")
APPLE_SCRIPT_PATH="$SCRIPT_DIR/dial.scpt"

# --- Logging Helper ---
log() {
    echo -e "\033[1;34m[$(date +'%Y-%m-%d %H:%M:%S')]\033[0m $1"
}

log_error() {
    echo -e "\033[1;31m[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:\033[0m $1" >&2
}

# --- Argument Check ---
if [ -z "$1" ]; then
    log_error "No phone number provided."
    echo "Usage: $0 <E.164_phone_number> [\"Optional sales goal in quotes\"]"
    exit 1
fi
PHONE_NUMBER=$1
SALES_GOAL=$2 # This will be the second argument

# --- Cleanup Function ---
# This function is called on script exit to restore audio devices.
cleanup() {
    log "--- Running cleanup ---"
    if [ -n "$ORIGINAL_INPUT" ]; then
        log "Restoring original audio input device to '$ORIGINAL_INPUT'..."
        SwitchAudioSource -t input -s "$ORIGINAL_INPUT" || log_error "Failed to restore input device."
    fi
    if [ -n "$ORIGINAL_OUTPUT" ]; then
        log "Restoring original audio output device to '$ORIGINAL_OUTPUT'..."
        SwitchAudioSource -t output -s "$ORIGINAL_OUTPUT" || log_error "Failed to restore output device."
    fi
    log "--- Cleanup complete ---"
}

# --- Trap for exit signals ---
# Ensures cleanup runs even if the script is interrupted (Ctrl+C).
trap cleanup EXIT INT TERM

# --- Main Logic ---
log "Starting call orchestration for number: $PHONE_NUMBER"

# 1. Save original audio devices
log "Saving current audio devices..."
ORIGINAL_INPUT=$(SwitchAudioSource -c -t input)
ORIGINAL_OUTPUT=$(SwitchAudioSource -c -t output)
log "  - Original Input:  '$ORIGINAL_INPUT'"
log "  - Original Output: '$ORIGINAL_OUTPUT'"

# 2. Switch to BlackHole
log "Switching audio devices to '$TARGET_AUDIO_DEVICE'..."
SwitchAudioSource -t input -s "$TARGET_AUDIO_DEVICE"
SwitchAudioSource -t output -s "$TARGET_AUDIO_DEVICE"
log "  - Current Input:  '$(SwitchAudioSource -c -t input)'"
log "  - Current Output: '$(SwitchAudioSource -c -t output)'"

# 3. Launch 3CX and Dial
log "Opening 3CX Desktop App..."
open -a "3CX Desktop App"
sleep 2 # Give the app time to launch and settle

log "Dialing $PHONE_NUMBER via AppleScript..."
DIAL_RESULT=$(osascript "$APPLE_SCRIPT_PATH" "$PHONE_NUMBER")
if [[ "$DIAL_RESULT" == *"Error"* ]]; then
    log_error "AppleScript failed to dial: $DIAL_RESULT"
    exit 1
fi
log "AppleScript result: $DIAL_RESULT"
sleep 2 # Give the call time to connect

# 4. Activate venv and run the bot
log "Activating Python virtual environment..."
if [ ! -f "$VENV_PATH/bin/activate" ]; then
    log_error "Python virtual environment not found at $VENV_PATH."
    log_error "Please run './scripts/install_mac.sh' first."
    exit 1
fi
source "$VENV_PATH/bin/activate"

log "Starting the Python AI bot... (Press Ctrl+C to end the call)"
# The bot script will run here until it exits or is interrupted.
# The `trap` will handle cleanup automatically.
if [ -n "$SALES_GOAL" ]; then
    log "  - With sales goal: '$SALES_GOAL'"
    python -m "$BOT_MAIN_MODULE" --sales-goal "$SALES_GOAL"
else
    log "  - No sales goal provided."
    python -m "$BOT_MAIN_MODULE"
fi

log "Bot script finished. Orchestration complete."
exit 0
