import os
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
from PIL import Image, ImageTk
import customtkinter as ctk

from core import __version__, __app_name__

from core.generator import CertificateGenerator
from core.config import ConfigManager
from core.utils import (
    normalize_name,
    hex_to_rgb,
    sanitize_filename
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class DiplomaApp(ctk.CTk):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir

        self.config_mgr = ConfigManager(self.base_dir / "config.json", self.base_dir)
        self.cfg = self.config_mgr.load()

        self.template_path = Path(self.cfg["template_path"])
        self.font_path = Path(self.cfg["font_path"])
        self.output_dir = Path(self.cfg["output_dir"])
        self.current_color_hex = str(self.cfg.get("text_color", "#182B49"))

        self.right_col_width = int(self.cfg.get("right_col_width", 420))

        # Генератор и кэш полноразмерного рендера в RAM
        self.generator: CertificateGenerator | None = None
        self._current_rendered_cert: Image.Image | None = None
        self._photo_ref: ImageTk.PhotoImage | None = None
        self._canvas_img_id: int | None = None

        self._init_generator()

        # Высокопроизводительные переменные сплиттера
        self._is_dragging_divider = False
        self._drag_start_x = 0
        self._start_col_width = self.right_col_width
        self._pending_mouse_x = 0
        self._last_applied_width = self.right_col_width
        self._drag_throttle_job: str | None = None
        self._preview_debounce_job: str | None = None

        self.name_rows: list[tuple[ctk.CTkFrame, ctk.CTkEntry]] = []
        self.is_advanced_open = False

        self.title(f"{__app_name__} v{__version__}")
        self.geometry("940x740")
        self.minsize(820, 660)

        self._build_ui()
        self._update_rendered_cache()

    def _init_generator(self):
        try:
            self.generator = CertificateGenerator(self.template_path, self.font_path)
        except Exception:
            self.generator = None

    def _build_ui(self):
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=20, pady=(10, 2))

        ctk.CTkLabel(
            top_bar,
            text="Выдача грамот",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")

        self.main_layout = ctk.CTkFrame(self, fg_color="transparent")
        self.main_layout.pack(fill="both", expand=True, padx=20, pady=4)

        # ЛЕВАЯ КОЛОНКА
        self.left_col = ctk.CTkFrame(self.main_layout, corner_radius=12)
        self.left_col.pack(side="left", fill="both", expand=True)

        names_header = ctk.CTkFrame(self.left_col, fg_color="transparent")
        names_header.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(names_header, text="Награждаемые:", font=ctk.CTkFont(weight="bold")).pack(side="left")

        ctk.CTkButton(
            names_header, text="📋 Список имён из буфера", width=95, height=28,
            fg_color="#1F6FEB", hover_color="#388BFD",
            command=self._paste_from_clipboard, font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            names_header, text="➕ Имя", width=65, height=28,
            command=lambda: self._add_name_row(), font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="right")

        self.scroll_names = ctk.CTkScrollableFrame(self.left_col, corner_radius=8)
        self.scroll_names.pack(padx=10, pady=(0, 6), fill="both", expand=True)

        for _ in range(3):
            self._add_name_row()

        # Чекбоксы
        chk_frame = ctk.CTkFrame(self.left_col, fg_color="transparent")
        chk_frame.pack(fill="x", padx=12, pady=(2, 6))

        self.chk_format_var = ctk.BooleanVar(value=self.cfg.get("auto_format", True))
        self.chk_format = ctk.CTkCheckBox(
            chk_frame, text="Форматировать ФИО (иванов иван → Иванов Иван)",
            variable=self.chk_format_var, font=ctk.CTkFont(size=11),
            command=self._save_current_config
        )
        self.chk_format.pack(side="left", padx=(0, 15))

        self.chk_open_var = ctk.BooleanVar(value=self.cfg.get("auto_open", True))
        self.chk_open = ctk.CTkCheckBox(
            chk_frame, text="Открыть PDF после создания",
            variable=self.chk_open_var, font=ctk.CTkFont(size=11),
            command=self._save_current_config
        )
        self.chk_open.pack(side="left")

        # Прогресс
        self.progress_bar = ctk.CTkProgressBar(self.left_col)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=12, pady=(2, 2))

        self.lbl_status = ctk.CTkLabel(
            self.left_col, text="Готов к работе", text_color="gray", font=ctk.CTkFont(size=11)
        )
        self.lbl_status.pack(pady=(0, 4))

        self.btn_generate = ctk.CTkButton(
            self.left_col,
            text="Собрать PDF",
            command=self._start_generation_thread,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            fg_color="#2EA043",
            hover_color="#238636"
        )
        self.btn_generate.pack(fill="x", padx=12, pady=(0, 12))

        # ДИНАМИЧЕСКИЙ РАЗДЕЛИТЕЛЬ
        self.divider = ctk.CTkFrame(
            self.main_layout,
            width=6,
            fg_color="#30363D",
            cursor="size_we",
            corner_radius=3
        )
        self.divider.pack(side="left", fill="y", padx=5)

        self.divider.bind("<Enter>", lambda e: self.divider.configure(fg_color="#58A6FF"))
        self.divider.bind("<Leave>", lambda e: self.divider.configure(fg_color="#30363D") if not self._is_dragging_divider else None)
        self.divider.bind("<ButtonPress-1>", self._on_divider_press)
        self.divider.bind("<B1-Motion>", self._on_divider_drag)
        self.divider.bind("<ButtonRelease-1>", self._on_divider_release)
        # Двойной клик для мгновенного сброса ширины:
        self.divider.bind("<Double-Button-1>", lambda e: self._reset_divider_width())

        # ПРАВАЯ КОЛОНКА
        self.right_col = ctk.CTkFrame(
            self.main_layout,
            width=self.right_col_width,
            corner_radius=12
        )
        self.right_col.pack(side="right", fill="both")
        self.right_col.pack_propagate(False)

        ctk.CTkLabel(
            self.right_col, text="Живой предпросмотр", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(pady=(8, 4))

        self.preview_canvas = tk.Canvas(
            self.right_col,
            bg="#161B22",
            highlightthickness=0,
            bd=0
        )
        self.preview_canvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.preview_canvas.bind("<Configure>", self._on_canvas_configure)

        # 3. Кнопка настроек
        self.btn_toggle_advanced = ctk.CTkButton(
            self, text="⚙ Продвинутые настройки ▼",
            command=self._toggle_advanced,
            fg_color="transparent", text_color="#8B949E", hover_color="#21262D",
            font=ctk.CTkFont(size=12)
        )
        self.btn_toggle_advanced.pack(pady=(2, 0))

        self._build_advanced_frame()

        # 4. Футер
        footer = ctk.CTkFrame(self, fg_color="transparent", height=24)
        footer.pack(side="bottom", fill="x", padx=20, pady=(2, 6))

        # Левая часть футера: контакты разработчика
        lbl_author = ctk.CTkLabel(footer, text="Разработчик ПО:", font=ctk.CTkFont(size=11), text_color="gray")
        lbl_author.pack(side="left", padx=(0, 5))

        lbl_tg = ctk.CTkLabel(
            footer, text="Telegram: @bel_gray", font=ctk.CTkFont(size=11, underline=True),
            text_color="#58A6FF", cursor="hand2"
        )
        lbl_tg.pack(side="left", padx=5)
        lbl_tg.bind("<Button-1>", lambda e: webbrowser.open("https://t.me/bel_gray"))

        lbl_mail = ctk.CTkLabel(
            footer, text="Почта: belg186@yandex.ru", font=ctk.CTkFont(size=11, underline=True),
            text_color="#58A6FF", cursor="hand2"
        )
        lbl_mail.pack(side="left", padx=5)
        lbl_mail.bind("<Button-1>", lambda e: webbrowser.open("mailto:belg186@yandex.ru"))

        lbl_mail = ctk.CTkLabel(
            footer, text="GitHub: BelGray", font=ctk.CTkFont(size=11, underline=True),
            text_color="#58A6FF", cursor="hand2"
        )
        lbl_mail.pack(side="left", padx=5)
        lbl_mail.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/BelGray/"))

        # Правая часть футера: версия сборки
        lbl_version = ctk.CTkLabel(
            footer,
            text=f"v{__version__}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#8B949E"
        )
        lbl_version.pack(side="right", padx=(0, 5))

        lbl_mail = ctk.CTkLabel(
            footer, text="\"Как этим пользоваться?\"", font=ctk.CTkFont(size=11, underline=True),
            text_color="#8B949E", cursor="hand2"
        )
        lbl_mail.pack(side="right", padx=5)
        lbl_mail.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/BelGray/SchoolDiplomaGenerator/blob/main/README.md"))

        lbl_mail = ctk.CTkLabel(
            footer, text="Скачать последнюю версию", font=ctk.CTkFont(size=11, underline=True),
            text_color="#8B949E", cursor="hand2"
        )
        lbl_mail.pack(side="right", padx=5)
        lbl_mail.bind("<Button-1>", lambda e: webbrowser.open(
            "https://github.com/BelGray/SchoolDiplomaGenerator/releases/latest"))

    # =========================================================================
    # ВЫСОКОПРОИЗВОДИТЕЛЬНЫЙ РАЗДЕЛИТЕЛЬ (Паттерн Event Coalescing)
    # =========================================================================

    def _on_divider_press(self, event):
        self._is_dragging_divider = True
        self._drag_start_x = event.x_root
        self._start_col_width = self.right_col.winfo_width()
        self._last_applied_width = self._start_col_width
        self._pending_mouse_x = event.x_root
        self.divider.configure(fg_color="#58A6FF")

    def _on_divider_drag(self, event):
        # 1. Мгновенно сохраняем координату мыши (тратится 0.001 мс)
        self._pending_mouse_x = event.x_root

        # 2. Троттлинг: если кадр уже запланирован — игнорируем спам событий мыши
        if self._drag_throttle_job is None:
            self._drag_throttle_job = self.after(20, self._apply_throttled_drag)

    def _apply_throttled_drag(self):
        """Выполняется строго с фиксированной частотой (~45-50 FPS) без перегрузки CPU."""
        self._drag_throttle_job = None
        if not self._is_dragging_divider:
            return

        delta = self._pending_mouse_x - self._drag_start_x
        new_width = self._start_col_width - delta

        max_limit = int(self.winfo_width() * 0.70)
        new_width = max(220, min(max_limit, new_width))

        # Фильтр микро-дребезга (если сдвиг меньше 3px — не тратим ресурсы)
        if abs(new_width - self._last_applied_width) < 3:
            return

        self._last_applied_width = new_width
        self.right_col_width = new_width
        self.right_col.configure(width=new_width)

        # Быстро обновляем Canvas
        self._redraw_canvas_viewport(fast_mode=True)

    def _on_divider_release(self, event):
        if self._drag_throttle_job is not None:
            self.after_cancel(self._drag_throttle_job)
            self._drag_throttle_job = None

        self._is_dragging_divider = False
        self.divider.configure(fg_color="#30363D")
        self._save_current_config()
        # Финальный качественный рендер
        self._redraw_canvas_viewport(fast_mode=False)

    def _reset_divider_width(self):
        """Двойной клик сбрасывает ширину до удобных 420px."""
        self.right_col_width = 420
        self.right_col.configure(width=420)
        self._redraw_canvas_viewport(fast_mode=False)
        self._save_current_config()

    def _on_canvas_configure(self, event):
        if not self._is_dragging_divider:
            self._redraw_canvas_viewport(fast_mode=False)

    # =========================================================================
    # ДВУХУРОВНЕВЫЙ КОНВЕЙЕР РЕНДЕРИНГА
    # =========================================================================

    def _schedule_live_preview(self):
        if self._preview_debounce_job is not None:
            self.after_cancel(self._preview_debounce_job)
        self._preview_debounce_job = self.after(50, self._update_rendered_cache)

    def _update_rendered_cache(self):
        """Рендерит полноразмерную грамоту в RAM только при изменении параметров."""
        self._preview_debounce_job = None
        if self.generator is None:
            return

        try:
            sample_name = "Иванов Иван"
            for _, entry in self.name_rows:
                val = entry.get().strip()
                if val:
                    sample_name = normalize_name(val) if self.chk_format_var.get() else val
                    break

            raw_y = self.entry_y.get().strip()
            baseline_y = int(raw_y) if raw_y.isdigit() else 765

            raw_size = self.entry_size.get().strip()
            font_size = int(raw_size) if raw_size.isdigit() else 75

            raw_x = self.entry_x.get().strip()
            target_x = int(raw_x) if raw_x.isdigit() else None

            rgb_color = hex_to_rgb(self.current_color_hex)

            self._current_rendered_cert = self.generator.render_single(
                name=sample_name,
                base_font_size=font_size,
                baseline_y=baseline_y,
                target_x=target_x,
                text_color=rgb_color
            )
            self._redraw_canvas_viewport(fast_mode=False)
        except Exception:
            pass

    def _redraw_canvas_viewport(self, fast_mode: bool = False):
        """Сверхбыстрое масштабирование и перерисовка Canvas без создания/удаления объектов."""
        if self._current_rendered_cert is None:
            self.preview_canvas.delete("all")
            self._canvas_img_id = None
            self.preview_canvas.create_text(
                120, 100, text="Загрузка шаблона...", fill="gray", font=("Arial", 12)
            )
            return

        try:
            cw = self.preview_canvas.winfo_width()
            ch = self.preview_canvas.winfo_height()

            if cw <= 20 or ch <= 20:
                return

            avail_w = max(10, cw - 16)
            avail_h = max(10, ch - 16)

            img_w, img_h = self._current_rendered_cert.size

            scale = min(avail_w / img_w, avail_h / img_h)
            target_w = max(10, int(img_w * scale))
            target_h = max(10, int(img_h * scale))

            resample_filter = Image.Resampling.NEAREST if fast_mode else Image.Resampling.BILINEAR
            thumb = self._current_rendered_cert.resize((target_w, target_h), resample_filter)

            self._photo_ref = ImageTk.PhotoImage(thumb)

            center_x = cw // 2
            center_y = ch // 2

            # Высокопроизводительное обновление: не удаляем объект, а меняем координаты и картинку!
            if self._canvas_img_id is None:
                self.preview_canvas.delete("all")
                self._canvas_img_id = self.preview_canvas.create_image(
                    center_x, center_y, anchor="center", image=self._photo_ref
                )
            else:
                self.preview_canvas.coords(self._canvas_img_id, center_x, center_y)
                self.preview_canvas.itemconfigure(self._canvas_img_id, image=self._photo_ref)

        except Exception:
            pass

    # =========================================================================
    # ОСТАЛЬНАЯ ЛОГИКА
    # =========================================================================

    def _build_advanced_frame(self):
        self.advanced_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#161B22")

        row1 = ctk.CTkFrame(self.advanced_frame, fg_color="transparent")
        row1.pack(padx=12, pady=6, fill="x")

        ctk.CTkButton(
            row1, text="📄 Импорт ФИО из .txt", command=self._import_from_txt,
            fg_color="#30363D", hover_color="#484F58", width=120
        ).pack(side="left", padx=(0, 5))

        self.btn_tpl = ctk.CTkButton(row1, text="Шаблон грамоты", command=self._select_template, width=120)
        self.btn_tpl.pack(side="left", padx=5)

        self.btn_font = ctk.CTkButton(row1, text="Шрифт", command=self._select_font, width=120)
        self.btn_font.pack(side="left", padx=5)

        self.btn_color = ctk.CTkButton(
            row1, text="Цвет текста", command=self._pick_text_color,
            fg_color=self.current_color_hex, width=100, text_color="white"
        )
        self.btn_color.pack(side="right", padx=(5, 0))

        row2 = ctk.CTkFrame(self.advanced_frame, fg_color="transparent")
        row2.pack(padx=12, pady=4, fill="x")

        ctk.CTkLabel(row2, text="X (положение текста по горизонтали):", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 2))
        self.entry_x = ctk.CTkEntry(row2, width=65)
        self.entry_x.insert(0, str(self.cfg.get("coord_x", "Авто")))
        self.entry_x.pack(side="left", padx=(0, 10))
        self.entry_x.bind("<KeyRelease>", lambda e: self._schedule_live_preview())

        ctk.CTkLabel(row2, text="Y (положение текста по вертикали):", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 2))
        self.entry_y = ctk.CTkEntry(row2, width=60)
        self.entry_y.insert(0, str(self.cfg.get("baseline_y", 765)))
        self.entry_y.pack(side="left", padx=(0, 10))
        self.entry_y.bind("<KeyRelease>", lambda e: self._schedule_live_preview())

        ctk.CTkLabel(row2, text="Размер текста:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 2))
        self.entry_size = ctk.CTkEntry(row2, width=55)
        self.entry_size.insert(0, str(self.cfg.get("font_size", 75)))
        self.entry_size.pack(side="left", padx=(0, 10))
        self.entry_size.bind("<KeyRelease>", lambda e: self._schedule_live_preview())

        row3 = ctk.CTkFrame(self.advanced_frame, fg_color="transparent")
        row3.pack(padx=12, pady=(4, 8), fill="x")

        ctk.CTkLabel(row3, text="Имя файла:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self.entry_filename = ctk.CTkEntry(row3, width=170)
        self.entry_filename.insert(0, str(self.cfg.get("pdf_name", "Грамоты")))
        self.entry_filename.pack(side="left", padx=(0, 10))

        self.btn_out = ctk.CTkButton(
            row3, text=f"Папка сохранения: {self.output_dir.name}/", command=self._select_output_dir,
            fg_color="#21262D", hover_color="#30363D", font=ctk.CTkFont(size=11)
        )
        self.btn_out.pack(side="right", fill="x", expand=True)

    def _add_name_row(self, name_text: str = ""):
        row_frame = ctk.CTkFrame(self.scroll_names, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)

        entry = ctk.CTkEntry(row_frame, placeholder_text="ФИО ученика...")
        if name_text:
            entry.insert(0, name_text)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        if len(self.name_rows) == 0:
            entry.bind("<KeyRelease>", lambda e: self._schedule_live_preview())

        del_btn = ctk.CTkButton(
            row_frame, text="✕", width=28, height=28,
            fg_color="#DA3633", hover_color="#B62324",
            command=lambda rf=row_frame, e=entry: self._remove_name_row(rf, e)
        )
        del_btn.pack(side="right")
        self.name_rows.append((row_frame, entry))

    def _remove_name_row(self, row_frame: ctk.CTkFrame, entry: ctk.CTkEntry):
        row_frame.destroy()
        self.name_rows = [item for item in self.name_rows if item[1] != entry]
        if self.name_rows:
            self.name_rows[0][1].bind("<KeyRelease>", lambda e: self._schedule_live_preview())
        self._schedule_live_preview()

    def _paste_from_clipboard(self):
        try:
            raw_clipboard = self.clipboard_get()
        except Exception:
            messagebox.showwarning("Буфер пуст", "В буфере обмена нет текста!")
            return

        lines = [line.strip() for line in raw_clipboard.splitlines() if line.strip()]
        if not lines:
            return

        if all(not entry.get().strip() for _, entry in self.name_rows):
            for rf, _ in self.name_rows:
                rf.destroy()
            self.name_rows.clear()

        for line in lines:
            formatted = normalize_name(line) if self.chk_format_var.get() else line
            self._add_name_row(formatted)

        self._schedule_live_preview()
        messagebox.showinfo("Успех", f"Вставлено участников: {len(lines)}")

    def _import_from_txt(self):
        f = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not f:
            return
        try:
            try:
                with open(f, "r", encoding="utf-8") as file:
                    lines = [l.strip() for l in file if l.strip()]
            except UnicodeDecodeError:
                with open(f, "r", encoding="cp1251") as file:
                    lines = [l.strip() for l in file if l.strip()]

            if all(not entry.get().strip() for _, entry in self.name_rows):
                for rf, _ in self.name_rows:
                    rf.destroy()
                self.name_rows.clear()

            for line in lines:
                formatted = normalize_name(line) if self.chk_format_var.get() else line
                self._add_name_row(formatted)

            self._schedule_live_preview()
            messagebox.showinfo("Импорт завершен", f"Загружено: {len(lines)}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочесть файл:\n{e}")

    def _pick_text_color(self):
        color = colorchooser.askcolor(initialcolor=self.current_color_hex, title="Выберите цвет текста на грамотах")
        if color and color[1]:
            self.current_color_hex = color[1]
            self.btn_color.configure(fg_color=self.current_color_hex)
            self._save_current_config()
            self._schedule_live_preview()

    def _toggle_advanced(self):
        if self.is_advanced_open:
            self.advanced_frame.pack_forget()
            self.btn_toggle_advanced.configure(text="⚙ Продвинутые настройки ▼")
            self.is_advanced_open = False
        else:
            self.advanced_frame.pack(padx=20, pady=(2, 6), fill="x", before=self.btn_toggle_advanced)
            self.btn_toggle_advanced.configure(text="⚙ Скрыть продвинутые настройки ▲")
            self.is_advanced_open = True

    def _select_template(self):
        f = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if f:
            self.template_path = Path(f)
            self._init_generator()
            self._schedule_live_preview()
            self._save_current_config()

    def _select_font(self):
        f = filedialog.askopenfilename(filetypes=[("Fonts", "*.ttf *.otf")])
        if f:
            self.font_path = Path(f)
            self._init_generator()
            self._schedule_live_preview()
            self._save_current_config()

    def _select_output_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.output_dir = Path(d)
            self.btn_out.configure(text=f"Папка: {self.output_dir.name}/")
            self._save_current_config()

    def _save_current_config(self):
        data = {
            "template_path": str(self.template_path),
            "font_path": str(self.font_path),
            "output_dir": str(self.output_dir),
            "font_size": int(self.entry_size.get().strip()) if self.entry_size.get().strip().isdigit() else 75,
            "baseline_y": int(self.entry_y.get().strip()) if self.entry_y.get().strip().isdigit() else 765,
            "coord_x": self.entry_x.get().strip(),
            "pdf_name": self.entry_filename.get().strip(),
            "text_color": self.current_color_hex,
            "auto_format": self.chk_format_var.get(),
            "auto_open": self.chk_open_var.get(),
            "right_col_width": self.right_col_width,
        }
        self.config_mgr.save(data)

    def _start_generation_thread(self):
        raw_names = [entry.get().strip() for _, entry in self.name_rows if entry.get().strip()]
        if not raw_names:
            messagebox.showwarning("Внимание", "Добавьте хотя бы одно имя!")
            return

        if self.chk_format_var.get():
            names = [normalize_name(n) for n in raw_names]
        else:
            names = raw_names

        raw_x = self.entry_x.get().strip()
        target_x = int(raw_x) if raw_x.isdigit() else None

        try:
            baseline_y = int(self.entry_y.get().strip())
            font_size = int(self.entry_size.get().strip())
        except ValueError:
            messagebox.showerror("Ошибка", "Y и размер шрифта должны быть числами!")
            return

        self._save_current_config()

        clean_name = sanitize_filename(self.entry_filename.get())
        output_pdf = self.output_dir / clean_name

        self.btn_generate.configure(state="disabled")
        self.lbl_status.configure(text="Рендеринг (300 DPI)...")

        rgb_color = hex_to_rgb(self.current_color_hex)

        threading.Thread(
            target=self._run_generation,
            args=(names, output_pdf, font_size, baseline_y, target_x, rgb_color),
            daemon=True
        ).start()

    def _run_generation(
        self,
        names: list[str],
        output_pdf: Path,
        font_size: int,
        baseline_y: int,
        target_x: int | None,
        rgb_color: tuple[int, int, int]
    ):
        try:
            generator = CertificateGenerator(
                template_path=self.template_path,
                font_path=self.font_path
            )

            def thread_progress(current: int, total: int):
                self.after(0, self._on_progress, current, total)

            generator.generate_batch_pdf(
                names=names,
                output_pdf_path=output_pdf,
                base_font_size=font_size,
                baseline_y=baseline_y,
                target_x=target_x,
                text_color=rgb_color,
                progress_callback=thread_progress
            )

            self.after(0, self._on_success, output_pdf, len(names))

        except Exception as e:
            self.after(0, self._on_error, str(e))

    def _on_progress(self, current: int, total: int):
        self.progress_bar.set(current / total)
        self.lbl_status.configure(text=f"Стр. {current} из {total}...")

    def _on_success(self, output_pdf: Path, count: int):
        self.btn_generate.configure(state="normal")
        self.lbl_status.configure(text="Готово!")
        messagebox.showinfo("Успех", f"Файл сохранен ({count} стр.):\n{output_pdf}")

        if self.chk_open_var.get():
            try:
                os.startfile(output_pdf)
            except Exception:
                pass

    def _on_error(self, error_msg: str):
        self.btn_generate.configure(state="normal")
        self.lbl_status.configure(text="Ошибка")
        messagebox.showerror("Ошибка генерации", error_msg)