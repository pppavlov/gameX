import math
import random
import sys
from dataclasses import dataclass

from panda3d.core import (
    AmbientLight,
    DirectionalLight,
    NodePath,
    PNMImage,
    Point3,
    SamplerState,
    TextNode,
    Texture,
    Vec2,
    WindowProperties,
    loadPrcFileData,
)

# Force explicit display backends: hardware first, then software fallback.
loadPrcFileData("", "load-display pandagl")
loadPrcFileData("", "aux-display pandadx9")
loadPrcFileData("", "aux-display p3tinydisplay")
loadPrcFileData("", "notify-level-display warning")

from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task


WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

GRID_W = 26
GRID_H = 26
TILE = 2.0
HALF_WORLD_X = GRID_W * TILE * 0.5
HALF_WORLD_Y = GRID_H * TILE * 0.5

PLAYER_SPEED = 10.5
PLAYER_RADIUS = 0.55
PLAYER_MAX_HP = 100

ENEMY_SPEED = 4.2
ENEMY_RADIUS = 0.55
ENEMY_DAMAGE = 8
ENEMY_ATTACK_RANGE = 1.7
ENEMY_ATTACK_COOLDOWN = 0.9

SHOT_COOLDOWN = 0.16
SHOT_RANGE = 26.0

STATE_MENU = "menu"
STATE_PLAYING = "playing"
STATE_GAME_OVER = "game_over"


@dataclass
class Cover:
    node: NodePath
    x: float
    y: float
    half_size: float
    hp: int


@dataclass
class Enemy:
    node: NodePath
    x: float
    y: float
    hp: int
    attack_cd: float


