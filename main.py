import math
import random
import sys
from dataclasses import dataclass

import pygame


SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

TILE_SIZE = 64
GRID_COLS = 50
GRID_ROWS = 34
WORLD_WIDTH = GRID_COLS * TILE_SIZE
WORLD_HEIGHT = GRID_ROWS * TILE_SIZE
WORLD_RECT = pygame.Rect(0, 0, WORLD_WIDTH, WORLD_HEIGHT)

PLAYER_MOVE_TIME = 0.11
ENEMY_MOVE_TIME = 0.13
ENEMY_STEP_INTERVAL = 0.42

BULLET_SPEED = 830
BULLET_LIFETIME = 1.2
SHOT_COOLDOWN = 0.14
ENEMY_ATTACK_COOLDOWN = 0.65
ENEMY_ATTACK_DAMAGE = 9

STATE_MENU = "menu"
STATE_PLAYING = "playing"
STATE_GAME_OVER = "game_over"


@dataclass
class Bullet:
    pos: pygame.Vector2
    vel: pygame.Vector2
    lifetime: float


@dataclass
class Enemy:
    cell: tuple[int, int]
    pos: pygame.Vector2
    move_from: pygame.Vector2
    move_to: pygame.Vector2
    move_timer: float
    step_timer: float
    hp: int
    attack_cooldown: float


@dataclass
class Player:
    cell: tuple[int, int]
    pos: pygame.Vector2
    move_from: pygame.Vector2
    move_to: pygame.Vector2
    move_timer: float
    hp: int
    shot_timer: float


