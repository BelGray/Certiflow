import json
from pathlib import Path
from typing import Any, Dict


class ConfigManager:
    def __init__(self, config_file: Path, base_dir: Path):
        self.config_file = config_file
        self.base_dir = base_dir

        self.defaults: Dict[str, Any] = {
            "template_path": "DEFAULT",
            "font_path": "DEFAULT",
            "output_dir": str(self.base_dir),
            "font_size": 80,
            "baseline_y": 1140,
            "coord_x": "Авто",
            "pdf_name": "Грамоты",
            "text_color": "#182B49",
            "auto_format": True,
            "auto_open": True,
            "right_col_width": 420,
        }

    def load(self) -> Dict[str, Any]:
        if not self.config_file.exists():
            return self.defaults.copy()
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config = self.defaults.copy()
                config.update(saved)
                return config
        except Exception:
            return self.defaults.copy()

    def save(self, data: Dict[str, Any]) -> None:
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Не удалось сохранить конфиг: {e}")