from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Callable
from PIL import Image, ImageDraw, ImageFont


@lru_cache(maxsize=64)
def get_cached_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path, size)


class CertificateGenerator:
    def __init__(self, template_path: Path, font_path: Path):
        self.template_path = Path(template_path)
        self.font_path = Path(font_path)

        if not self.template_path.exists():
            raise FileNotFoundError(f"Шаблон не найден: {self.template_path}")
        if not self.font_path.exists():
            raise FileNotFoundError(f"Шрифт не найден: {self.font_path}")

    def _get_fitted_font(
        self, text: str, initial_size: int, max_width: int
    ) -> ImageFont.FreeTypeFont:
        current_size = initial_size
        font = get_cached_font(str(self.font_path), current_size)

        dummy_img = Image.new("RGB", (1, 1))
        draw = ImageDraw.Draw(dummy_img)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]

        # Теперь цикл работает мгновенно в памяти, без дискового I/O
        while text_width > max_width and current_size > 20:
            current_size -= 2
            font = get_cached_font(str(self.font_path), current_size)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]

        return font

    def render_single(
        self,
        name: str,
        base_font_size: int = 75,
        baseline_y: Optional[int] = 1140,
        target_x: Optional[int] = None,
        text_color: tuple[int, int, int] = (24, 43, 73),
    ) -> Image.Image:
        img = Image.open(self.template_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        img_width, img_height = img.size

        center_x = target_x if target_x is not None else (img_width // 2)
        target_y = baseline_y if baseline_y is not None else 1140

        max_allowed_width = int(img_width * 0.70)
        font = self._get_fitted_font(name, base_font_size, max_allowed_width)

        draw.text(
            (center_x, target_y),
            name,
            font=font,
            fill=text_color,
            anchor="ms"
        )
        return img

    def generate_batch_pdf(
        self,
        names: List[str],
        output_pdf_path: Path,
        base_font_size: int = 75,
        baseline_y: int = 1140,
        target_x: Optional[int] = None,
        text_color: tuple[int, int, int] = (24, 43, 73),
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        if not names:
            raise ValueError("Список имен пуст")

        rendered_pages: List[Image.Image] = []
        total = len(names)

        for idx, raw_name in enumerate(names, start=1):
            name = raw_name.strip()
            if not name:
                continue

            page = self.render_single(
                name=name,
                base_font_size=base_font_size,
                baseline_y=baseline_y,
                target_x=target_x,
                text_color=text_color,
            )
            rendered_pages.append(page)

            if progress_callback:
                progress_callback(idx, total)

        if not rendered_pages:
            raise ValueError("Нет валидных имен для генерации")

        # Полиграфическое качество 300 DPI
        first_page = rendered_pages[0]
        other_pages = rendered_pages[1:]

        first_page.save(
            str(output_pdf_path),
            "PDF",
            resolution=300.0,
            save_all=True,
            append_images=other_pages,
        )