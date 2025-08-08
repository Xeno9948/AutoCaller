#!/bin/bash

# Installation script for the AI Voicebot on macOS.
# This script will:
# 1. Check for Homebrew and offer to install it.
# 2. Install necessary system dependencies using Homebrew.
# 3. Create a Python virtual environment.
# 4. Install required Python packages from requirements.txt.

# --- Script Configuration ---
set -e # Exit on any error

# --- Helper Functions ---
log() {
    # Blue text for informational messages
    echo -e "\n\033[1;34m=> $1\033[0m"
}

log_success() {
    # Green text for success messages
    echo -e "\033[1;32m✅ $1\033[0m"
}

log_warning() {
    # Yellow text for warnings
    echo -e "\033[1;33m⚠️ $1\033[0m"
}

log_error() {
    # Red text for errors
    echo -e "\033[1;31m❌ ERROR: $1\033[0m" >&2
}

# --- Check for Homebrew ---
log "Checking for Homebrew..."
if ! command -v brew &> /dev/null; then
    log_warning "Homebrew not found."
    read -p "Do you want to install Homebrew now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    else
        log_error "Homebrew is required. Please install it and run this script again."
        exit 1
    fi
else
    log_success "Homebrew is already installed. Updating..."
    brew update
fi

# --- Install System Dependencies ---
log "Installing system dependencies with Homebrew..."
dependencies="python@3.11 ffmpeg portaudio switchaudio-osx"
for dep in $dependencies; do
    if brew list $dep &>/dev/null; then
        log_success "$dep is already installed."
    else
        log "Installing $dep..."
        brew install $dep
    fi
done
log_success "All system dependencies are installed."

# --- Create Python Virtual Environment ---
VENV_DIR=".venv"
log "Creating Python virtual environment at '$VENV_DIR'..."
if [ -d "$VENV_DIR" ]; then
    log_warning "Virtual environment already exists. Skipping creation."
else
    # Use the Homebrew-installed Python to ensure we get the right version
    /usr/local/opt/python@3.11/bin/python3.11 -m venv "$VENV_DIR"
    log_success "Virtual environment created."
fi

# --- Activate Venv and Install Python Packages ---
log "Activating virtual environment and installing Python packages..."
# Temporarily change directory to the script's location to find requirements.txt
cd "$(dirname "$0")/.."
source "$VENV_DIR/bin/activate"

log "Upgrading pip..."
pip install --upgrade pip

log "Installing packages from requirements.txt..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    log_success "Python packages installed."
else
    log_error "requirements.txt not found in the project root!"
    # Deactivate before exiting on error
    deactivate
    exit 1
fi

# --- Print Next Steps ---
log_success "Installation complete!"
echo -e "\n\033[1;32m--- Next Steps ---\033[0m"
echo "1. Install the BlackHole 2ch virtual audio driver from:"
echo "   \033[0;34mhttps://github.com/ExistentialAudio/BlackHole/releases\033[0m"
echo "   (Download and run the installer)."
echo ""
echo "2. Make 3CX the default for 'tel:' links. In FaceTime, go to Settings and change"
echo "   'Default for calls:' from 'FaceTime' to '3CX Desktop App'."
echo ""
echo "3. Copy the example environment file:"
echo "   \033[0;33mcp .env.example .env\033[0m"
echo ""
echo "4. Edit the new \`.env\` file and add your OpenAI API key."
echo ""
echo "5. Find your 'BlackHole 2ch' device name/index by running:"
echo "   \033[0;33mpython scripts/list_audio_devices.py\033[0m"
echo ""
echo "6. Update \`config.yaml\` with the correct audio device names or indexes."
echo ""
echo "7. You are now ready to run the bot! Start a call with:"
echo "   \033[0;33m./mac/call_with_bot.sh +15551234567\033[0m"

# Deactivate venv for the current shell session so it doesn't pollute the user's shell
deactivate
