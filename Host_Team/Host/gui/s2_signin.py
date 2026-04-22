"""
s2_signin.py
------------
Compatibility entrypoint for the sign-in stage.
Delegates all logic to the PyQt6 implementation in signin.py.
"""

import sys
from PyQt6.QtWidgets import QApplication
from signin import SplashConfig, create_signin_window

__all__ = ["SplashConfig", "create_signin_window"]

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = create_signin_window()
    win.show()
    sys.exit(app.exec())