class Button:
    def __init__(self, rect: pygame.Rect, text: str):
        self.rect = rect
        self.text = text

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, hovered: bool) -> None:
        bg = (38, 58, 92) if hovered else (23, 35, 62)
        outline = (140, 190, 255) if hovered else (90, 130, 190)
        pygame.draw.rect(surface, bg, self.rect, border_radius=14)
        pygame.draw.rect(surface, outline, self.rect, width=2, border_radius=14)
        txt = font.render(self.text, True, (236, 244, 255))
        surface.blit(txt, txt.get_rect(center=self.rect.center))

    def contains(self, mouse_pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(mouse_pos)


def make_grass_texture(size: int) -> pygame.Surface:
    rng = random.Random(1337)
    surf = pygame.Surface((size, size))
    surf.fill((41, 96, 56))

    for _ in range(320):
        x = rng.randrange(size)
        y = rng.randrange(size)
        shade = rng.randrange(-18, 19)
        color = (
            max(0, min(255, 46 + shade)),
            max(0, min(255, 108 + shade)),
            max(0, min(255, 62 + shade)),
        )
        surf.set_at((x, y), color)

    for _ in range(26):
        x = rng.randrange(size - 8)
        y = rng.randrange(size - 8)
        color = (50, 117, 68)
        pygame.draw.rect(surf, color, (x, y, rng.randrange(2, 6), rng.randrange(2, 5)))

    return surf


def make_wall_texture(size: int) -> pygame.Surface:
    surf = pygame.Surface((size, size))
    surf.fill((90, 92, 102))

    brick_h = size // 4
    brick_w = size // 3
    for row in range(4):
        y = row * brick_h
        offset = 0 if row % 2 == 0 else brick_w // 2
        for x in range(-brick_w + offset, size + brick_w, brick_w):
            rect = pygame.Rect(x, y, brick_w, brick_h)
            pygame.draw.rect(surf, (112, 114, 124), rect.inflate(-2, -2))
            pygame.draw.rect(surf, (75, 77, 86), rect, width=1)

    return surf


def make_player_sprite() -> pygame.Surface:
    surf = pygame.Surface((54, 54), pygame.SRCALPHA)
    pygame.draw.circle(surf, (34, 175, 246), (27, 27), 22)
    pygame.draw.circle(surf, (14, 60, 92), (27, 27), 22, width=3)
    pygame.draw.rect(surf, (236, 247, 255), (24, 4, 6, 22), border_radius=2)
    pygame.draw.circle(surf, (234, 245, 255), (27, 27), 7)
    return surf


def make_enemy_sprite() -> pygame.Surface:
    surf = pygame.Surface((46, 46), pygame.SRCALPHA)
    pygame.draw.circle(surf, (216, 66, 66), (23, 23), 18)
    pygame.draw.circle(surf, (115, 20, 20), (23, 23), 18, width=3)
    pygame.draw.circle(surf, (253, 205, 205), (17, 18), 3)
    pygame.draw.circle(surf, (253, 205, 205), (29, 18), 3)
    return surf


def cell_to_world(cell: tuple[int, int]) -> pygame.Vector2:
    return pygame.Vector2(
        cell[0] * TILE_SIZE + TILE_SIZE * 0.5,
        cell[1] * TILE_SIZE + TILE_SIZE * 0.5,
    )


def world_to_cell(pos: pygame.Vector2) -> tuple[int, int]:
    return int(pos.x // TILE_SIZE), int(pos.y // TILE_SIZE)


def cell_inside(cell: tuple[int, int]) -> bool:
    return 0 <= cell[0] < GRID_COLS and 0 <= cell[1] < GRID_ROWS


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def clamp_camera(pos: pygame.Vector2) -> pygame.Vector2:
    cx = pos.x - SCREEN_WIDTH * 0.5
    cy = pos.y - SCREEN_HEIGHT * 0.5
    cx = max(0, min(cx, WORLD_WIDTH - SCREEN_WIDTH))
    cy = max(0, min(cy, WORLD_HEIGHT - SCREEN_HEIGHT))
    return pygame.Vector2(cx, cy)


def draw_tiled_texture(
    surface: pygame.Surface,
    texture: pygame.Surface,
    rect: pygame.Rect,
    camera: pygame.Vector2,
) -> None:
    start_x = rect.left // TILE_SIZE * TILE_SIZE
    start_y = rect.top // TILE_SIZE * TILE_SIZE
    end_x = rect.right + TILE_SIZE
    end_y = rect.bottom + TILE_SIZE

    for y in range(start_y, end_y, TILE_SIZE):
        for x in range(start_x, end_x, TILE_SIZE):
            sx = x - camera.x
            sy = y - camera.y
            surface.blit(texture, (sx, sy))


def generate_wall_tiles() -> set[tuple[int, int]]:
    rng = random.Random(11)
    chunks: list[pygame.Rect] = []
    safe_zone = pygame.Rect(GRID_COLS // 2 - 5, GRID_ROWS // 2 - 4, 11, 9)

    for _ in range(85):
        w = rng.choice((2, 3, 4, 5))
        h = rng.choice((2, 3, 4))
        x = rng.randint(1, GRID_COLS - w - 2)
        y = rng.randint(1, GRID_ROWS - h - 2)
        rect = pygame.Rect(x, y, w, h)
        if rect.colliderect(safe_zone):
            continue
        if any(rect.colliderect(existing.inflate(2, 2)) for existing in chunks):
            continue
        chunks.append(rect)

    wall_tiles: set[tuple[int, int]] = set()
    for rect in chunks:
        for gy in range(rect.top, rect.bottom):
            for gx in range(rect.left, rect.right):
                wall_tiles.add((gx, gy))

    return wall_tiles


def draw_grid_overlay(screen: pygame.Surface, camera: pygame.Vector2) -> None:
    start_col = max(0, int(camera.x // TILE_SIZE))
    end_col = min(GRID_COLS - 1, int((camera.x + SCREEN_WIDTH) // TILE_SIZE) + 1)
    start_row = max(0, int(camera.y // TILE_SIZE))
    end_row = min(GRID_ROWS - 1, int((camera.y + SCREEN_HEIGHT) // TILE_SIZE) + 1)

    color = (74, 96, 116)
    for gx in range(start_col, end_col + 1):
        x = gx * TILE_SIZE - camera.x
        pygame.draw.line(screen, color, (x, 0), (x, SCREEN_HEIGHT), width=1)

    for gy in range(start_row, end_row + 1):
        y = gy * TILE_SIZE - camera.y
        pygame.draw.line(screen, color, (0, y), (SCREEN_WIDTH, y), width=1)


def draw_world(
    screen: pygame.Surface,
    grass_texture: pygame.Surface,
    wall_texture: pygame.Surface,
    wall_tiles: set[tuple[int, int]],
    camera: pygame.Vector2,
) -> None:
    visible_world = pygame.Rect(int(camera.x), int(camera.y), SCREEN_WIDTH, SCREEN_HEIGHT)
    draw_tiled_texture(screen, grass_texture, visible_world, camera)
    draw_grid_overlay(screen, camera)

    start_col = max(0, int(camera.x // TILE_SIZE))
    end_col = min(GRID_COLS - 1, int((camera.x + SCREEN_WIDTH) // TILE_SIZE) + 1)
    start_row = max(0, int(camera.y // TILE_SIZE))
    end_row = min(GRID_ROWS - 1, int((camera.y + SCREEN_HEIGHT) // TILE_SIZE) + 1)

    for gy in range(start_row, end_row + 1):
        for gx in range(start_col, end_col + 1):
            if (gx, gy) not in wall_tiles:
                continue
            x = gx * TILE_SIZE - camera.x
            y = gy * TILE_SIZE - camera.y
            screen.blit(wall_texture, (x, y))
            pygame.draw.rect(
                screen,
                (45, 47, 53),
                pygame.Rect(x, y, TILE_SIZE, TILE_SIZE),
                width=2,
            )


def make_player(cell: tuple[int, int]) -> Player:
    pos = cell_to_world(cell)
    return Player(
        cell=cell,
        pos=pygame.Vector2(pos),
        move_from=pygame.Vector2(pos),
        move_to=pygame.Vector2(pos),
        move_timer=0.0,
        hp=100,
        shot_timer=0.0,
    )


def make_enemy(cell: tuple[int, int], rng: random.Random) -> Enemy:
    pos = cell_to_world(cell)
    return Enemy(
        cell=cell,
        pos=pygame.Vector2(pos),
        move_from=pygame.Vector2(pos),
        move_to=pygame.Vector2(pos),
        move_timer=0.0,
        step_timer=rng.uniform(0.0, ENEMY_STEP_INTERVAL),
        hp=3,
        attack_cooldown=0.0,
    )


def spawn_enemies(
    count: int,
    wall_tiles: set[tuple[int, int]],
    player_cell: tuple[int, int],
) -> list[Enemy]:
    rng = random.Random(77)
    enemies: list[Enemy] = []
    occupied: set[tuple[int, int]] = {player_cell}

    attempts = 0
    while len(enemies) < count and attempts < 6000:
        attempts += 1
        cell = (rng.randint(1, GRID_COLS - 2), rng.randint(1, GRID_ROWS - 2))
        if cell in wall_tiles or cell in occupied:
            continue
        if manhattan(cell, player_cell) < 8:
            continue
        enemies.append(make_enemy(cell, rng))
        occupied.add(cell)

    return enemies


def animate_unit(pos: pygame.Vector2, move_from: pygame.Vector2, move_to: pygame.Vector2, move_timer: float, dt: float, duration: float) -> tuple[pygame.Vector2, float]:
    if move_timer <= 0:
        return pygame.Vector2(move_to), 0.0

    new_timer = max(0.0, move_timer - dt)
    t = 1.0 - (new_timer / duration)
    return move_from.lerp(move_to, t), new_timer


def cell_walkable(
    cell: tuple[int, int],
    wall_tiles: set[tuple[int, int]],
    blocked_cells: set[tuple[int, int]],
) -> bool:
    return cell_inside(cell) and cell not in wall_tiles and cell not in blocked_cells


def request_player_step(
    player: Player,
    direction: tuple[int, int],
    wall_tiles: set[tuple[int, int]],
    enemy_cells: set[tuple[int, int]],
) -> None:
    if player.move_timer > 0:
        return

    target = (player.cell[0] + direction[0], player.cell[1] + direction[1])
    if not cell_walkable(target, wall_tiles, enemy_cells):
        return

    player.cell = target
    player.move_from = pygame.Vector2(player.pos)
    player.move_to = cell_to_world(target)
    player.move_timer = PLAYER_MOVE_TIME


def choose_enemy_step(
    enemy_cell: tuple[int, int],
    player_cell: tuple[int, int],
    wall_tiles: set[tuple[int, int]],
    blocked_cells: set[tuple[int, int]],
    rng: random.Random,
) -> tuple[int, int]:
    dx = player_cell[0] - enemy_cell[0]
    dy = player_cell[1] - enemy_cell[1]

    primary_dirs: list[tuple[int, int]] = []
    if abs(dx) >= abs(dy):
        primary_dirs.append((sign(dx), 0))
        primary_dirs.append((0, sign(dy)))
    else:
        primary_dirs.append((0, sign(dy)))
        primary_dirs.append((sign(dx), 0))

    fallback_dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    rng.shuffle(fallback_dirs)
    candidate_dirs = primary_dirs + fallback_dirs

    for step in candidate_dirs:
        if step == (0, 0):
            continue
        target = (enemy_cell[0] + step[0], enemy_cell[1] + step[1])
        if cell_walkable(target, wall_tiles, blocked_cells):
            return target
    return enemy_cell


def reset_game(wall_tiles: set[tuple[int, int]]) -> tuple[Player, list[Bullet], list[Enemy], int]:
    start_cell = (GRID_COLS // 2, GRID_ROWS // 2)
    player = make_player(start_cell)
    bullets: list[Bullet] = []
    enemies = spawn_enemies(14, wall_tiles, player.cell)
    score = 0
    return player, bullets, enemies, score


def main() -> None:
    pygame.init()
    pygame.display.set_caption("ECHO PROTOCOL - Prototype")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    title_font = pygame.font.SysFont("consolas", 56, bold=True)
    menu_font = pygame.font.SysFont("consolas", 34, bold=True)
    ui_font = pygame.font.SysFont("consolas", 24)
    small_font = pygame.font.SysFont("consolas", 20)

    grass_texture = make_grass_texture(TILE_SIZE)
    wall_texture = make_wall_texture(TILE_SIZE)
    player_sprite = make_player_sprite()
    enemy_sprite = make_enemy_sprite()

    wall_tiles = generate_wall_tiles()
    player, bullets, enemies, score = reset_game(wall_tiles)

    start_button = Button(pygame.Rect(SCREEN_WIDTH // 2 - 140, 360, 280, 60), "Start Mission")
    quit_button = Button(pygame.Rect(SCREEN_WIDTH // 2 - 140, 440, 280, 60), "Exit")

    movement_keys: dict[int, tuple[int, int]] = {
        pygame.K_w: (0, -1),
        pygame.K_UP: (0, -1),
        pygame.K_s: (0, 1),
        pygame.K_DOWN: (0, 1),
        pygame.K_a: (-1, 0),
        pygame.K_LEFT: (-1, 0),
        pygame.K_d: (1, 0),
        pygame.K_RIGHT: (1, 0),
    }

    enemy_rng = random.Random(1234)
    state = STATE_MENU
    running = True

    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.04)
        mouse = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if state == STATE_MENU:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if start_button.contains(mouse):
                        player, bullets, enemies, score = reset_game(wall_tiles)
                        state = STATE_PLAYING
                    elif quit_button.contains(mouse):
                        running = False

            elif state in (STATE_PLAYING, STATE_GAME_OVER):
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    state = STATE_MENU

                if state == STATE_GAME_OVER and event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    player, bullets, enemies, score = reset_game(wall_tiles)
                    state = STATE_PLAYING

                if state == STATE_PLAYING and event.type == pygame.KEYDOWN and event.key in movement_keys:
                    enemy_cells = {enemy.cell for enemy in enemies}
                    request_player_step(player, movement_keys[event.key], wall_tiles, enemy_cells)

                if state == STATE_PLAYING and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if player.shot_timer <= 0:
                        camera = clamp_camera(player.pos)
                        world_mouse = pygame.Vector2(mouse[0] + camera.x, mouse[1] + camera.y)
                        direction = world_mouse - player.pos
                        if direction.length_squared() > 0:
                            velocity = direction.normalize() * BULLET_SPEED
                            bullets.append(Bullet(pos=pygame.Vector2(player.pos), vel=velocity, lifetime=BULLET_LIFETIME))
                            player.shot_timer = SHOT_COOLDOWN

        if state == STATE_MENU:
            for y in range(SCREEN_HEIGHT):
                t = y / SCREEN_HEIGHT
                color = (int(9 + 14 * t), int(15 + 30 * t), int(31 + 60 * t))
                pygame.draw.line(screen, color, (0, y), (SCREEN_WIDTH, y))

            title = title_font.render("ECHO PROTOCOL", True, (235, 246, 255))
            subtitle = ui_font.render("Prototype: grid move + shooting", True, (188, 210, 233))
            screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 190)))
            screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 250)))

            start_button.draw(screen, menu_font, start_button.contains(mouse))
            quit_button.draw(screen, menu_font, quit_button.contains(mouse))

            info = [
                "WASD / Arrows - step by grid",
                "Mouse Left - shoot",
                "ESC - menu",
            ]
            for i, line in enumerate(info):
                txt = small_font.render(line, True, (196, 216, 236))
                screen.blit(txt, (20, SCREEN_HEIGHT - 90 + i * 24))

            pygame.display.flip()
            continue

        player.pos, player.move_timer = animate_unit(
            player.pos,
            player.move_from,
            player.move_to,
            player.move_timer,
            dt,
            PLAYER_MOVE_TIME,
        )
        player.shot_timer = max(0.0, player.shot_timer - dt)

        if state == STATE_PLAYING:
            alive_bullets: list[Bullet] = []
            for bullet in bullets:
                bullet.pos += bullet.vel * dt
                bullet.lifetime -= dt
                if bullet.lifetime <= 0:
                    continue
                if not WORLD_RECT.collidepoint(bullet.pos.x, bullet.pos.y):
                    continue

                bullet_cell = world_to_cell(bullet.pos)
                if bullet_cell in wall_tiles:
                    continue

                hit_enemy = None
                for enemy in enemies:
                    if enemy.pos.distance_to(bullet.pos) < 22:
                        hit_enemy = enemy
                        break
                if hit_enemy is not None:
                    hit_enemy.hp -= 1
                    if hit_enemy.hp <= 0:
                        enemies.remove(hit_enemy)
                        score += 1
                    continue

                alive_bullets.append(bullet)
            bullets = alive_bullets

            for enemy in enemies:
                enemy.pos, enemy.move_timer = animate_unit(
                    enemy.pos,
                    enemy.move_from,
                    enemy.move_to,
                    enemy.move_timer,
                    dt,
                    ENEMY_MOVE_TIME,
                )
                enemy.step_timer = max(0.0, enemy.step_timer - dt)
                enemy.attack_cooldown = max(0.0, enemy.attack_cooldown - dt)

            enemy_cells_snapshot = {enemy.cell for enemy in enemies}
            for enemy in enemies:
                if manhattan(enemy.cell, player.cell) == 1 and enemy.attack_cooldown <= 0:
                    player.hp -= ENEMY_ATTACK_DAMAGE
                    enemy.attack_cooldown = ENEMY_ATTACK_COOLDOWN
                    continue

                if enemy.move_timer > 0 or enemy.step_timer > 0:
                    continue

                blocked_cells = set(enemy_cells_snapshot)
                blocked_cells.discard(enemy.cell)
                blocked_cells.add(player.cell)
                target = choose_enemy_step(enemy.cell, player.cell, wall_tiles, blocked_cells, enemy_rng)
                enemy.step_timer = ENEMY_STEP_INTERVAL
                if target != enemy.cell:
                    enemy_cells_snapshot.discard(enemy.cell)
                    enemy.cell = target
                    enemy_cells_snapshot.add(enemy.cell)
                    enemy.move_from = pygame.Vector2(enemy.pos)
                    enemy.move_to = cell_to_world(target)
                    enemy.move_timer = ENEMY_MOVE_TIME

            if player.hp <= 0:
                state = STATE_GAME_OVER

        camera = clamp_camera(player.pos)
        draw_world(screen, grass_texture, wall_texture, wall_tiles, camera)

        for bullet in bullets:
            sx = int(bullet.pos.x - camera.x)
            sy = int(bullet.pos.y - camera.y)
            pygame.draw.circle(screen, (255, 230, 130), (sx, sy), 4)
            pygame.draw.circle(screen, (255, 255, 220), (sx, sy), 2)

        for enemy in enemies:
            draw_pos = (enemy.pos.x - camera.x, enemy.pos.y - camera.y)
            screen.blit(enemy_sprite, enemy_sprite.get_rect(center=draw_pos))

        world_mouse = pygame.Vector2(mouse[0] + camera.x, mouse[1] + camera.y)
        aim_vec = world_mouse - player.pos
        angle = -math.degrees(math.atan2(aim_vec.y, aim_vec.x)) + 90 if aim_vec.length_squared() > 0 else 0
        rotated = pygame.transform.rotozoom(player_sprite, angle, 1.0)
        screen.blit(rotated, rotated.get_rect(center=(player.pos.x - camera.x, player.pos.y - camera.y)))

        hud_bg = pygame.Surface((380, 112), pygame.SRCALPHA)
        pygame.draw.rect(hud_bg, (8, 10, 20, 190), hud_bg.get_rect(), border_radius=12)
        screen.blit(hud_bg, (14, 14))
        hp_color = (122, 238, 150) if player.hp > 40 else (255, 184, 94) if player.hp > 20 else (255, 100, 100)
        hp_txt = ui_font.render(f"HP: {max(0, player.hp)}", True, hp_color)
        score_txt = ui_font.render(f"Kills: {score}", True, (218, 232, 248))
        left_txt = ui_font.render(f"Enemies: {len(enemies)}", True, (218, 232, 248))
        cell_txt = small_font.render(f"Cell: {player.cell[0]}, {player.cell[1]}", True, (196, 216, 236))
        screen.blit(hp_txt, (28, 24))
        screen.blit(score_txt, (28, 50))
        screen.blit(left_txt, (170, 50))
        screen.blit(cell_txt, (28, 80))

        controls = small_font.render("WASD step grid | LMB shoot | ESC menu", True, (220, 236, 255))
        screen.blit(controls, (18, SCREEN_HEIGHT - 32))

        if state == STATE_GAME_OVER:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((5, 8, 16, 170))
            screen.blit(overlay, (0, 0))
            g1 = title_font.render("MISSION FAILED", True, (255, 210, 210))
            g2 = menu_font.render("Press R to restart", True, (230, 236, 250))
            g3 = small_font.render("Press ESC to return menu", True, (198, 216, 239))
            screen.blit(g1, g1.get_rect(center=(SCREEN_WIDTH // 2, 270)))
            screen.blit(g2, g2.get_rect(center=(SCREEN_WIDTH // 2, 350)))
            screen.blit(g3, g3.get_rect(center=(SCREEN_WIDTH // 2, 395)))

        pygame.display.flip()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
