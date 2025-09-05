import arcade
import os
import arcade.gui
from dataclasses import dataclass
from pathlib import Path
from pyglet.window import key
from PIL import Image
import pyglet
import math

def draw_fullscreen_texture(window: arcade.Window, texture: arcade.Texture):
    w, h = window.width, window.height

    # 1) Классика (arcade 2.x–ранние 3.x)
    if hasattr(arcade, "draw_texture_rectangle"):
        arcade.draw_texture_rectangle(w // 2, h // 2, w, h, texture)
        return

    # 2) Вариант с LBWH (часть 3.x)
    if hasattr(arcade, "draw_lrwh_rectangle_textured"):
        arcade.draw_lrwh_rectangle_textured(0, 0, w, h, texture)
        return

    # 3) Новый API: draw_texture_rect(texture, LBWH)
    if hasattr(arcade, "draw_texture_rect"):
        try:
            # на всякий случай попробуем "старую" сигнатуру (если вдруг есть)
            arcade.draw_texture_rect(w // 2, h // 2, w, h, texture)  # может бросить TypeError
        except TypeError:
            LBWH = getattr(arcade, "LBWH", None)
            if LBWH is not None:
                arcade.draw_texture_rect(texture, LBWH(0, 0, w, h))
            else:
                # запасной путь через спрайт
                spr = arcade.Sprite(center_x=w // 2, center_y=h // 2, texture=texture)
                spr.width, spr.height = w, h
                spr.draw()
        return

    # 4) Последний запасной путь — спрайт (должен работать везде)
    spr = arcade.Sprite(center_x=w // 2, center_y=h // 2, texture=texture)
    spr.width, spr.height = w, h
    spr.draw()

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
SPRITES_DIR = ASSETS_DIR / "sprites"
LEVELS = [
    "assets/maps/lvl1.json",
    "assets/maps/lvl2.json",
    "assets/maps/lvl3.json"
]

# === Константы окна ===
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 900
TILE_SCALING = 1
# === Базовые значения геймплея (могут меняться настройками) ===
PLAYER_MOVE_SPEED = 3
PLAYER_JUMP_SPEED = 2
GRAVITY = 1.35
PLAYER_ACCELERATION = 0.5   # как быстро разгоняется
PLAYER_FRICTION = 0.1       # как быстро тормозит (0 = резкая остановка)
# --- Константы управления ---
PLAYER_SPEED = 3      # скорость движения влево/вправо
JUMP_SPEED = 0.5     # сила прыжка
REQUIRE_GEMS = True
MAX_JUMPS = 2

# Клавиши по умолчанию
DEFAULT_KEYS = {
    "fire": {"left": arcade.key.LEFT, "right": arcade.key.RIGHT, "jump": arcade.key.UP},
    "water": {"left": arcade.key.A, "right": arcade.key.D, "jump": arcade.key.W},
}
@dataclass
class GameConfig:
    difficulty: str = "Нормальная"
    sound_on: bool = True
    show_hints: bool = True

class AudioManager:
    def __init__(self):
        self.menu_music = None
        self.game_music = None
        self.current_player = None
        self.sound_on = True

    def play_music(self, path, loop=True):
        if not self.sound_on:
            return
        if self.current_player:
            self.current_player.pause()
            self.current_player.delete()
            self.current_player = None

        sound = arcade.Sound(path, streaming=True)
        self.current_player = sound.play(loop=loop)
        return sound

    def stop(self):
        if self.current_player:
            self.current_player.pause()
            self.current_player.delete()
            self.current_player = None

    def set_sound(self, enabled: bool):
        self.sound_on = enabled
        if not enabled:
            self.stop()

def apply_config(cfg: GameConfig):
    global PLAYER_MOVE_SPEED, PLAYER_JUMP_SPEED, GRAVITY
    if cfg.difficulty == "Лёгкая":
        PLAYER_MOVE_SPEED = 4
        PLAYER_JUMP_SPEED = 10
        GRAVITY = 0.5
    elif cfg.difficulty == "Сложная":
        PLAYER_MOVE_SPEED = 6
        PLAYER_JUMP_SPEED = 12
        GRAVITY = 0.5
    else:
        PLAYER_MOVE_SPEED = 5
        PLAYER_JUMP_SPEED = 11
        GRAVITY = 0.5

# === Игровые классы ===
class Player(arcade.Sprite):
    def __init__(self, image, scale, controls):
        super().__init__(image, scale)
        self.controls = controls
        self.change_x = 0
        self.change_y = 0
        self.max_speed = 3  # максимальная скорость по X
        self.acceleration = 0.4  # ускорение
        self.friction = 3  # замедление
        self.jump_strength = 13  # сила прыжка
        self.can_jump = False

    def update_movement(self, keys: pyglet.window.key.KeyStateHandler):
        # --- Горизонтальное движение ---
        if keys[self.controls["left"]]:
            self.change_x -= PLAYER_ACCELERATION
        elif keys[self.controls["right"]]:
            self.change_x += PLAYER_ACCELERATION
        else:
            # трение — плавное замедление
            if abs(self.change_x) > PLAYER_FRICTION:
                self.change_x -= PLAYER_FRICTION * (1 if self.change_x > 0 else -1)
            else:
                self.change_x = 0

        # Ограничиваем максимальную скорость
        if self.change_x > PLAYER_MOVE_SPEED:
            self.change_x = PLAYER_MOVE_SPEED
        elif self.change_x < -PLAYER_MOVE_SPEED:
            self.change_x = -PLAYER_MOVE_SPEED

        # --- Прыжок ---
        if keys[self.controls["jump"]] and self.can_jump:
            self.change_y = PLAYER_JUMP_SPEED
            self.can_jump = False

    def update(self, platforms: arcade.SpriteList, delta_time: float = 1 / 60):
        # Двигаем по X и Y
        self.center_x += self.change_x
        self.center_y += self.change_y
        self.change_y -= GRAVITY

        # Проверка коллизий с платформами
        hits = arcade.check_for_collision_with_list(self, platforms)
        if hits:
            # ставим игрока поверх платформы
            for platform in hits:
                if self.change_y <= 0:  # только если падали вниз
                    self.bottom = platform.top
                    self.change_y = 0
                    self.can_jump = True
        else:
            self.can_jump = False
class BaseUIView(arcade.View):
    """Базовый класс для всех экранов с UIManager'ом."""
    def __init__(self):
        super().__init__()
        self.ui = arcade.gui.UIManager()

    def on_show_view(self):
        self.ui.enable()
        self.ui.clear()  # вместо устаревшего purge()

    def on_hide_view(self):
        self.ui.disable()

    def on_draw(self):
        self.clear()
        self.ui.draw()

    def _anchor_center(self, widget: arcade.gui.UIWidget):
        """Оборачиваем виджет в центрирующий AnchorLayout и добавляем в UI."""
        anchor = arcade.gui.UIAnchorLayout()
        anchor.add(widget, anchor_x="center_x", anchor_y="center_y")
        self.ui.add(anchor)

class ImageButton(arcade.gui.UITextureButton):
    def __init__(self, normal_texture: arcade.Texture, scale: float = 2.0, **kwargs):
        super().__init__(texture=normal_texture, scale=scale, **kwargs)
        self.normal_texture = normal_texture


class SplashView(arcade.View):
    def __init__(self):
        super().__init__()
        # Загружаем картинку заставки
        self.background = arcade.load_texture("assets/Start.png")

    def on_draw(self):
        rect = arcade.LBWH(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)

        # ВАЖНО: сначала texture, потом rect
        arcade.draw_texture_rect(self.background, rect)
    def on_key_press(self, key, modifiers):
        # Переход в главное меню
        menu = MainMenuView()
        self.window.show_view(menu)

    def on_mouse_press(self, x, y, button, modifiers):
        # Переход в главное меню
        menu = MainMenuView()
        self.window.show_view(menu)

class MainMenuView(BaseUIView):
    def __init__(self):
        super().__init__()
        self.manager = arcade.gui.UIManager()

        # Загружаем фон
        self.background = arcade.load_texture("C:/gamr/assets/background.png")

        # Загружаем кнопки
        self.play_texture = arcade.load_texture("C:/gamr/assets/bg.png")
        self.settings_texture = arcade.load_texture("C:/gamr/assets/st.png")
        self.exit_texture = arcade.load_texture("C:/gamr/assets/ex.png")

    def on_show_view(self):
        self.manager.enable()
        self.manager.clear()
        super().on_show_view()
        # Меню-музыка
        self.window.audio.play_music("assets/music/menu.mp3")
        v_box = arcade.gui.UIBoxLayout(vertical=True, space_between=20)

        play_btn = ImageButton(self.play_texture, scale=0.4)
        settings_btn = ImageButton(self.settings_texture, scale=0.4)
        exit_btn = ImageButton(self.exit_texture, scale=0.4)

        play_btn.on_click = lambda e: self.window.show_view(LevelSelectView())
        settings_btn.on_click = lambda e: self.window.show_view(SettingsView())
        exit_btn.on_click = lambda e: arcade.exit()

        v_box.add(play_btn)
        v_box.add(settings_btn)
        v_box.add(exit_btn)

        anchor = arcade.gui.UIAnchorLayout()
        anchor.add(v_box, anchor_x="center_x", anchor_y="center_y")
        self.manager.add(anchor)

    def on_draw(self):
        self.clear()

        # Создаём прямоугольник LBWH (Left, Bottom, Width, Height)
        rect = arcade.LBWH(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)

        # ВАЖНО: сначала texture, потом rect
        arcade.draw_texture_rect(self.background, rect)

        # Рисуем кнопки
        self.manager.draw()


# ---------- ВЫБОР УРОВНЯ ----------
class LevelSelectView(BaseUIView):
    def __init__(self, return_to=None, bg_path="C:/gamr/assets/levels_bg.png"):
        super().__init__()
        self.manager = arcade.gui.UIManager()
        self.background = arcade.load_texture(bg_path)
        self.return_to = return_to

        # Сколько уровней показывать
        try:
            from fix import GameView
            self.level_count = len(getattr(GameView, "LEVELS", [])) or 3
        except Exception:
            self.level_count = 3

    def on_show_view(self):
        super().on_show_view()
        self.manager.enable()
        self.manager.clear()
        self.window.audio.play_music("assets/music/menu.mp3")
        v_box = arcade.gui.UIBoxLayout(space_between=10)

        # Заголовок

        # Кнопки уровней
        from fix import GameView  # если в том же файле — убери
        for i in range(1, self.level_count + 1):
            btn = arcade.gui.UIFlatButton(text=f"Уровень {i}", width=300, height=50)
            btn.on_click = (lambda e, lvl=i: self.window.show_view(GameView(level=lvl)))
            v_box.add(btn, space_around=(0, 0, 10, 0))

        # Кнопка "Назад"
        back = arcade.gui.UIFlatButton(text="Назад", width=300, height=50)
        back.on_click = lambda e: self.window.show_view(self.return_to or MainMenuView())
        v_box.add(back, space_around=(20, 0, 0, 0))

        # Центрируем блок
        anchor = arcade.gui.UIAnchorLayout()
        anchor.add(v_box, anchor_x="center_x", anchor_y="center_y")
        self.manager.add(anchor)

    def on_draw(self):
        self.clear()
        # Фон
        rect = arcade.LBWH(0, 0, self.window.width, self.window.height)
        arcade.draw_texture_rect(self.background, rect)
        # UI
        self.manager.draw()

    def on_hide_view(self):
        self.manager.disable()

# ---------- НАСТРОЙКИ ----------
class SettingsView(BaseUIView):
    def __init__(self, return_to=None, bg_path="C:/gamr/assets/settings_bg.png"):
        super().__init__()
        self.return_to = return_to

        # UIManager для виджетов
        self.manager = arcade.gui.UIManager()

        # Фон настроек
        self.background = arcade.load_texture(bg_path)

        # Кнопки
        self._btn_difficulty = None
        self._btn_sound = None
        self._btn_hints = None
        self._btn_back = None

    # --- вспомогательное: гарантируем наличие конфига ---
    def _ensure_config(self):
        if not hasattr(self.window, "game_config"):
            class _Cfg:
                difficulty = "Нормальная"
                sound_on = True
                show_hints = True
            self.window.game_config = _Cfg()

    # --- on_show_view: создаём и размещаем кнопки ---
    def on_show_view(self):
        # если в BaseUIView что-то важно (например, hotkey ESC), можно оставить:
        # super().on_show_view()

        self.manager.enable()
        self.manager.clear()
        super().on_show_view()
        # Меню-музыка
        self.window.audio.play_music("assets/music/menu.mp3")
        v_box = arcade.gui.UIBoxLayout(space_between=10)


        self._btn_difficulty = arcade.gui.UIFlatButton(text="", width=300, height=50)
        self._btn_difficulty.on_click = self._on_toggle_difficulty
        v_box.add(self._btn_difficulty)

        self._btn_sound = arcade.gui.UIFlatButton(text="", width=300, height=50)
        self._btn_sound.on_click = self._on_toggle_sound
        v_box.add(self._btn_sound)

        self._btn_hints = arcade.gui.UIFlatButton(text="", width=300, height=50)
        self._btn_hints.on_click = self._on_toggle_hints
        v_box.add(self._btn_hints)

        self._btn_back = arcade.gui.UIFlatButton(text="Назад", width=300, height=50)
        self._btn_back.on_click = self._go_back
        v_box.add(self._btn_back, space_around=(12, 0, 0, 0))

        anchor = arcade.gui.UIAnchorLayout()
        anchor.add(v_box, anchor_x="center_x", anchor_y="center_y")
        self.manager.add(anchor)

        self._ensure_config()
        self._refresh_labels()

    # --- подписи на кнопках из конфига ---
    def _refresh_labels(self, *_):
        self._ensure_config()
        cfg = self.window.game_config
        self._btn_difficulty.text = f"Сложность: {cfg.difficulty}"
        self._btn_sound.text = f"Звук: {'Вкл' if cfg.sound_on else 'Выкл'}"
        self._btn_hints.text = f"Подсказки: {'Вкл' if cfg.show_hints else 'Выкл'}"

    # --- обработчики ---
    def _on_toggle_difficulty(self, *_):
        self._ensure_config()
        cfg = self.window.game_config
        order = ["Лёгкая", "Нормальная", "Сложная"]
        try:
            idx = order.index(cfg.difficulty)
        except ValueError:
            idx = 1
        cfg.difficulty = order[(idx + 1) % len(order)]

        # если у тебя есть функция apply_config, вызовем её безопасно
        if "apply_config" in globals():
            try:
                apply_config(cfg)
            except Exception:
                pass

        self._refresh_labels()

    def _on_toggle_sound(self, *_):
        cfg: GameConfig = getattr(self.window, "game_config", GameConfig())
        cfg.sound_on = not cfg.sound_on
        setattr(self.window, "game_config", cfg)
        # переключаем музыку
        self.window.audio.set_sound(cfg.sound_on)
        self._refresh_labels()

    def _on_toggle_hints(self, *_):
        self._ensure_config()
        cfg = self.window.game_config
        cfg.show_hints = not cfg.show_hints
        self._refresh_labels()

    def _go_back(self, *_):
        if callable(self.return_to):
            self.window.show_view(self.return_to())
        elif isinstance(self.return_to, type) and issubclass(self.return_to, arcade.View):
            self.window.show_view(self.return_to())
        else:
            self.window.show_view(MainMenuView())

    # --- рендеринг ---
    def on_draw(self):
        self.clear()
        # фон растягиваем на весь экран — корректный способ для Arcade 3.3.2
        rect = arcade.LBWH(0, 0, self.window.width, self.window.height)
        arcade.draw_texture_rect(self.background, rect)
        self.manager.draw()

    def on_hide_view(self):
        self.manager.disable()

# ---------- ПАУЗА ----------
class PauseView(arcade.View):
    def __init__(self, game_view):
        super().__init__()
        self.game_view = game_view
        self.manager = arcade.gui.UIManager()

    def on_show_view(self):
        self.manager.enable()
        self.manager.clear()
        super().on_show_view()
        self.window.audio.play_music("assets/music/pause.mp3")
        v_box = arcade.gui.UIBoxLayout(space_between=10)
        v_box.add(arcade.gui.UILabel(text="ПАУЗА", font_size=22, bold=True))

        resume_btn = arcade.gui.UIFlatButton(text="Продолжить", width=300, height=50)
        resume_btn.on_click = lambda e: self.window.show_view(self.game_view)
        v_box.add(resume_btn)

        restart_btn = arcade.gui.UIFlatButton(text="Перезапуск уровня", width=300, height=50)
        restart_btn.on_click = lambda e: self.window.show_view(GameView(level=self.game_view.level_num))
        v_box.add(restart_btn)

        menu_btn = arcade.gui.UIFlatButton(text="Главное меню", width=300, height=50)
        menu_btn.on_click = lambda e: self.window.show_view(MainMenuView())
        v_box.add(menu_btn)

        anchor = arcade.gui.UIAnchorLayout()
        anchor.add(v_box, anchor_x="center_x", anchor_y="center_y")
        self.manager.add(anchor)

    def on_hide_view(self):
        self.manager.disable()

    def on_draw(self):
        # рисуем игру "под паузой"
        self.game_view.on_draw()
        arcade.draw_lrbt_rectangle_filled(0, SCREEN_WIDTH, 0, SCREEN_HEIGHT, (0, 0, 0, 150))
        self.manager.draw()



# ---------- ПОБЕДА ----------
class WinView(BaseUIView):
    def __init__(self, level_num: int, has_next: bool = True):
        super().__init__()
        self.level_num = level_num
        self.has_next = has_next

    def on_show_view(self):
        super().on_show_view()
        arcade.set_background_color(arcade.color.DARK_SPRING_GREEN)
        self.window.audio.play_music("assets/music/win.mp3")
        box = arcade.gui.UIBoxLayout(space_between=10)
        box.add(arcade.gui.UILabel(text="ПОБЕДА!", font_size=24, bold=True),
                space_around=(0, 0, 12, 0))

        if self.has_next:
            next_btn = arcade.gui.UIFlatButton(text="Следующий уровень", width=300, height=50)
            next_btn.on_click = lambda e: self.window.show_view(GameView(level=self.level_num + 1))
            box.add(next_btn)

        level_select = arcade.gui.UIFlatButton(text="Выбор уровня", width=300, height=50)
        level_select.on_click = lambda e: self.window.show_view(LevelSelectView())
        box.add(level_select)

        main_menu = arcade.gui.UIFlatButton(text="Главное меню", width=300, height=50)
        main_menu.on_click = lambda e: self.window.show_view(MainMenuView())
        box.add(main_menu)

        self._anchor_center(box)


# ---------- ПОРАЖЕНИЕ ----------
class LoseView(BaseUIView):
    def __init__(self, level_num: int):
        super().__init__()
        self.level_num = level_num

    def on_show_view(self):
        super().on_show_view()
        arcade.set_background_color(arcade.color.DARK_RED)
        self.window.audio.play_music("assets/music/lose.mp3")
        box = arcade.gui.UIBoxLayout(space_between=10)
        box.add(arcade.gui.UILabel(text="ПОРАЖЕНИЕ", font_size=24, bold=True),
                space_around=(0, 0, 12, 0))

        retry = arcade.gui.UIFlatButton(text="Заново", width=300, height=50)
        retry.on_click = lambda e: self.window.show_view(GameView(level=self.level_num))
        box.add(retry)

        main_menu = arcade.gui.UIFlatButton(text="Главное меню", width=300, height=50)
        main_menu.on_click = lambda e: self.window.show_view(MainMenuView())
        box.add(main_menu)

        self._anchor_center(box)


# === Игра ===
class GameView(arcade.View):

    def __init__(self, level=1):
        super().__init__()
        self.level_num = level
        self.tile_map = None
        cfg: GameConfig = getattr(self.window, "game_config", GameConfig())
        apply_config(cfg)
        self.players = arcade.SpriteList()
        self.fire = None
        self.water = None
        # --- обработка клавиш ---
        self.keys = pyglet.window.key.KeyStateHandler()
        self.window.push_handlers(self.keys)

        self.fire_gems = arcade.SpriteList()
        self.water_gems = arcade.SpriteList()
        self.hazards = arcade.SpriteList()
        self.doors = arcade.SpriteList()
        self.platforms = arcade.SpriteList()
        self.setup_level()

    def can_jump(self, player):
        # проверяем, стоит ли игрок на платформе
        hits = arcade.check_for_collision_with_list(player, self.platforms)
        return len(hits) > 0 or player.bottom <= 0
    def setup_level(self):
        layer_options = {
            "Platforms": {"use_spatial_hash": True},  # для коллизий
            "Gems": {"use_spatial_hash": False},
            "Hazards": {"use_spatial_hash": False},
            "Doors": {"use_spatial_hash": False}
        }
        self.players = arcade.SpriteList()
        map_name = f"C:/gamr/lvl{self.level_num}.tmx"
        tile_map = arcade.load_tilemap(map_name, scaling=1.5)
        self.platforms = tile_map.sprite_lists.get("Platforms", arcade.SpriteList())
        self.fire_gems = tile_map.sprite_lists.get("fire_gems", arcade.SpriteList())
        self.water_gems = tile_map.sprite_lists.get("water_gems", arcade.SpriteList())
        self.hazards = tile_map.sprite_lists.get("Hazards", arcade.SpriteList())
        self.doors = tile_map.sprite_lists.get("Doors", arcade.SpriteList())
        self.tile_map = arcade.load_tilemap(map_name, TILE_SCALING, layer_options)
        self.scene = arcade.Scene.from_tilemap(self.tile_map)
        FIRE_CONTROLS = {"left": arcade.key.A, "right": arcade.key.D, "jump": arcade.key.W}
        WATER_CONTROLS = {"left": arcade.key.LEFT, "right": arcade.key.RIGHT, "jump": arcade.key.UP}
        spawn_fire = self.tile_map.object_lists["Fire_spawn"][0]
        spawn_water = self.tile_map.object_lists["Water_spawn"][0]
        # Fire
        self.fire = Player("assets/sprites/water.png", 0.045, FIRE_CONTROLS)
        self.fire.center_x = spawn_fire.shape[0]
        self.fire.center_y = spawn_fire.shape[1]+self.fire.height / 2
        self.players.append(self.fire)

        # Water
        self.water = Player("assets/sprites/fire.png", 0.045, WATER_CONTROLS)
        self.water.center_x = spawn_water.shape[0]
        self.water.center_y = spawn_water.shape[1]+self.water.height / 2
        self.players.append(self.water)

        # Платформа для теста
        hits = arcade.check_for_collision_with_list(self.fire, self.platforms)
        if hits:
            top = max(p.top for p in hits)
            self.fire.bottom = top
            self.fire.change_y = 0

    def on_show_view(self):

        arcade.set_background_color(arcade.color.BLUE_SAPPHIRE)

        super().on_show_view()
        self.window.audio.play_music("assets/music/game.mp3")

    def on_draw(self):
        self.clear()
        self.platforms.draw()
        self.fire_gems.draw()
        self.water_gems.draw()
        self.hazards.draw()
        self.doors.draw()
        self.players.draw()

        cfg: GameConfig = getattr(self.window, "game_config", GameConfig())
        if cfg.show_hints:
            arcade.draw_text("ESC — пауза", 10, 10, arcade.color.LIGHT_GRAY, 12)

    def on_update(self, delta_time: float):

        # --- границы по X ---
        for p in (self.fire, self.water):
            if p.left < 0:
                p.left = 0
                p.change_x = 0
            if p.right > SCREEN_WIDTH:
                p.right = SCREEN_WIDTH
                p.change_x = 0
        for player in self.players:
            player.update_movement(self.keys)

        # --- обработка движения и коллизий ---
        for player in self.players:
            # --- гравитация ---
            player.change_y -= GRAVITY

            # --- движение по Y ---
            player.center_y += player.change_y
            hits = arcade.check_for_collision_with_list(player, self.platforms)

            if hits:
                for platform in hits:
                    # падение сверху
                    if player.change_y <= 0 and player.top > platform.top:
                        player.bottom = platform.top
                        player.change_y = 0
                        player.can_jump = True
                    # удар головой снизу
                    elif player.change_y > 0 and player.bottom < platform.bottom:
                        player.top = platform.bottom
                        player.change_y = 0
            else:
                player.can_jump = False

            # --- движение по X ---
            player.center_x += player.change_x
            hits = arcade.check_for_collision_with_list(player, self.platforms)

            if hits:
                for platform in hits:
                    if player.change_x > 0:  # движение вправо
                        if player.right > platform.left:
                            player.right = platform.left
                            player.change_x = 0
                    elif player.change_x < 0:  # движение влево
                        if player.left < platform.right:
                            player.left = platform.right
                            player.change_x = 0

            # --- проверка пола ---
            if player.bottom <= 0:
                player.bottom = 0
                player.change_y = 0
                player.can_jump = True

        # --- сбор предметов ---
        for player in (self.fire, self.water):

            for gem in arcade.check_for_collision_with_list(self.water, self.fire_gems):
                gem.remove_from_sprite_lists()
            for gem in arcade.check_for_collision_with_list(self.fire, self.water_gems):
                gem.remove_from_sprite_lists()
        for player in (self.fire, self.water):
            if arcade.check_for_collision_with_list(player, self.hazards):
                self.window.show_view(LoseView(self.level_num))
                return

        # Проверка победы
        for door in self.doors:
            if arcade.check_for_collision(self.fire, door) and arcade.check_for_collision(self.water, door):
                gems_done = (len(self.fire_gems) == 0 and len(self.water_gems) == 0) if REQUIRE_GEMS else True
                if gems_done:
                    self.window.show_view(WinView(self.level_num))
                return
    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
                    pause_view = PauseView(self)
                    self.window.show_view(pause_view)


# === Запуск ===
def main():
    window = arcade.Window(1200, 900, "Главное меню с картинками")
    menu = SplashView()
    window.audio = AudioManager()
    window.show_view(menu)
    arcade.run()


if __name__ == "__main__":
    main()
