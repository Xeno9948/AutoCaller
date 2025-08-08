# bot/status_server.py
import logging
from flask import Flask, jsonify, request
from threading import Thread
from collections import deque
from typing import Dict, Any, Deque, List
from werkzeug.serving import make_server

log = logging.getLogger(__name__)

class StatusServer:
    """
    A simple Flask server that runs in a background thread to provide
    health checks and status information about the bot.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.port = self.config.get("server", {}).get("port", 8765)
        self.app = Flask(__name__)
        # Use a deque as a ring buffer for the most recent turns
        self.recent_turns: Deque[Dict[str, Any]] = deque(maxlen=20)
        self.server_thread: Thread = None
        self.server: make_server = None

        self._setup_routes()

    def _setup_routes(self):
        @self.app.route('/health', methods=['GET'])
        def health():
            log.debug("Health check endpoint requested.")
            return jsonify({
                "status": "ok",
                "recent_turn_count": len(self.recent_turns)
            })

        @self.app.route('/recent', methods=['GET'])
        def recent():
            log.debug("Recent turns endpoint requested.")
            # Return a snapshot of the current config and recent turns
            return jsonify({
                "config_snapshot": self.config,
                "recent_turns": list(self.recent_turns)
            })

        @self.app.before_request
        def log_request():
            # This is a bit noisy for DEBUG, but good for INFO
            if log.isEnabledFor(logging.DEBUG):
                log.debug(f"Flask Request: {request.method} {request.path} from {request.remote_addr}")

    def add_turn_data(self, turn_data: Dict[str, Any]):
        """
        Adds data from a completed conversation turn to the in-memory ring buffer.
        This method is thread-safe because deque appends are atomic.
        """
        self.recent_turns.append(turn_data)

    def start(self):
        """Starts the Flask server in a background thread."""
        if self.server_thread and self.server_thread.is_alive():
            log.warning("Status server is already running.")
            return

        log.info(f"Starting status server on http://0.0.0.0:{self.port}")

        # Use werkzeug's make_server for a more controllable server instance
        self.server = make_server('0.0.0.0', self.port, self.app, threaded=True)
        self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        log.info("Status server started in a background thread.")

    def stop(self):
        """Stops the Flask server gracefully."""
        if self.server:
            log.info("Stopping status server...")
            self.server.shutdown()
            self.server = None
        if self.server_thread:
            self.server_thread.join(timeout=2)
            if self.server_thread.is_alive():
                log.warning("Status server thread did not stop in time.")
            self.server_thread = None
        log.info("Status server stopped.")