class EchoProtocol3D(ShowBase):
    def __init__(self) -> None:
        super().__init__()

        props = WindowProperties()
        props.setSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        props.setTitle("ECHO PROTOCOL 3D - Python Prototype")
        if self.win is not None and hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)

        self.setBackgroundColor(0.06, 0.08, 0.12, 1)
        self.disableMouse()
        self.camera.setPos(0, -42, 50)
        self.camera.setHpr(0, -62, 0)
        self.camLens.setFov(58)

        self.rng = random.Random(20260301)

        self.tex_ground = self._make_checker_texture("ground", (52, 100, 70), (44, 84, 60), 128, 8)
        self.tex_wall = self._make_checker_texture("wall", (95, 98, 110), (78, 82, 92), 128, 8)
        self.tex_cover = self._make_checker_texture("cover", (126, 110, 84), (102, 86, 64), 128, 8)
        self.tex_player = self._make_checker_texture("player", (55, 178, 248), (38, 130, 190), 64, 8)
        self.tex_enemy = self._make_checker_texture("enemy", (217, 78, 78), (150, 44, 44), 64, 8)

        self._setup_lights()
        self._setup_input()
        self._setup_ui()

        self.world_root = self.render.attachNewNode("world")
        self.ground = None

        self.player = None
        self.player_x = 0.0
        self.player_y = 0.0
        self.player_hp = PLAYER_MAX_HP
        self.score = 0
        self.last_shot_time = 0.0

        self.covers: list[Cover] = []
        self.enemies: list[Enemy] = []

        self.state = STATE_MENU
        self.victory = False

        self._show_menu()
        self.taskMgr.add(self._update, "update")

    def _setup_lights(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.setColor((0.52, 0.56, 0.64, 1))
        ambient_np = self.render.attachNewNode(ambient)
        self.render.setLight(ambient_np)

        sun = DirectionalLight("sun")
        sun.setColor((0.86, 0.88, 0.92, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(18, -58, 0)
        self.render.setLight(sun_np)

    def _setup_input(self) -> None:
        self.key_map = {"w": False, "a": False, "s": False, "d": False}
        for key in self.key_map.keys():
            self.accept(key, self._set_key, [key, True])
            self.accept(f"{key}-up", self._set_key, [key, False])

        self.accept("mouse1", self._fire)
        self.accept("enter", self._handle_enter)
        self.accept("escape", self._handle_escape)
        self.accept("r", self._handle_restart)

    def _setup_ui(self) -> None:
        self.menu_title = OnscreenText(
            text="ECHO PROTOCOL 3D",
            pos=(0, 0.36),
            scale=0.1,
            fg=(0.93, 0.97, 1, 1),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.menu_subtitle = OnscreenText(
            text="Python + Panda3D | Top-down 3D prototype",
            pos=(0, 0.24),
            scale=0.045,
            fg=(0.76, 0.84, 0.92, 1),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.menu_hint = OnscreenText(
            text="ENTER - start | ESC - exit",
            pos=(0, 0.11),
            scale=0.05,
            fg=(0.83, 0.9, 0.97, 1),
            align=TextNode.ACenter,
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

        self.hud = OnscreenText(
            text="",
            pos=(-1.32, 0.92),
            scale=0.045,
            fg=(0.91, 0.97, 1, 1),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.controls = OnscreenText(
            text="WASD move | LMB shoot | R restart | ESC menu",
            pos=(-1.32, -0.92),
            scale=0.038,
            fg=(0.82, 0.88, 0.95, 1),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.log = OnscreenText(
            text="",
            pos=(-1.32, 0.8),
            scale=0.036,
            fg=(0.95, 0.9, 0.7, 1),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.log_message = ""

        self._toggle_hud(False)
        self.gameover_text.hide()

    def _toggle_hud(self, visible: bool) -> None:
        if visible:
            self.hud.show()
            self.controls.show()
            self.log.show()
        else:
            self.hud.hide()
            self.controls.hide()
            self.log.hide()

    def _set_key(self, key: str, value: bool) -> None:
        self.key_map[key] = value

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

    def _show_menu(self) -> None:
        self.state = STATE_MENU
        self.menu_title.show()
        self.menu_subtitle.show()
        self.menu_hint.show()
        self.gameover_text.hide()
        self._toggle_hud(False)

    def _hide_menu(self) -> None:
        self.menu_title.hide()
        self.menu_subtitle.hide()
        self.menu_hint.hide()

    def _cleanup_world(self) -> None:
        self.world_root.removeNode()
        self.world_root = self.render.attachNewNode("world")
        self.covers = []
        self.enemies = []
        self.player = None

    def _start_game(self) -> None:
        self._cleanup_world()

        self.state = STATE_PLAYING
        self.victory = False
        self.player_hp = PLAYER_MAX_HP
        self.score = 0
        self.last_shot_time = 0.0
        self.log_message = "Mission started"

        ground_model = self.loader.loadModel("models/box")
        ground_model.reparentTo(self.world_root)
        ground_model.setScale(HALF_WORLD_X, HALF_WORLD_Y, 0.05)
        ground_model.setPos(0, 0, -0.05)
        ground_model.setTexture(self.tex_ground, 1)
        self.ground = ground_model

        self._spawn_boundaries()
        self._spawn_covers(80)
        self._spawn_player()
        self._spawn_enemies(18)

        self._hide_menu()
        self.gameover_text.hide()
        self._toggle_hud(True)
        self._refresh_hud()

    def _spawn_boundaries(self) -> None:
        block = self.loader.loadModel("models/box")
        block.setScale(0.5, 0.5, 1.0)
        for gx in range(GRID_W):
            for gy in (0, GRID_H - 1):
                node = block.copyTo(self.world_root)
                x, y = self._grid_to_world(gx, gy)
                node.setPos(x, y, 1.0)
                node.setTexture(self.tex_wall, 1)
                self.covers.append(Cover(node=node, x=x, y=y, half_size=0.95, hp=999))
        for gy in range(1, GRID_H - 1):
            for gx in (0, GRID_W - 1):
                node = block.copyTo(self.world_root)
                x, y = self._grid_to_world(gx, gy)
                node.setPos(x, y, 1.0)
                node.setTexture(self.tex_wall, 1)
                self.covers.append(Cover(node=node, x=x, y=y, half_size=0.95, hp=999))
        block.removeNode()

    def _spawn_covers(self, count: int) -> None:
        block = self.loader.loadModel("models/box")
        attempts = 0
        placed = 0

        while placed < count and attempts < count * 20:
            attempts += 1
            gx = self.rng.randint(2, GRID_W - 3)
            gy = self.rng.randint(2, GRID_H - 3)
            x, y = self._grid_to_world(gx, gy)

            if abs(x) < 4 and abs(y) < 4:
                continue
            if self._circle_hits_cover(x, y, 0.9):
                continue

            node = block.copyTo(self.world_root)
            height = self.rng.choice([0.8, 1.0, 1.2])
            node.setScale(0.5, 0.5, height)
            node.setPos(x, y, height)
            node.setTexture(self.tex_cover, 1)

            hp = 2 if height <= 1.0 else 3
            self.covers.append(Cover(node=node, x=x, y=y, half_size=0.9, hp=hp))
            placed += 1

        block.removeNode()

    def _spawn_player(self) -> None:
        node = self.loader.loadModel("models/box")
        node.reparentTo(self.world_root)
        node.setScale(0.45, 0.45, 0.95)
        node.setTexture(self.tex_player, 1)
        self.player = node
        self.player_x = 0.0
        self.player_y = 0.0
        self.player.setPos(self.player_x, self.player_y, 0.95)

    def _spawn_enemies(self, count: int) -> None:
        model = self.loader.loadModel("models/box")
        placed = 0
        attempts = 0

        while placed < count and attempts < count * 40:
            attempts += 1
            gx = self.rng.randint(1, GRID_W - 2)
            gy = self.rng.randint(1, GRID_H - 2)
            x, y = self._grid_to_world(gx, gy)

            if math.hypot(x - self.player_x, y - self.player_y) < 10:
                continue
            if self._circle_hits_cover(x, y, 0.8):
                continue
            if any(math.hypot(x - enemy.x, y - enemy.y) < 1.5 for enemy in self.enemies):
                continue

            node = model.copyTo(self.world_root)
            node.setScale(0.45, 0.45, 0.85)
            node.setPos(x, y, 0.85)
            node.setTexture(self.tex_enemy, 1)
            self.enemies.append(Enemy(node=node, x=x, y=y, hp=3, attack_cd=0.0))
            placed += 1

        model.removeNode()

    def _grid_to_world(self, gx: int, gy: int) -> tuple[float, float]:
        x = -HALF_WORLD_X + gx * TILE + TILE * 0.5
        y = -HALF_WORLD_Y + gy * TILE + TILE * 0.5
        return x, y

    def _clamp_world(self, x: float, y: float, radius: float) -> tuple[float, float]:
        x = max(-HALF_WORLD_X + radius, min(HALF_WORLD_X - radius, x))
        y = max(-HALF_WORLD_Y + radius, min(HALF_WORLD_Y - radius, y))
        return x, y

    def _circle_hits_cover(self, x: float, y: float, radius: float) -> bool:
        for cover in self.covers:
            if cover.hp <= 0:
                continue
            if abs(x - cover.x) <= (radius + cover.half_size) and abs(y - cover.y) <= (radius + cover.half_size):
                return True
        return False

    def _can_move_to(self, x: float, y: float, radius: float) -> bool:
        x, y = self._clamp_world(x, y, radius)
        if self._circle_hits_cover(x, y, radius):
            return False
        return True

    def _try_move_player(self, dx: float, dy: float) -> None:
        new_x = self.player_x + dx
        new_y = self.player_y
        if self._can_move_to(new_x, new_y, PLAYER_RADIUS):
            self.player_x = new_x

        new_x = self.player_x
        new_y = self.player_y + dy
        if self._can_move_to(new_x, new_y, PLAYER_RADIUS):
            self.player_y = new_y

        self.player_x, self.player_y = self._clamp_world(self.player_x, self.player_y, PLAYER_RADIUS)
        self.player.setPos(self.player_x, self.player_y, 0.95)

    def _mouse_to_ground(self) -> Point3 | None:
        if not self.mouseWatcherNode.hasMouse():
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

    def _fire(self) -> None:
        if self.state != STATE_PLAYING:
            return

        now = globalClock.getFrameTime()
        if now - self.last_shot_time < SHOT_COOLDOWN:
            return

        target = self._mouse_to_ground()
        if target is None:
            return

        shot_vec = Vec2(target.x - self.player_x, target.y - self.player_y)
        if shot_vec.lengthSquared() < 1e-6:
            return
        shot_dir = shot_vec.normalized()

        candidates: list[tuple[float, str, int]] = []

        for idx, enemy in enumerate(self.enemies):
            if enemy.hp <= 0:
                continue
            t, dist = self._distance_to_ray(self.player_x, self.player_y, shot_dir, enemy.x, enemy.y)
            if 0 <= t <= SHOT_RANGE and dist <= 0.75:
                candidates.append((t, "enemy", idx))

        for idx, cover in enumerate(self.covers):
            if cover.hp <= 0:
                continue
            t, dist = self._distance_to_ray(self.player_x, self.player_y, shot_dir, cover.x, cover.y)
            if 0 <= t <= SHOT_RANGE and dist <= (cover.half_size + 0.15):
                candidates.append((t, "cover", idx))

        self.last_shot_time = now
        if not candidates:
            self.log_message = "Shot missed"
            return

        candidates.sort(key=lambda item: item[0])
        _, hit_type, hit_idx = candidates[0]

        if hit_type == "enemy":
            enemy = self.enemies[hit_idx]
            enemy.hp -= 1
            if enemy.hp <= 0:
                self.score += 1
                enemy.node.removeNode()
                self.log_message = "Enemy down"
            else:
                self.log_message = "Enemy hit"
        else:
            cover = self.covers[hit_idx]
            if cover.hp >= 900:
                self.log_message = "Boundary wall"
            else:
                cover.hp -= 1
                if cover.hp <= 0:
                    cover.node.removeNode()
                    self.log_message = "Cover destroyed"
                else:
                    self.log_message = "Cover damaged"

    def _distance_to_ray(self, sx: float, sy: float, direction: Vec2, ox: float, oy: float) -> tuple[float, float]:
        vx = ox - sx
        vy = oy - sy
        t = vx * direction.x + vy * direction.y
        closest_x = sx + direction.x * t
        closest_y = sy + direction.y * t
        dist = math.hypot(ox - closest_x, oy - closest_y)
        return t, dist

    def _update_enemies(self, dt: float) -> None:
        for enemy in self.enemies:
            if enemy.hp <= 0:
                continue

            enemy.attack_cd = max(0.0, enemy.attack_cd - dt)
            dx = self.player_x - enemy.x
            dy = self.player_y - enemy.y
            dist = math.hypot(dx, dy)

            if dist <= ENEMY_ATTACK_RANGE:
                if enemy.attack_cd <= 0:
                    self.player_hp -= ENEMY_DAMAGE
                    enemy.attack_cd = ENEMY_ATTACK_COOLDOWN
                    self.log_message = "Player hit"
                continue

            if dist < 1e-6:
                continue

            step = ENEMY_SPEED * dt
            mvx = dx / dist * step
            mvy = dy / dist * step

            cand_x = enemy.x + mvx
            cand_y = enemy.y
            if self._can_enemy_move_to(enemy, cand_x, cand_y):
                enemy.x = cand_x

            cand_x = enemy.x
            cand_y = enemy.y + mvy
            if self._can_enemy_move_to(enemy, cand_x, cand_y):
                enemy.y = cand_y

            enemy.x, enemy.y = self._clamp_world(enemy.x, enemy.y, ENEMY_RADIUS)
            enemy.node.setPos(enemy.x, enemy.y, 0.85)

    def _can_enemy_move_to(self, moving_enemy: Enemy, x: float, y: float) -> bool:
        if self._circle_hits_cover(x, y, ENEMY_RADIUS):
            return False
        for other in self.enemies:
            if other is moving_enemy or other.hp <= 0:
                continue
            if math.hypot(x - other.x, y - other.y) < (ENEMY_RADIUS + ENEMY_RADIUS - 0.05):
                return False
        return True

    def _refresh_hud(self) -> None:
        alive_enemies = sum(1 for enemy in self.enemies if enemy.hp > 0)
        self.hud.setText(
            f"HP: {max(0, self.player_hp)}\n"
            f"Kills: {self.score}\n"
            f"Enemies: {alive_enemies}\n"
            f"Cover blocks: {sum(1 for c in self.covers if c.hp > 0 and c.hp < 900)}"
        )
        self.log.setText(self.log_message)

    def _handle_enter(self) -> None:
        if self.state in (STATE_MENU, STATE_GAME_OVER):
            self._start_game()

    def _handle_restart(self) -> None:
        if self.state == STATE_GAME_OVER:
            self._start_game()

    def _handle_escape(self) -> None:
        if self.state == STATE_PLAYING:
            self._cleanup_world()
            self._show_menu()
            return
        self.userExit()

    def _finish_game(self, victory: bool) -> None:
        self.state = STATE_GAME_OVER
        self.victory = victory
        self._toggle_hud(False)

        if victory:
            self.gameover_text.setFg((0.66, 0.95, 0.7, 1))
            self.gameover_text.setText("MISSION COMPLETE\nENTER - new mission | ESC - exit")
        else:
            self.gameover_text.setFg((0.97, 0.72, 0.72, 1))
            self.gameover_text.setText("MISSION FAILED\nR or ENTER - restart | ESC - exit")

        self.gameover_text.show()

    def _update(self, task: Task) -> int:
        dt = min(globalClock.getDt(), 0.04)

        if self.state == STATE_PLAYING:
            move = Vec2(
                (1 if self.key_map["d"] else 0) - (1 if self.key_map["a"] else 0),
                (1 if self.key_map["w"] else 0) - (1 if self.key_map["s"] else 0),
            )
            if move.lengthSquared() > 0:
                move = move.normalized()
                self._try_move_player(move.x * PLAYER_SPEED * dt, move.y * PLAYER_SPEED * dt)

            self._update_enemies(dt)
            self._refresh_hud()

            if self.player_hp <= 0:
                self._finish_game(victory=False)
            elif sum(1 for enemy in self.enemies if enemy.hp > 0) == 0:
                self._finish_game(victory=True)

        return Task.cont


def main() -> None:
    app = EchoProtocol3D()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
