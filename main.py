
import math
import random
import sys
from collections import deque
from dataclasses import dataclass
from typing import Optional

from panda3d.core import (
    AmbientLight,
    DirectionalLight,
    KeyboardButton,
    NodePath,
    PNMImage,
    Point3,
    SamplerState,
    TextNode,
    Texture,
    TransparencyAttrib,
    Vec2,
    WindowProperties,
    loadPrcFileData,
)

# Hardware first, then software fallback.
loadPrcFileData("", "load-display pandagl")
loadPrcFileData("", "aux-display pandadx9")
loadPrcFileData("", "aux-display p3tinydisplay")
loadPrcFileData("", "notify-level-display warning")

from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task


WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

GRID_W = 28
GRID_H = 28
TILE = 2.0
HALF_WORLD_X = GRID_W * TILE * 0.5
HALF_WORLD_Y = GRID_H * TILE * 0.5

STATE_MENU = "menu"
STATE_PLAYING = "playing"
STATE_GAME_OVER = "game_over"

AP_PER_TURN = 2
MOVE_STEPS_1_AP = 4
MOVE_STEPS_2_AP = 8

SHOT_RANGE = 14
BASE_CRIT = 10

CAM_PAN_SPEED = 25.0
CAM_EDGE_PIXELS = 22
CAM_ROT_SPEED = 80.0
CAM_MIN_ZOOM = 0.0
CAM_MAX_ZOOM = 1.0


Cell = tuple[int, int]


@dataclass
class Cover:
    node: NodePath
    cells: set[Cell]
    kind: str
    hp: int
    cover_bonus: int
    destructible: bool


@dataclass
class Unit:
    uid: str
    team: str
    role: str
    node: NodePath
    gun: NodePath
    muzzle: NodePath
    cell: Cell
    hp: int
    max_hp: int
    aim: int
    defense: int
    ap: int = AP_PER_TURN
    alive: bool = True
    overwatch: bool = False
    fortify: bool = False
    shoot_anim: float = 0.0


@dataclass
class ShotPreview:
    chance: int
    crit: int
    cover: int
    cover_cell: Optional[Cell]
    flanked: bool
    blocked: bool


