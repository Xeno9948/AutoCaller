# run_gui.py
import sys
import os
import tkinter as tk

# Add project root to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from gui.app import Application

def main():
    """
    Main entry point for the GUI application.
    """
    root = tk.Tk()
    app = Application(master=root)
    app.mainloop()

if __name__ == '__main__':
    main()
