# gui/app.py
import tkinter as tk
from tkinter import ttk, messagebox
import yaml
import os
import subprocess
import threading
import queue

# A dictionary to define widget types and options for each config key.
# This makes the form generation more manageable and declarative.
WIDGET_MAP = {
    "audio": {
        "input_device": {"type": "entry", "doc": "Name or index of the input device."},
        "output_device": {"type": "entry", "doc": "Name or index of the output device."},
        "sample_rate": {"type": "entry", "doc": "Sample rate for audio processing (e.g., 16000)."},
        "block_size": {"type": "entry", "doc": "Audio buffer size in samples."},
        "channels": {"type": "entry", "doc": "Number of audio channels (1 for mono)."},
        "output_gain_db": {"type": "entry", "doc": "Gain adjustment for output audio in dB."},
    },
    "vad": {
        "aggressiveness": {"type": "spinbox", "options": {"from_": 0, "to": 3, "increment": 1}, "doc": "VAD aggressiveness (0-3). Higher is more sensitive."},
        "frame_ms": {"type": "combobox", "options": [10, 20, 30], "doc": "Frame duration for VAD analysis in ms."},
        "min_speech_ms": {"type": "entry", "doc": "Minimum speech duration to trigger an utterance."},
        "max_silence_ms": {"type": "entry", "doc": "Silence duration to end an utterance."},
    },
    "llm": {
        "model": {"type": "entry", "doc": "The LLM model to use (e.g., gpt-4o-mini)."},
        "temperature": {"type": "scale", "options": {"from_": 0.0, "to": 2.0, "resolution": 0.1}, "doc": "Controls randomness. Lower is more deterministic."},
    },
    "stt": {
        "provider": {"type": "combobox", "options": ["openai", "local"], "doc": "Speech-to-Text provider."},
    },
    "tts": {
        "provider": {"type": "combobox", "options": ["openai", "local"], "doc": "Text-to-Speech provider."},
    },
    "openai": {
        "stt_model": {"type": "entry", "doc": "The Whisper model for STT."},
        "tts_model": {"type": "combobox", "options": ["tts-1", "tts-1-hd"], "doc": "The TTS model."},
        "voice": {"type": "combobox", "options": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"], "doc": "The voice for TTS."},
    },
    "persona": {
        "industry": {"type": "combobox", "options": ["generic", "tourism", "ecommerce", "cleaning"], "doc": "The bot's persona/context."},
        "max_reply_sentences": {"type": "spinbox", "options": {"from_": 1, "to": 10, "increment": 1}, "doc": "A safety rail to keep responses concise."},
    },
    "server": {
        "port": {"type": "entry", "doc": "Port for the Flask status server."},
    }
}

class Application(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.master.title("AI Voicebot Control Panel")
        self.master.geometry("850x650")
        self.pack(fill=tk.BOTH, expand=True)

        self.config_vars = {}
        self.config_data = {}
        self.config_filepath = "config.yaml"

        # For managing the bot subprocess
        self.bot_process = None
        self.log_queue = queue.Queue()

        self.create_widgets()
        self.load_config()
        self._process_log_queue()

    def create_widgets(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, fill="both", expand=True)

        self.control_tab = ttk.Frame(self.notebook, padding="10")
        self.config_tab = ttk.Frame(self.notebook, padding="10")
        self.logs_tab = ttk.Frame(self.notebook, padding="10")

        self.notebook.add(self.control_tab, text="Call Control")
        self.notebook.add(self.config_tab, text="Configuration")
        self.notebook.add(self.logs_tab, text="Logs")

        self.create_control_tab_content()
        self.create_config_tab_content()
        self.create_logs_tab_content()

    def create_control_tab_content(self):
        """Creates the content for the Call Control tab."""
        # --- Mainframe ---
        frame = ttk.Frame(self.control_tab)
        frame.pack(padx=10, pady=10, fill=tk.X)
        frame.columnconfigure(1, weight=1)

        # --- Phone Number Input ---
        ttk.Label(frame, text="Phone Number:").grid(row=0, column=0, padx=5, pady=10, sticky="w")
        self.phone_number_var = tk.StringVar()
        phone_entry = ttk.Entry(frame, textvariable=self.phone_number_var, width=40)
        phone_entry.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        phone_entry.insert(0, "+15551234567") # Default example

        # --- Control Buttons ---
        button_frame = ttk.Frame(self.control_tab)
        button_frame.pack(pady=10, fill=tk.X, side=tk.BOTTOM)

        self.start_button = ttk.Button(button_frame, text="Start Call", command=self.start_call)
        self.start_button.pack(side=tk.LEFT, padx=10)

        self.stop_button = ttk.Button(button_frame, text="Stop Call", command=self.stop_call, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=10)

        # --- Status Label ---
        self.status_var = tk.StringVar(value="Status: Idle")
        status_label = ttk.Label(button_frame, textvariable=self.status_var)
        status_label.pack(side=tk.RIGHT, padx=10)

    def create_config_tab_content(self):
        # Main frame with a scrollbar
        canvas = tk.Canvas(self.config_tab)
        scrollbar = ttk.Scrollbar(self.config_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Generate form widgets dynamically from WIDGET_MAP
        row = 0
        for section, settings in WIDGET_MAP.items():
            labelframe = ttk.LabelFrame(scrollable_frame, text=section.capitalize(), padding="10")
            labelframe.grid(row=row, column=0, padx=10, pady=5, sticky="ew")
            scrollable_frame.columnconfigure(0, weight=1)
            row += 1

            sub_row = 0
            for key, widget_info in settings.items():
                label = ttk.Label(labelframe, text=f"{key}:", tooltip=widget_info.get("doc", ""))
                label.grid(row=sub_row, column=0, sticky="w", padx=5, pady=5)

                var_key = f"{section}.{key}"
                widget_type = widget_info["type"]

                if widget_type == "scale":
                    var = tk.DoubleVar()
                else:
                    var = tk.StringVar()
                self.config_vars[var_key] = var

                widget = None
                if widget_type == "entry":
                    widget = ttk.Entry(labelframe, textvariable=var, width=40)
                elif widget_type == "spinbox":
                    widget = ttk.Spinbox(labelframe, textvariable=var, **widget_info["options"])
                elif widget_type == "combobox":
                    widget = ttk.Combobox(labelframe, textvariable=var, values=widget_info.get("options", []), state="readonly")
                elif widget_type == "scale":
                    scale_frame = ttk.Frame(labelframe)
                    widget = ttk.Scale(scale_frame, variable=var, orient="horizontal", **widget_info["options"])
                    value_label = ttk.Label(scale_frame, textvariable=var, width=5)
                    widget.pack(side="left", fill="x", expand=True)
                    value_label.pack(side="left", padx=5)
                    scale_frame.grid(row=sub_row, column=1, sticky="ew", padx=5)

                if widget and not isinstance(widget, ttk.Scale):
                    widget.grid(row=sub_row, column=1, sticky="ew", padx=5)

                labelframe.columnconfigure(1, weight=1)
                sub_row += 1

        save_button = ttk.Button(self.config_tab, text="Save Configuration", command=self.save_config)
        save_button.pack(side="bottom", pady=10, anchor="se")

    def load_config(self):
        try:
            with open(self.config_filepath, 'r') as f:
                self.config_data = yaml.safe_load(f)

            for section, settings in self.config_data.items():
                if section not in WIDGET_MAP: continue
                for key, value in settings.items():
                    var_key = f"{section}.{key}"
                    if var_key in self.config_vars:
                        self.config_vars[var_key].set(value)

            self.master.title(f"AI Voicebot Control Panel - {os.path.basename(self.config_filepath)}")
        except FileNotFoundError:
            messagebox.showerror("Error", f"Config file not found: {self.config_filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load or parse config file:\n{e}")

    def save_config(self):
        for var_key, var in self.config_vars.items():
            section, key = var_key.split('.')
            if section not in self.config_data: self.config_data[section] = {}

            try:
                original_value = self.config_data[section].get(key)
                new_value_str = var.get()

                if isinstance(original_value, bool):
                    value = new_value_str.lower() in ['true', '1', 't', 'y', 'yes']
                elif isinstance(original_value, int):
                    value = int(float(new_value_str))
                elif isinstance(original_value, float):
                    value = float(new_value_str)
                else:
                    value = new_value_str
                self.config_data[section][key] = value
            except (ValueError, tk.TclError) as e:
                print(f"Could not convert value for {var_key}: {e}")
                self.config_data[section][key] = var.get()

        try:
            with open(self.config_filepath, 'w') as f:
                yaml.dump(self.config_data, f, default_flow_style=False, sort_keys=False)
            messagebox.showinfo("Success", f"Configuration saved successfully to {self.config_filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration file:\n{e}")

    def create_logs_tab_content(self):
        """Creates the content for the Logs tab, including a live log viewer."""
        log_frame = ttk.Frame(self.logs_tab)
        log_frame.pack(fill="both", expand=True)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_viewer = tk.Text(
            log_frame,
            state='disabled',
            wrap=tk.WORD,
            font=("Menlo", 10, "normal"),
            bg="#2E2E2E",
            fg="#D0D0D0",
            insertbackground="white",
            relief=tk.FLAT
        )

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_viewer.yview)
        self.log_viewer['yscrollcommand'] = scrollbar.set

        self.log_viewer.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Start the log tailing process
        self.log_file_path = "logs/voicebot.log"
        self._tail_log_file()

    def _tail_log_file(self):
        """
        Checks for new lines in the log file and adds them to the viewer.
        Schedules itself to run again to create a polling loop.
        """
        try:
            # Create log directory and file if they don't exist
            if not os.path.exists(self.log_file_path):
                os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)
                with open(self.log_file_path, 'a'): pass # touch the file

            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                # Seek to the last known position
                if not hasattr(self, '_last_log_pos'):
                    self._last_log_pos = 0
                f.seek(self._last_log_pos)

                new_lines = f.readlines()
                if new_lines:
                    self.log_viewer.config(state='normal')
                    for line in new_lines:
                        self.log_viewer.insert(tk.END, line)
                    self.log_viewer.config(state='disabled')
                    self.log_viewer.see(tk.END) # Auto-scroll

                self._last_log_pos = f.tell()
        except Exception as e:
            try:
                self.log_viewer.config(state='normal')
                self.log_viewer.insert(tk.END, f"\n--- Error reading log file: {e} ---\n")
                self.log_viewer.config(state='disabled')
            except tk.TclError: # If widget is destroyed
                return

        self.master.after(1000, self._tail_log_file) # Check every second


    def start_call(self):
        if self.bot_process and self.bot_process.poll() is None:
            messagebox.showwarning("Warning", "A bot process is already running.")
            return

        phone_number = self.phone_number_var.get()
        if not phone_number:
            messagebox.showerror("Error", "Phone number cannot be empty.")
            return

        # A simple check for E.164 format
        if not phone_number.startswith('+') or not phone_number[1:].isdigit():
            messagebox.showerror("Error", "Please enter a valid E.164 formatted phone number (e.g., +15551234567).")
            return

        # Disable start button, enable stop button
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_var.set(f"Status: Calling {phone_number}...")
        self.notebook.select(self.logs_tab) # Switch to logs tab

        # Run the bot script in a separate thread
        thread = threading.Thread(target=self._run_bot_process, args=(phone_number,), daemon=True)
        thread.start()

    def stop_call(self):
        if self.bot_process and self.bot_process.poll() is None:
            self.log_queue.put("--- Terminating bot process... ---\n")
            self.bot_process.terminate() # Send SIGTERM
            self.bot_process = None
        else:
            messagebox.showinfo("Info", "No bot process is currently running.")

        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_var.set("Status: Idle")

    def _run_bot_process(self, phone_number):
        """This method runs in a background thread."""
        script_path = "mac/call_with_bot.sh"
        if not os.path.exists(script_path):
            self.log_queue.put(f"ERROR: Orchestration script not found at {script_path}\n")
            self.stop_call() # Reset UI state
            return

        try:
            command = [script_path, phone_number]
            self.bot_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # Read and queue the output line by line
            for line in iter(self.bot_process.stdout.readline, ''):
                self.log_queue.put(line)

            self.bot_process.stdout.close()
            return_code = self.bot_process.wait()
            self.log_queue.put(f"\n--- Bot process finished with exit code {return_code} ---\n")

        except Exception as e:
            self.log_queue.put(f"\n--- ERROR running bot process: {e} ---\n")
        finally:
            # Signal the main thread to reset the UI
            self.log_queue.put(None)

    def _process_log_queue(self):
        """Checks the queue for log messages and updates the GUI."""
        try:
            while not self.log_queue.empty():
                message = self.log_queue.get_nowait()
                if message is None: # Sentinel value to reset UI
                    self.start_button.config(state=tk.NORMAL)
                    self.stop_button.config(state=tk.DISABLED)
                    self.status_var.set("Status: Finished")
                else:
                    self.log_viewer.config(state='normal')
                    self.log_viewer.insert(tk.END, message)
                    self.log_viewer.see(tk.END)
                    self.log_viewer.config(state='disabled')
        finally:
            self.master.after(100, self._process_log_queue)


if __name__ == '__main__':
    root = tk.Tk()
    app = Application(master=root)
    app.mainloop()