class EchoProtocol3D(ShowBase):
    def __init__(self) -> None:
        super().__init__()

        props = WindowProperties()
        props.setSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        props.setTitle("ECHO PROTOCOL 3D - Turn Based Alpha")
        if self.win is not None and hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)

        self.disableMouse()
        self.setBackgroundColor(0.08, 0.1, 0.14, 1)

        self.rng = random.Random(20260301)
        self.state = STATE_MENU
        self.victory = False

        self.turn_side = "player"
        self.turn_number = 1
        self.selected_player_id: Optional[str] = None
        self.selected_enemy_id: Optional[str] = None

        self.score = 0
        self.player_team: list[Unit] = []
        self.enemy_team: list[Unit] = []
        self.covers: list[Cover] = []
        self.cover_by_cell: dict[Cell, Cover] = {}

        self.logs: deque[str] = deque(maxlen=8)

        self.world_root = self.render.attachNewNode("world")
        self.markers_root = self.world_root.attachNewNode("markers")

        self.player_marker: Optional[NodePath] = None
        self.enemy_marker: Optional[NodePath] = None
        self.hover_marker: Optional[NodePath] = None

        self.cam_center_x = 0.0
        self.cam_center_y = 0.0
        self.cam_yaw = 0.0
        self.cam_zoom = 0.42

        self.cam_keys = {
            "left": False,
            "right": False,
            "up": False,
            "down": False,
            "rot_l": False,
            "rot_r": False,
        }

        self.tex_ground = self._make_checker_texture("ground", (56, 103, 72), (46, 88, 62), 128, 8)
        self.tex_wall = self._make_checker_texture("wall", (95, 98, 110), (78, 82, 92), 128, 8)
        self.tex_cover = self._make_checker_texture("cover", (124, 110, 84), (99, 84, 63), 128, 8)
        self.tex_player = self._make_checker_texture("player", (58, 178, 248), (40, 132, 188), 64, 8)
        self.tex_enemy = self._make_checker_texture("enemy", (217, 78, 78), (153, 44, 44), 64, 8)
        self.tex_skin = self._make_checker_texture("skin", (227, 203, 172), (208, 181, 149), 64, 8)
        self.tex_weapon = self._make_checker_texture("weapon", (56, 66, 79), (43, 50, 60), 64, 8)
        self.tex_tree_bark = self._make_checker_texture("tree_bark", (110, 81, 56), (84, 62, 44), 64, 6)
        self.tex_tree_leaf = self._make_checker_texture("tree_leaf", (74, 132, 74), (53, 104, 58), 64, 6)
        self.tex_rock = self._make_checker_texture("rock", (118, 121, 129), (95, 99, 106), 64, 8)
        self.tex_house_wall = self._make_checker_texture("house_wall", (168, 164, 146), (142, 139, 122), 128, 8)
        self.tex_house_roof = self._make_checker_texture("house_roof", (130, 70, 62), (102, 51, 46), 128, 8)

        self._setup_lights()
        self._setup_input()
        self._setup_ui()
        self._show_menu()
        self._apply_camera()

        self.taskMgr.add(self._update, "update")

    # ---------- setup ----------
    def _setup_lights(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.setColor((0.54, 0.57, 0.64, 1))
        self.render.setLight(self.render.attachNewNode(ambient))

        sun = DirectionalLight("sun")
        sun.setColor((0.9, 0.9, 0.95, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(20, -58, 0)
        self.render.setLight(sun_np)

    def _setup_input(self) -> None:
        binds = [
            ("a", "left"),
            ("arrow_left", "left"),
            ("d", "right"),
            ("arrow_right", "right"),
            ("w", "up"),
            ("arrow_up", "up"),
            ("s", "down"),
            ("arrow_down", "down"),
            ("q", "rot_l"),
            ("e", "rot_r"),
        ]
        for key, name in binds:
            self.accept(key, self._set_cam_key, [name, True])
            self.accept(f"{key}-up", self._set_cam_key, [name, False])

        self.accept("wheel_up", self._zoom_camera, [-0.08])
        self.accept("wheel_down", self._zoom_camera, [0.08])

        self.accept("mouse1", self._on_left_click)
        self.accept("mouse3", self._on_right_click)
        self.accept("tab", self._cycle_player_unit)
        self.accept("o", self._set_overwatch_action)
        self.accept("f", self._set_fortify_action)
        self.accept("e", self._end_player_turn)
        self.accept("space", self._end_player_turn)

        self.accept("enter", self._handle_enter)
        self.accept("r", self._handle_restart)
        self.accept("escape", self._handle_escape)

    def _setup_ui(self) -> None:
        self.menu_title = OnscreenText(
            text="ECHO PROTOCOL",
            pos=(0, 0.47),
            scale=0.112,
            fg=(0.93, 0.97, 1, 1),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.menu_subtitle = OnscreenText(
            text="3D Turn-Based Tactical Alpha",
            pos=(0, 0.365),
            scale=0.05,
            fg=(0.76, 0.84, 0.92, 1),
            align=TextNode.ACenter,
            mayChange=True,
        )

        self.menu_panel = DirectFrame(
            frameColor=(0.08, 0.12, 0.2, 0.84),
            frameSize=(-0.64, 0.64, -0.44, 0.26),
            pos=(0, 0, -0.02),
            relief=1,
        )
        self.menu_start_btn = DirectButton(
            parent=self.menu_panel,
            text="Start Mission",
            text_scale=0.065,
            text_fg=(0.92, 0.96, 1, 1),
            scale=0.54,
            pos=(0, 0, 0.05),
            frameSize=(-0.74, 0.74, -0.18, 0.18),
            frameColor=(0.16, 0.3, 0.5, 1),
            pressEffect=False,
            command=self._start_battle,
        )
        self.menu_exit_btn = DirectButton(
            parent=self.menu_panel,
            text="Exit",
            text_scale=0.06,
            text_fg=(0.92, 0.96, 1, 1),
            scale=0.48,
            pos=(0, 0, -0.24),
            frameSize=(-0.62, 0.62, -0.18, 0.18),
            frameColor=(0.35, 0.18, 0.18, 1),
            pressEffect=False,
            command=self._quit_app,
        )
        self.menu_hint_top = OnscreenText(
            text="Turn-based combat with AP, cover and hit chance",
            pos=(0, 0.31),
            scale=0.04,
            fg=(0.82, 0.89, 0.96, 1),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.menu_hint_bottom = OnscreenText(
            text="Camera: WASD/Arrows pan, Q/E rotate, mouse wheel zoom",
            pos=(0, -0.5),
            scale=0.038,
            fg=(0.82, 0.89, 0.96, 1),
            align=TextNode.ACenter,
            mayChange=True,
        )

        self.turn_text = OnscreenText(
            text="",
            pos=(-1.31, 0.95),
            scale=0.048,
            fg=(0.91, 0.97, 1, 1),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.hud_text = OnscreenText(
            text="",
            pos=(-1.31, 0.82),
            scale=0.039,
            fg=(0.87, 0.93, 0.99, 1),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.controls_text = OnscreenText(
            text=(
                "LMB select/shoot | RMB move | TAB next | O overwatch | F fortify | E end turn\n"
                "Camera: WASD/Arrows pan | Q/E rotate | Wheel zoom | ESC menu"
            ),
            pos=(-1.31, -0.88),
            scale=0.032,
            fg=(0.76, 0.84, 0.93, 1),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.log_text = OnscreenText(
            text="",
            pos=(-1.31, 0.65),
            scale=0.034,
            fg=(0.95, 0.9, 0.72, 1),
            align=TextNode.ALeft,
            mayChange=True,
        )

        self.gameover_text = OnscreenText(
            text="",
            pos=(0, 0.05),
            scale=0.08,
            fg=(1, 0.75, 0.75, 1),
            align=TextNode.ACenter,
            mayChange=True,
        )

        self._toggle_hud(False)
        self.gameover_text.hide()

    def _toggle_hud(self, visible: bool) -> None:
        items = [self.turn_text, self.hud_text, self.controls_text, self.log_text]
        for item in items:
            item.show() if visible else item.hide()

    # ---------- texture helpers ----------
    def _make_checker_texture(
        self,
        name: str,
        color_a: tuple[int, int, int],
        color_b: tuple[int, int, int],
        size: int,
        step: int,
    ) -> Texture:
        img = PNMImage(size, size)
        for y in range(size):
            for x in range(size):
                use_a = ((x // step) + (y // step)) % 2 == 0
                c = color_a if use_a else color_b
                img.setXelA(x, y, c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, 1.0)

        tex = Texture(name)
        tex.load(img)
        tex.setMagfilter(SamplerState.FT_nearest)
        tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
        return tex
    # ---------- menu / states ----------
    def _show_menu(self) -> None:
        self.state = STATE_MENU
        self.menu_title.show()
        self.menu_subtitle.show()
        self.menu_panel.show()
        self.menu_start_btn.show()
        self.menu_exit_btn.show()
        self.menu_hint_top.show()
        self.menu_hint_bottom.show()
        self.gameover_text.hide()
        self._toggle_hud(False)

    def _hide_menu(self) -> None:
        self.menu_title.hide()
        self.menu_subtitle.hide()
        self.menu_panel.hide()
        self.menu_start_btn.hide()
        self.menu_exit_btn.hide()
        self.menu_hint_top.hide()
        self.menu_hint_bottom.hide()

    def _quit_app(self) -> None:
        self.userExit()

    def _cleanup_world(self) -> None:
        self.world_root.removeNode()
        self.world_root = self.render.attachNewNode("world")
        self.markers_root = self.world_root.attachNewNode("markers")

        self.covers = []
        self.cover_by_cell = {}
        self.player_team = []
        self.enemy_team = []
        self.selected_player_id = None
        self.selected_enemy_id = None

        self.player_marker = None
        self.enemy_marker = None
        self.hover_marker = None

    # ---------- grid / world ----------
    def _grid_to_world(self, cell: Cell) -> tuple[float, float]:
        gx, gy = cell
        x = -HALF_WORLD_X + gx * TILE + TILE * 0.5
        y = -HALF_WORLD_Y + gy * TILE + TILE * 0.5
        return x, y

    def _world_to_cell(self, x: float, y: float) -> Optional[Cell]:
        gx = int((x + HALF_WORLD_X) // TILE)
        gy = int((y + HALF_WORLD_Y) // TILE)
        if 0 <= gx < GRID_W and 0 <= gy < GRID_H:
            return gx, gy
        return None

    def _in_bounds(self, cell: Cell) -> bool:
        return 0 <= cell[0] < GRID_W and 0 <= cell[1] < GRID_H

    def _neighbors4(self, cell: Cell) -> list[Cell]:
        x, y = cell
        return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

    def _manhattan(self, a: Cell, b: Cell) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    # ---------- world build ----------
    def _start_battle(self) -> None:
        self._cleanup_world()

        self.state = STATE_PLAYING
        self.victory = False
        self.score = 0
        self.turn_number = 1
        self.turn_side = "player"
        self.logs.clear()

        ground = self.loader.loadModel("models/box")
        ground.reparentTo(self.world_root)
        ground.setScale(HALF_WORLD_X, HALF_WORLD_Y, 0.05)
        ground.setPos(0, 0, -0.05)
        ground.setTexture(self.tex_ground, 1)

        self._spawn_boundaries()
        self._spawn_houses(11)
        self._spawn_trees(38)
        self._spawn_rocks(30)
        self._spawn_crates(28)

        self._spawn_player_squad()
        self._spawn_enemy_squad(12)
        self._build_markers()

        self.selected_player_id = next((u.uid for u in self.player_team if u.alive), None)
        if self.selected_player_id is not None:
            unit = self._get_unit(self.selected_player_id)
            if unit is not None:
                wx, wy = self._grid_to_world(unit.cell)
                self.cam_center_x = wx
                self.cam_center_y = wy

        self._start_player_turn(first_turn=True)

        self._hide_menu()
        self.gameover_text.hide()
        self._toggle_hud(True)
        self._refresh_hud()

    def _register_cover(
        self,
        node: NodePath,
        cells: set[Cell],
        kind: str,
        hp: int,
        cover_bonus: int,
        destructible: bool,
    ) -> None:
        cover = Cover(
            node=node,
            cells=set(cells),
            kind=kind,
            hp=hp,
            cover_bonus=cover_bonus,
            destructible=destructible,
        )
        self.covers.append(cover)
        for cell in cells:
            self.cover_by_cell[cell] = cover

    def _can_place_cover(self, cells: set[Cell], clear_spawn: bool = True) -> bool:
        for cell in cells:
            if not self._in_bounds(cell):
                return False
            if cell in self.cover_by_cell:
                return False
            if clear_spawn and cell[0] <= 4:
                return False
        return True

    def _spawn_boundaries(self) -> None:
        box = self.loader.loadModel("models/box")
        box.setScale(0.5, 0.5, 1.0)

        for gx in range(GRID_W):
            for gy in (0, GRID_H - 1):
                cell = (gx, gy)
                x, y = self._grid_to_world(cell)
                node = box.copyTo(self.world_root)
                node.setPos(x, y, 1.0)
                node.setTexture(self.tex_wall, 1)
                self._register_cover(node, {cell}, "wall", 9999, 40, False)

        for gy in range(1, GRID_H - 1):
            for gx in (0, GRID_W - 1):
                cell = (gx, gy)
                x, y = self._grid_to_world(cell)
                node = box.copyTo(self.world_root)
                node.setPos(x, y, 1.0)
                node.setTexture(self.tex_wall, 1)
                self._register_cover(node, {cell}, "wall", 9999, 40, False)

        box.removeNode()

    def _spawn_houses(self, count: int) -> None:
        placed = 0
        attempts = 0
        while placed < count and attempts < count * 40:
            attempts += 1
            gx = self.rng.randint(6, GRID_W - 6)
            gy = self.rng.randint(2, GRID_H - 5)
            cells = {(gx, gy), (gx + 1, gy), (gx, gy + 1), (gx + 1, gy + 1)}
            if not self._can_place_cover(cells):
                continue

            x0, y0 = self._grid_to_world((gx, gy))
            x1, y1 = self._grid_to_world((gx + 1, gy + 1))
            cx = (x0 + x1) * 0.5
            cy = (y0 + y1) * 0.5

            root = self.world_root.attachNewNode("house")
            body = self.loader.loadModel("models/box")
            body.reparentTo(root)
            body.setScale(1.9, 1.9, 1.25)
            body.setPos(0, 0, 1.25)
            body.setTexture(self.tex_house_wall, 1)

            roof = self.loader.loadModel("models/box")
            roof.reparentTo(root)
            roof.setScale(2.1, 2.1, 0.32)
            roof.setPos(0, 0, 2.82)
            roof.setTexture(self.tex_house_roof, 1)

            root.setPos(cx, cy, 0)
            self._register_cover(root, cells, "house", 8, 40, True)
            placed += 1

    def _spawn_trees(self, count: int) -> None:
        placed = 0
        attempts = 0
        while placed < count and attempts < count * 35:
            attempts += 1
            cell = (self.rng.randint(2, GRID_W - 3), self.rng.randint(2, GRID_H - 3))
            if not self._can_place_cover({cell}):
                continue

            x, y = self._grid_to_world(cell)
            root = self.world_root.attachNewNode("tree")

            trunk = self.loader.loadModel("models/box")
            trunk.reparentTo(root)
            trunk.setScale(0.19, 0.19, 0.84)
            trunk.setPos(0, 0, 0.84)
            trunk.setTexture(self.tex_tree_bark, 1)

            canopy = self.loader.loadModel("models/smiley")
            canopy.reparentTo(root)
            canopy.setScale(0.76)
            canopy.setPos(0, 0, 1.95)
            canopy.setTexture(self.tex_tree_leaf, 1)

            root.setPos(x, y, 0)
            self._register_cover(root, {cell}, "tree", 3, 20, True)
            placed += 1

    def _spawn_rocks(self, count: int) -> None:
        placed = 0
        attempts = 0
        while placed < count and attempts < count * 35:
            attempts += 1
            cell = (self.rng.randint(2, GRID_W - 3), self.rng.randint(2, GRID_H - 3))
            if not self._can_place_cover({cell}):
                continue

            x, y = self._grid_to_world(cell)
            root = self.world_root.attachNewNode("rock")

            a = self.loader.loadModel("models/box")
            a.reparentTo(root)
            a.setScale(0.5, 0.46, 0.34)
            a.setPos(-0.1, 0.06, 0.34)
            a.setTexture(self.tex_rock, 1)

            b = self.loader.loadModel("models/box")
            b.reparentTo(root)
            b.setScale(0.42, 0.36, 0.28)
            b.setPos(0.22, -0.1, 0.28)
            b.setTexture(self.tex_rock, 1)

            root.setPos(x, y, 0)
            self._register_cover(root, {cell}, "rock", 2, 25, True)
            placed += 1

    def _spawn_crates(self, count: int) -> None:
        placed = 0
        attempts = 0
        while placed < count and attempts < count * 35:
            attempts += 1
            cell = (self.rng.randint(2, GRID_W - 3), self.rng.randint(2, GRID_H - 3))
            if not self._can_place_cover({cell}):
                continue

            x, y = self._grid_to_world(cell)
            node = self.loader.loadModel("models/box")
            node.reparentTo(self.world_root)
            node.setScale(0.42, 0.42, 0.64)
            node.setPos(x, y, 0.64)
            node.setTexture(self.tex_cover, 1)
            self._register_cover(node, {cell}, "crate", 3, 30, True)
            placed += 1
    def _create_soldier(self, texture: Texture) -> tuple[NodePath, NodePath, NodePath]:
        root = self.world_root.attachNewNode("soldier")

        legs = self.loader.loadModel("models/box")
        legs.reparentTo(root)
        legs.setScale(0.23, 0.18, 0.36)
        legs.setPos(0, 0, 0.36)
        legs.setTexture(texture, 1)

        torso = self.loader.loadModel("models/box")
        torso.reparentTo(root)
        torso.setScale(0.3, 0.22, 0.34)
        torso.setPos(0, 0, 1.03)
        torso.setTexture(texture, 1)

        head = self.loader.loadModel("models/box")
        head.reparentTo(root)
        head.setScale(0.17, 0.17, 0.17)
        head.setPos(0, 0, 1.47)
        head.setTexture(self.tex_skin, 1)

        gun = self.loader.loadModel("models/box")
        gun.reparentTo(root)
        gun.setScale(0.35, 0.08, 0.05)
        gun.setPos(0, 0.38, 1.06)
        gun.setTexture(self.tex_weapon, 1)

        muzzle = self.loader.loadModel("models/box")
        muzzle.reparentTo(root)
        muzzle.setScale(0.08, 0.08, 0.08)
        muzzle.setPos(0, 0.59, 1.06)
        muzzle.setColor(1.0, 0.82, 0.35, 1.0)
        muzzle.setTransparency(TransparencyAttrib.MAlpha)
        muzzle.setAlphaScale(0.0)

        return root, gun, muzzle

    def _spawn_player_squad(self) -> None:
        templates = [
            ("P1", "Ranger", 10, 10, 73, 8),
            ("P2", "Support", 9, 9, 68, 10),
            ("P3", "Heavy", 12, 12, 63, 13),
        ]
        spawn_cells = [(2, 10), (2, 13), (2, 16)]

        for idx, tpl in enumerate(templates):
            uid, role, hp, max_hp, aim, defense = tpl
            cell = spawn_cells[idx]
            root, gun, muzzle = self._create_soldier(self.tex_player)
            x, y = self._grid_to_world(cell)
            root.setPos(x, y, 0)
            root.setH(0)
            self.player_team.append(
                Unit(
                    uid=uid,
                    team="player",
                    role=role,
                    node=root,
                    gun=gun,
                    muzzle=muzzle,
                    cell=cell,
                    hp=hp,
                    max_hp=max_hp,
                    aim=aim,
                    defense=defense,
                )
            )

    def _spawn_enemy_squad(self, count: int) -> None:
        placed = 0
        attempts = 0
        while placed < count and attempts < count * 60:
            attempts += 1
            cell = (self.rng.randint(GRID_W - 8, GRID_W - 3), self.rng.randint(2, GRID_H - 3))
            if cell in self.cover_by_cell:
                continue
            if any(unit.alive and unit.cell == cell for unit in self.player_team + self.enemy_team):
                continue

            root, gun, muzzle = self._create_soldier(self.tex_enemy)
            x, y = self._grid_to_world(cell)
            root.setPos(x, y, 0)
            root.setH(180)

            hp = self.rng.randint(7, 10)
            aim = self.rng.randint(57, 67)
            defense = self.rng.randint(4, 10)
            self.enemy_team.append(
                Unit(
                    uid=f"E{placed + 1}",
                    team="enemy",
                    role="Raider",
                    node=root,
                    gun=gun,
                    muzzle=muzzle,
                    cell=cell,
                    hp=hp,
                    max_hp=hp,
                    aim=aim,
                    defense=defense,
                )
            )
            placed += 1

    def _build_markers(self) -> None:
        def make_marker(color: tuple[float, float, float, float]) -> NodePath:
            marker = self.loader.loadModel("models/box")
            marker.reparentTo(self.markers_root)
            marker.setScale(0.53, 0.53, 0.03)
            marker.setColor(*color)
            marker.setTransparency(TransparencyAttrib.MAlpha)
            marker.hide()
            return marker

        self.player_marker = make_marker((0.22, 0.62, 1.0, 0.45))
        self.enemy_marker = make_marker((1.0, 0.32, 0.32, 0.42))
        self.hover_marker = make_marker((1.0, 0.94, 0.35, 0.3))

    # ---------- unit / cover helpers ----------
    def _all_units(self) -> list[Unit]:
        return self.player_team + self.enemy_team

    def _alive_units(self, team: str) -> list[Unit]:
        units = self.player_team if team == "player" else self.enemy_team
        return [u for u in units if u.alive]

    def _get_unit(self, uid: Optional[str]) -> Optional[Unit]:
        if uid is None:
            return None
        for unit in self._all_units():
            if unit.uid == uid and unit.alive:
                return unit
        return None

    def _unit_at_cell(self, cell: Cell, team: Optional[str] = None) -> Optional[Unit]:
        for unit in self._all_units():
            if not unit.alive:
                continue
            if team is not None and unit.team != team:
                continue
            if unit.cell == cell:
                return unit
        return None

    def _is_blocked(self, cell: Cell, ignore_uid: Optional[str] = None) -> bool:
        if not self._in_bounds(cell):
            return True
        if cell in self.cover_by_cell:
            return True
        for unit in self._all_units():
            if not unit.alive:
                continue
            if ignore_uid is not None and unit.uid == ignore_uid:
                continue
            if unit.cell == cell:
                return True
        return False

    def _bfs_path(self, start: Cell, goal: Cell, ignore_uid: Optional[str]) -> list[Cell]:
        if start == goal:
            return [start]

        queue: deque[Cell] = deque([start])
        prev: dict[Cell, Optional[Cell]] = {start: None}

        while queue:
            cur = queue.popleft()
            for nxt in self._neighbors4(cur):
                if nxt in prev:
                    continue
                if self._is_blocked(nxt, ignore_uid=ignore_uid):
                    continue
                prev[nxt] = cur
                if nxt == goal:
                    queue.clear()
                    break
                queue.append(nxt)

        if goal not in prev:
            return []

        path: list[Cell] = []
        cur: Optional[Cell] = goal
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path

    def _movement_ap_cost(self, steps: int) -> int:
        if steps <= 0:
            return 0
        if steps <= MOVE_STEPS_1_AP:
            return 1
        if steps <= MOVE_STEPS_2_AP:
            return 2
        return 999

    def _move_unit(self, unit: Unit, target: Cell) -> bool:
        if not unit.alive or unit.ap <= 0:
            return False
        if target == unit.cell:
            return False
        if self._is_blocked(target, ignore_uid=unit.uid):
            return False

        path = self._bfs_path(unit.cell, target, ignore_uid=unit.uid)
        if not path:
            return False
        steps = len(path) - 1
        cost = self._movement_ap_cost(steps)
        if cost > unit.ap:
            return False

        unit.cell = target
        unit.ap -= cost
        unit.overwatch = False
        unit.fortify = False

        wx, wy = self._grid_to_world(target)
        unit.node.setPos(wx, wy, 0)
        if steps > 0:
            prev = path[-2]
            dx = target[0] - prev[0]
            dy = target[1] - prev[1]
            unit.node.setH(math.degrees(math.atan2(dx, dy)))

        self._log(f"{unit.uid} moved {steps} tiles (-{cost} AP)")
        return True

    # ---------- los / cover / combat ----------
    def _bresenham(self, start: Cell, end: Cell) -> list[Cell]:
        x0, y0 = start
        x1, y1 = end
        cells: list[Cell] = []

        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy

        while True:
            cells.append((x0, y0))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy
        return cells

    def _has_los(self, start: Cell, end: Cell) -> bool:
        if start == end:
            return True
        line = self._bresenham(start, end)
        for cell in line[1:-1]:
            if cell in self.cover_by_cell:
                return False
        return True

    def _cover_bonus_for_cell(self, cell: Cell) -> int:
        cover = self.cover_by_cell.get(cell)
        if cover is None:
            return 0
        return cover.cover_bonus

    def _compute_cover(self, attacker: Cell, target: Cell) -> tuple[int, Optional[Cell], bool]:
        dx = attacker[0] - target[0]
        dy = attacker[1] - target[1]

        dirs: list[Cell] = []
        if dx != 0:
            dirs.append((1 if dx > 0 else -1, 0))
        if dy != 0:
            dirs.append((0, 1 if dy > 0 else -1))
        if not dirs:
            dirs.append((0, 0))

        best = 0
        best_cell: Optional[Cell] = None
        for d in dirs:
            c = (target[0] + d[0], target[1] + d[1])
            bonus = self._cover_bonus_for_cell(c)
            if bonus > best:
                best = bonus
                best_cell = c

        has_any_cover = any(self._cover_bonus_for_cell(n) > 0 for n in self._neighbors4(target))
        flanked = has_any_cover and best == 0
        return best, best_cell, flanked

    def _shot_preview(self, attacker: Unit, target: Unit, reaction: bool = False) -> ShotPreview:
        if self._manhattan(attacker.cell, target.cell) > SHOT_RANGE:
            return ShotPreview(0, 0, 0, None, False, True)
        if not self._has_los(attacker.cell, target.cell):
            return ShotPreview(0, 0, 0, None, False, True)

        chance = attacker.aim
        if reaction:
            chance -= 15

        distance_penalty = max(0, self._manhattan(attacker.cell, target.cell) - 5) * 6
        chance -= distance_penalty

        cover_bonus, cover_cell, flanked = self._compute_cover(attacker.cell, target.cell)
        target_def = target.defense + (18 if target.fortify else 0)

        if flanked:
            chance += 20
            effective_cover = 0
        else:
            effective_cover = cover_bonus
            chance -= effective_cover

        chance -= target_def
        chance = max(5, min(95, int(chance)))
        crit = max(0, min(70, BASE_CRIT + (22 if flanked else 0)))

        return ShotPreview(chance, crit, effective_cover, cover_cell, flanked, False)

    def _destroy_cover(self, cover: Cover) -> None:
        for cell in list(cover.cells):
            if self.cover_by_cell.get(cell) is cover:
                del self.cover_by_cell[cell]
        cover.node.removeNode()
        cover.hp = 0
        self._log(f"{cover.kind.title()} destroyed")

    def _damage_cover_cell(self, cell: Optional[Cell], amount: int = 1) -> None:
        if cell is None:
            return
        cover = self.cover_by_cell.get(cell)
        if cover is None or not cover.destructible:
            return
        cover.hp -= amount
        if cover.hp <= 0:
            self._destroy_cover(cover)
        else:
            self._log(f"{cover.kind.title()} damaged")

    def _trigger_shot_anim(self, unit: Unit) -> None:
        unit.shoot_anim = 1.0
        unit.muzzle.setAlphaScale(1.0)

    def _resolve_shot(self, attacker: Unit, target: Unit, reaction: bool = False, spend_ap: bool = True) -> bool:
        if not attacker.alive or not target.alive:
            return False
        if spend_ap and attacker.ap < 1:
            return False

        preview = self._shot_preview(attacker, target, reaction=reaction)
        if preview.blocked:
            if attacker.team == "player":
                self._log("No line of sight")
            return False

        if spend_ap:
            attacker.ap -= 1

        ax, ay = self._grid_to_world(attacker.cell)
        tx, ty = self._grid_to_world(target.cell)
        attacker.node.setH(math.degrees(math.atan2(tx - ax, ty - ay)))
        self._trigger_shot_anim(attacker)

        roll = self.rng.randint(1, 100)
        if roll <= preview.chance:
            dmg = self.rng.randint(2, 4)
            crit_roll = self.rng.randint(1, 100)
            if crit_roll <= preview.crit:
                dmg += 2
                crit_label = " CRIT"
            else:
                crit_label = ""

            target.hp -= dmg
            self._log(f"{attacker.uid} hit {target.uid} for {dmg}{crit_label}")
            if target.hp <= 0:
                target.alive = False
                target.node.hide()
                if attacker.team == "player":
                    self.score += 1
                self._log(f"{target.uid} eliminated")
                if target.uid == self.selected_enemy_id:
                    self.selected_enemy_id = None
        else:
            self._log(f"{attacker.uid} missed {target.uid} ({preview.chance}%)")
            if preview.cover_cell is not None and self.rng.random() < 0.62:
                self._damage_cover_cell(preview.cover_cell, amount=1)

        return True
    # ---------- turns ----------
    def _start_player_turn(self, first_turn: bool = False) -> None:
        self.turn_side = "player"
        if not first_turn:
            self.turn_number += 1

        for unit in self.player_team:
            if not unit.alive:
                continue
            unit.ap = AP_PER_TURN
            unit.overwatch = False
            unit.fortify = False

        if self.selected_player_id is None or self._get_unit(self.selected_player_id) is None:
            self.selected_player_id = next((u.uid for u in self.player_team if u.alive), None)

        self._log(f"Player turn {self.turn_number}")

    def _end_player_turn(self) -> None:
        if self.state != STATE_PLAYING or self.turn_side != "player":
            return
        if self._check_game_end():
            return
        self._enemy_turn()

    def _enemy_turn(self) -> None:
        self.turn_side = "enemy"
        self._log("Enemy turn")

        for enemy in self.enemy_team:
            if not enemy.alive:
                continue
            enemy.ap = AP_PER_TURN
            enemy.overwatch = False
            enemy.fortify = False

            while enemy.ap > 0 and enemy.alive:
                if self._check_game_end():
                    return

                target = self._best_enemy_target(enemy)
                if target is not None:
                    fired = self._resolve_shot(enemy, target, reaction=False, spend_ap=True)
                    if fired:
                        continue

                nearest = self._closest_player(enemy)
                if nearest is None:
                    break

                path = self._bfs_path(enemy.cell, nearest.cell, ignore_uid=enemy.uid)
                if len(path) < 2:
                    break

                if enemy.ap < 1:
                    break

                enemy.ap -= 1
                old_cell = enemy.cell
                enemy.cell = path[1]
                wx, wy = self._grid_to_world(enemy.cell)
                enemy.node.setPos(wx, wy, 0)
                dx = enemy.cell[0] - old_cell[0]
                dy = enemy.cell[1] - old_cell[1]
                enemy.node.setH(math.degrees(math.atan2(dx, dy)))
                self._log(f"{enemy.uid} moved")

                self._trigger_overwatch(enemy)
                if self._check_game_end():
                    return

        if self._check_game_end():
            return
        self._start_player_turn(first_turn=False)

    def _best_enemy_target(self, enemy: Unit) -> Optional[Unit]:
        candidates: list[Unit] = []
        for unit in self.player_team:
            if not unit.alive:
                continue
            preview = self._shot_preview(enemy, unit, reaction=False)
            if preview.blocked:
                continue
            candidates.append(unit)
        if not candidates:
            return None
        return min(candidates, key=lambda u: (u.hp, self._manhattan(enemy.cell, u.cell)))

    def _closest_player(self, enemy: Unit) -> Optional[Unit]:
        alive = [u for u in self.player_team if u.alive]
        if not alive:
            return None
        return min(alive, key=lambda u: self._manhattan(enemy.cell, u.cell))

    def _trigger_overwatch(self, moving_enemy: Unit) -> None:
        watchers = [u for u in self.player_team if u.alive and u.overwatch]
        for watcher in watchers:
            if not moving_enemy.alive:
                break
            preview = self._shot_preview(watcher, moving_enemy, reaction=True)
            if preview.blocked:
                continue
            self._log(f"Overwatch: {watcher.uid} -> {moving_enemy.uid}")
            self._resolve_shot(watcher, moving_enemy, reaction=True, spend_ap=False)
            watcher.overwatch = False

    def _check_game_end(self) -> bool:
        alive_players = any(u.alive for u in self.player_team)
        alive_enemies = any(u.alive for u in self.enemy_team)

        if not alive_enemies:
            self._finish_game(victory=True)
            return True
        if not alive_players:
            self._finish_game(victory=False)
            return True
        return False

    # ---------- actions ----------
    def _cycle_player_unit(self) -> None:
        if self.state != STATE_PLAYING:
            return
        alive = [u for u in self.player_team if u.alive]
        if not alive:
            return
        if self.selected_player_id is None:
            self.selected_player_id = alive[0].uid
            return

        ids = [u.uid for u in alive]
        if self.selected_player_id not in ids:
            self.selected_player_id = alive[0].uid
            return

        start = ids.index(self.selected_player_id)
        for shift in range(1, len(ids) + 1):
            idx = (start + shift) % len(ids)
            unit = self._get_unit(ids[idx])
            if unit is not None and unit.ap > 0:
                self.selected_player_id = unit.uid
                wx, wy = self._grid_to_world(unit.cell)
                self.cam_center_x = wx
                self.cam_center_y = wy
                return

    def _set_overwatch_action(self) -> None:
        if self.state != STATE_PLAYING or self.turn_side != "player":
            return
        unit = self._get_unit(self.selected_player_id)
        if unit is None or not unit.alive or unit.ap < 1:
            return
        unit.ap -= 1
        unit.overwatch = True
        self._log(f"{unit.uid} on overwatch")

    def _set_fortify_action(self) -> None:
        if self.state != STATE_PLAYING or self.turn_side != "player":
            return
        unit = self._get_unit(self.selected_player_id)
        if unit is None or not unit.alive or unit.ap < 1:
            return
        unit.ap -= 1
        unit.fortify = True
        self._log(f"{unit.uid} fortified (+defense)")

    # ---------- mouse interaction ----------
    def _mouse_to_ground(self) -> Optional[Point3]:
        if self.mouseWatcherNode is None or not self.mouseWatcherNode.hasMouse():
            return None

        mpos = self.mouseWatcherNode.getMouse()
        near = Point3()
        far = Point3()
        self.camLens.extrude(mpos, near, far)

        near_world = self.render.getRelativePoint(self.camera, near)
        far_world = self.render.getRelativePoint(self.camera, far)
        direction = far_world - near_world
        if abs(direction.z) < 1e-6:
            return None

        t = -near_world.z / direction.z
        if t < 0:
            return None
        return near_world + direction * t

    def _mouse_to_cell(self) -> Optional[Cell]:
        p = self._mouse_to_ground()
        if p is None:
            return None
        return self._world_to_cell(p.x, p.y)

    def _on_left_click(self) -> None:
        if self.state != STATE_PLAYING or self.turn_side != "player":
            return
        cell = self._mouse_to_cell()
        if cell is None:
            return

        clicked_player = self._unit_at_cell(cell, team="player")
        clicked_enemy = self._unit_at_cell(cell, team="enemy")
        selected = self._get_unit(self.selected_player_id)

        if clicked_player is not None:
            self.selected_player_id = clicked_player.uid
            wx, wy = self._grid_to_world(clicked_player.cell)
            self.cam_center_x = wx
            self.cam_center_y = wy
            return

        if clicked_enemy is not None:
            self.selected_enemy_id = clicked_enemy.uid
            if selected is not None and selected.alive and selected.ap > 0:
                self._resolve_shot(selected, clicked_enemy, reaction=False, spend_ap=True)
                self._check_game_end()
            return

        shift_down = (
            self.mouseWatcherNode is not None
            and self.mouseWatcherNode.isButtonDown(KeyboardButton.shift())
        )
        if shift_down and selected is not None and selected.ap > 0 and cell in self.cover_by_cell:
            cover = self.cover_by_cell[cell]
            if self._has_los(selected.cell, cell):
                selected.ap -= 1
                self._trigger_shot_anim(selected)
                self._damage_cover_cell(cell, amount=2)
                self._log(f"{selected.uid} shot {cover.kind}")

    def _on_right_click(self) -> None:
        if self.state != STATE_PLAYING or self.turn_side != "player":
            return
        cell = self._mouse_to_cell()
        if cell is None:
            return
        unit = self._get_unit(self.selected_player_id)
        if unit is None:
            return
        moved = self._move_unit(unit, cell)
        if moved:
            wx, wy = self._grid_to_world(unit.cell)
            self.cam_center_x = wx
            self.cam_center_y = wy

    # ---------- camera ----------
    def _set_cam_key(self, key: str, value: bool) -> None:
        self.cam_keys[key] = value

    def _zoom_camera(self, delta: float) -> None:
        self.cam_zoom = max(CAM_MIN_ZOOM, min(CAM_MAX_ZOOM, self.cam_zoom + delta))

    def _apply_camera(self) -> None:
        distance = 28 + self.cam_zoom * 22
        height = 28 + self.cam_zoom * 28

        yaw_rad = math.radians(self.cam_yaw)
        ox = -math.sin(yaw_rad) * distance
        oy = -math.cos(yaw_rad) * distance

        self.camera.setPos(self.cam_center_x + ox, self.cam_center_y + oy, height)
        self.camera.lookAt(self.cam_center_x, self.cam_center_y, 0)

    def _update_camera(self, dt: float) -> None:
        if self.state not in (STATE_PLAYING,):
            self._apply_camera()
            return

        move_x = (1 if self.cam_keys["right"] else 0) - (1 if self.cam_keys["left"] else 0)
        move_y = (1 if self.cam_keys["up"] else 0) - (1 if self.cam_keys["down"] else 0)

        if self.mouseWatcherNode is not None and self.mouseWatcherNode.hasMouse():
            m = self.mouseWatcherNode.getMouse()
            px = (m.x * 0.5 + 0.5) * WINDOW_WIDTH
            py = (m.y * 0.5 + 0.5) * WINDOW_HEIGHT
            if px < CAM_EDGE_PIXELS:
                move_x -= 1
            elif px > WINDOW_WIDTH - CAM_EDGE_PIXELS:
                move_x += 1
            if py < CAM_EDGE_PIXELS:
                move_y += 1
            elif py > WINDOW_HEIGHT - CAM_EDGE_PIXELS:
                move_y -= 1

        if self.cam_keys["rot_l"]:
            self.cam_yaw += CAM_ROT_SPEED * dt
        if self.cam_keys["rot_r"]:
            self.cam_yaw -= CAM_ROT_SPEED * dt

        if move_x != 0 or move_y != 0:
            length = math.hypot(move_x, move_y)
            nx = move_x / length
            ny = move_y / length

            rad = math.radians(self.cam_yaw)
            forward = Vec2(math.sin(rad), math.cos(rad))
            right = Vec2(forward.y, -forward.x)

            speed = CAM_PAN_SPEED * dt
            delta = right * nx * speed + forward * ny * speed
            self.cam_center_x += delta.x
            self.cam_center_y += delta.y

        self.cam_center_x = max(-HALF_WORLD_X + 3.5, min(HALF_WORLD_X - 3.5, self.cam_center_x))
        self.cam_center_y = max(-HALF_WORLD_Y + 3.5, min(HALF_WORLD_Y - 3.5, self.cam_center_y))

        self._apply_camera()
    # ---------- visuals ----------
    def _update_markers(self) -> None:
        if self.player_marker is None or self.enemy_marker is None or self.hover_marker is None:
            return

        selected_player = self._get_unit(self.selected_player_id)
        if selected_player is not None and selected_player.alive:
            x, y = self._grid_to_world(selected_player.cell)
            self.player_marker.setPos(x, y, 0.03)
            self.player_marker.show()
        else:
            self.player_marker.hide()

        selected_enemy = self._get_unit(self.selected_enemy_id)
        if selected_enemy is not None and selected_enemy.alive:
            x, y = self._grid_to_world(selected_enemy.cell)
            self.enemy_marker.setPos(x, y, 0.03)
            self.enemy_marker.show()
        else:
            self.enemy_marker.hide()

        hover_cell = self._mouse_to_cell()
        if self.state == STATE_PLAYING and hover_cell is not None:
            x, y = self._grid_to_world(hover_cell)
            self.hover_marker.setPos(x, y, 0.02)
            self.hover_marker.show()
        else:
            self.hover_marker.hide()

    def _update_shot_anims(self, dt: float) -> None:
        for unit in self._all_units():
            if not unit.alive:
                continue
            if unit.shoot_anim > 0:
                unit.shoot_anim = max(0.0, unit.shoot_anim - dt * 10.5)
                pulse = math.sin(unit.shoot_anim * math.pi)
                unit.gun.setY(0.38 - pulse * 0.12)
                unit.muzzle.setScale(0.08 + pulse * 0.06)
                unit.muzzle.setAlphaScale(unit.shoot_anim)
            else:
                unit.gun.setY(0.38)
                unit.muzzle.setScale(0.08)
                unit.muzzle.setAlphaScale(0.0)

    # ---------- hud / logs ----------
    def _log(self, message: str) -> None:
        self.logs.appendleft(message)

    def _refresh_hud(self) -> None:
        if self.state != STATE_PLAYING:
            return

        alive_players = [u for u in self.player_team if u.alive]
        alive_enemies = [u for u in self.enemy_team if u.alive]
        selected_player = self._get_unit(self.selected_player_id)
        selected_enemy = self._get_unit(self.selected_enemy_id)

        self.turn_text.setText(f"Round {self.turn_number} | Turn: {self.turn_side.upper()}")

        if selected_player is not None:
            line = (
                f"Selected: {selected_player.uid} ({selected_player.role}) | HP {selected_player.hp}/{selected_player.max_hp} | "
                f"AP {selected_player.ap} | AIM {selected_player.aim}\n"
            )
        else:
            line = "Selected: none\n"

        stats = (
            f"Squad alive: {len(alive_players)} | Enemies alive: {len(alive_enemies)} | Kills: {self.score}\n"
            f"World props: {sum(1 for c in self.covers if c.hp > 0 and c.destructible)} destructible"
        )

        if selected_player is not None and selected_enemy is not None and selected_enemy.alive:
            preview = self._shot_preview(selected_player, selected_enemy, reaction=False)
            if preview.blocked:
                shot_line = "\nShot: blocked (no LOS / too far)"
            else:
                cover_label = "none" if preview.cover == 0 else ("half" if preview.cover <= 25 else "full")
                flank_label = "YES" if preview.flanked else "no"
                shot_line = (
                    f"\nShot -> Hit {preview.chance}% | Crit {preview.crit}% | Cover {cover_label} | Flank {flank_label}"
                )
        else:
            shot_line = ""

        self.hud_text.setText(line + stats + shot_line)
        self.log_text.setText("\n".join(self.logs))

    # ---------- state handlers ----------
    def _handle_enter(self) -> None:
        if self.state in (STATE_MENU, STATE_GAME_OVER):
            self._start_battle()

    def _handle_restart(self) -> None:
        if self.state == STATE_GAME_OVER:
            self._start_battle()

    def _handle_escape(self) -> None:
        if self.state in (STATE_PLAYING, STATE_GAME_OVER):
            self._cleanup_world()
            self._show_menu()
            return
        self.userExit()

    def _finish_game(self, victory: bool) -> None:
        if self.state == STATE_GAME_OVER:
            return
        self.state = STATE_GAME_OVER
        self.victory = victory

        self._toggle_hud(False)
        self.gameover_text.show()
        if victory:
            self.gameover_text.setFg((0.66, 0.95, 0.7, 1))
            self.gameover_text.setText("MISSION COMPLETE\nENTER/R - new mission | ESC - menu")
        else:
            self.gameover_text.setFg((0.97, 0.72, 0.72, 1))
            self.gameover_text.setText("MISSION FAILED\nENTER/R - retry | ESC - menu")

    # ---------- update ----------
    def _update(self, task: Task) -> int:
        dt = min(globalClock.getDt(), 0.04)

        self._update_camera(dt)

        if self.state == STATE_PLAYING:
            self._update_shot_anims(dt)
            self._update_markers()
            self._refresh_hud()
            self._check_game_end()
        else:
            self._update_markers()

        return Task.cont


def main() -> None:
    app = EchoProtocol3D()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
