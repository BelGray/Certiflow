import sys
from pathlib import Path
from ui.app import DiplomaApp

if __name__ == "__main__":

    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        BASE_DIR = Path(sys.argv[0]).resolve().parent
    else:
        BASE_DIR = Path(__file__).resolve().parent

    app = DiplomaApp(base_dir=BASE_DIR)
    app.mainloop()