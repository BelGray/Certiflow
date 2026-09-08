import sys
from pathlib import Path
from ui.app import DiplomaApp

if __name__ == "__main__":

    BUNDLE_DIR = Path(__file__).resolve().parent

    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        USER_DIR = Path(sys.argv[0]).resolve().parent
    else:
        USER_DIR = BUNDLE_DIR

    app = DiplomaApp(bundle_dir=BUNDLE_DIR, user_dir=USER_DIR)
    app.mainloop()