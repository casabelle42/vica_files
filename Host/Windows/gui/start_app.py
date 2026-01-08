"""
Main application startup script.
Starts with the Available Devices window, which leads to the Query window.
"""

import sys
import os

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtWidgets import QApplication
from Host.gui.availibleDevices import MainWindow as AvailableDevicesWindow


def main():
    """Start the application with the Available Devices window."""
    app = QApplication(sys.argv)
    
    # Create and show the Available Devices window
    # This is the main entry point - users click "Query" button to open Query window
    devices_window = AvailableDevicesWindow()
    devices_window.show()
    
    print("="*60)
    print("Sentinel Nexus V2 - Application Started")
    print("="*60)
    print("Available Devices window is now open.")
    print("Click the 'Query' button to open the Query window.")
    print("Click the 'Exit' button to close the application.")
    print("="*60)
    
    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

