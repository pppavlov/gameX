import math
import random
import sys
from dataclasses import dataclass

import pygame


SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

WORLD_WIDTH = 3200
WORLD_HEIGHT = 2200
WORLD_RECT = pygame.Rect(0, 0, WORLD_WIDTH, WORLD_HEIGHT)

TILE_SIZE = 64
PLAYER_RADIUS = 20
PLAYER_SPEED = 310
BULLET_SPEED = 830
BULLET_LIFETIME = 1.2
SHOT_COOLDOWN = 0.14
ENEMY_SPEED = 120

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
    pos: pygame.Vector2
    hp: int
    attack_cooldown: float


@dataclass
class Player:
    pos: pygame.Vector2
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


def clamp_camera(pos: pygame.Vector2) -> pygame.Vector2:
    cx = pos.x - SCREEN_WIDTH * 0.5
    cy = pos.y - SCREEN_HEIGHT * 0.5
    cx = max(0, min(cx, WORLD_WIDTH - SCREEN_WIDTH))
    cy = max(0, min(cy, WORLD_HEIGHT - SCREEN_HEIGHT))
    return pygame.Vector2(cx, cy)


def move_with_collisions(
    start_pos: pygame.Vector2,
    velocity: pygame.Vector2,
    dt: float,
    radius: int,
    obstacles: list[pygame.Rect],
) -> pygame.Vector2:
    new_pos = pygame.Vector2(start_pos)
    step = velocity * dt

    if step.x != 0:
        new_pos.x += step.x
        test_rect = pygame.Rect(0, 0, radius * 2, radius * 2)
        test_rect.center = (new_pos.x, start_pos.y)
        for wall in obstacles:
            if test_rect.colliderect(wall):
                if step.x > 0:
                    new_pos.x = wall.left - radius
                else:
                    new_pos.x = wall.right + radius
                test_rect.centerx = new_pos.x

    if step.y != 0:
        new_pos.y += step.y
        test_rect = pygame.Rect(0, 0, radius * 2, radius * 2)
        test_rect.center = (new_pos.x, new_pos.y)
        for wall in obstacles:
            if test_rect.colliderect(wall):
                if step.y > 0:
                    new_pos.y = wall.top - radius
                else:
                    new_pos.y = wall.bottom + radius
                test_rect.centery = new_pos.y

    new_pos.x = max(radius, min(WORLD_WIDTH - radius, new_pos.x))
    new_pos.y = max(radius, min(WORLD_HEIGHT - radius, new_pos.y))
    return new_pos


def generate_obstacles() -> list[pygame.Rect]:
    rng = random.Random(11)
    obstacles: list[pygame.Rect] = []
    safe_zone = pygame.Rect(1250, 880, 700, 450)

    for _ in range(44):
        w = rng.choice((120, 160, 200, 260))
        h = rng.choice((90, 120, 150, 180))
        x = rng.randint(80, WORLD_WIDTH - w - 80)
        y = rng.randint(80, WORLD_HEIGHT - h - 80)
        rect = pygame.Rect(x, y, w, h)
        if rect.colliderect(safe_zone):
            continue
        if any(rect.colliderect(existing.inflate(12, 12)) for existing in obstacles):
            continue
        obstacles.append(rect)
    return obstacles


def spawn_enemies(count: int, obstacles: list[pygame.Rect]) -> list[Enemy]:
    rng = random.Random(77)
    enemies: list[Enemy] = []
    safe_center = pygame.Vector2(WORLD_WIDTH * 0.5, WORLD_HEIGHT * 0.5)

    while len(enemies) < count:
        pos = pygame.Vector2(rng.randint(60, WORLD_WIDTH - 60), rng.randint(60, WORLD_HEIGHT - 60))
        if pos.distance_to(safe_center) < 320:
            continue
        test = pygame.Rect(0, 0, 44, 44)
        test.center = (pos.x, pos.y)
        if any(test.colliderect(wall) for wall in obstacles):
            continue
        enemies.append(Enemy(pos=pos, hp=3, attack_cooldown=0))

    return enemies


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


def draw_world(
    screen: pygame.Surface,
    grass_texture: pygame.Surface,
    wall_texture: pygame.Surface,
    obstacles: list[pygame.Rect],
    camera: pygame.Vector2,
) -> None:
    visible_world = pygame.Rect(
        int(camera.x),
        int(camera.y),
        SCREEN_WIDTH,
        SCREEN_HEIGHT,
    )

    draw_tiled_texture(screen, grass_texture, visible_world, camera)

    for wall in obstacles:
        if not wall.colliderect(visible_world):
            continue
        draw_tiled_texture(screen, wall_texture, wall, camera)
        screen_rect = wall.move(-camera.x, -camera.y)
        pygame.draw.rect(screen, (45, 47, 53), screen_rect, width=2)


def reset_game(obstacles: list[pygame.Rect]) -> tuple[Player, list[Bullet], list[Enemy], int]:
    player = Player(pos=pygame.Vector2(WORLD_WIDTH * 0.5, WORLD_HEIGHT * 0.5), hp=100, shot_timer=0)
    bullets: list[Bullet] = []
    enemies = spawn_enemies(14, obstacles)
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

    obstacles = generate_obstacles()
    player, bullets, enemies, score = reset_game(obstacles)

    start_button = Button(pygame.Rect(SCREEN_WIDTH // 2 - 140, 360, 280, 60), "Start Mission")
    quit_button = Button(pygame.Rect(SCREEN_WIDTH // 2 - 140, 440, 280, 60), "Exit")

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
                        player, bullets, enemies, score = reset_game(obstacles)
                        state = STATE_PLAYING
                    elif quit_button.contains(mouse):
                        running = False

            elif state in (STATE_PLAYING, STATE_GAME_OVER):
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    state = STATE_MENU

                if state == STATE_GAME_OVER and event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    player, bullets, enemies, score = reset_game(obstacles)
                    state = STATE_PLAYING

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
                color = (
                    int(9 + 14 * t),
                    int(15 + 30 * t),
                    int(31 + 60 * t),
                )
                pygame.draw.line(screen, color, (0, y), (SCREEN_WIDTH, y))

            title = title_font.render("ECHO PROTOCOL", True, (235, 246, 255))
            subtitle = ui_font.render("Prototype: run, shoot, survive", True, (188, 210, 233))
            screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 190)))
            screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 250)))

            start_button.draw(screen, menu_font, start_button.contains(mouse))
            quit_button.draw(screen, menu_font, quit_button.contains(mouse))

            info = [
                "WASD / Arrows - move",
                "Mouse Left - shoot",
                "ESC - menu",
            ]
            for i, line in enumerate(info):
                txt = small_font.render(line, True, (196, 216, 236))
                screen.blit(txt, (20, SCREEN_HEIGHT - 90 + i * 24))

            pygame.display.flip()
            continue

        keys = pygame.key.get_pressed()
        move = pygame.Vector2(
            (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - (1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0),
            (1 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0) - (1 if keys[pygame.K_w] or keys[pygame.K_UP] else 0),
        )
        if move.length_squared() > 0:
            move = move.normalize() * PLAYER_SPEED
            player.pos = move_with_collisions(player.pos, move, dt, PLAYER_RADIUS, obstacles)

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

                hit_wall = any(wall.collidepoint(bullet.pos.x, bullet.pos.y) for wall in obstacles)
                if hit_wall:
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
                enemy.attack_cooldown = max(0.0, enemy.attack_cooldown - dt)

                to_player = player.pos - enemy.pos
                if to_player.length_squared() > 0:
                    direction = to_player.normalize()
                else:
                    direction = pygame.Vector2()
                enemy_velocity = direction * ENEMY_SPEED
                enemy.pos = move_with_collisions(enemy.pos, enemy_velocity, dt, 18, obstacles)

                if enemy.pos.distance_to(player.pos) < 36 and enemy.attack_cooldown <= 0:
                    player.hp -= 9
                    enemy.attack_cooldown = 0.65

            if player.hp <= 0:
                state = STATE_GAME_OVER

        camera = clamp_camera(player.pos)
        draw_world(screen, grass_texture, wall_texture, obstacles, camera)

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

        hud_bg = pygame.Surface((300, 92), pygame.SRCALPHA)
        pygame.draw.rect(hud_bg, (8, 10, 20, 180), hud_bg.get_rect(), border_radius=12)
        screen.blit(hud_bg, (14, 14))
        hp_color = (122, 238, 150) if player.hp > 40 else (255, 184, 94) if player.hp > 20 else (255, 100, 100)
        hp_txt = ui_font.render(f"HP: {max(0, player.hp)}", True, hp_color)
        score_txt = ui_font.render(f"Kills: {score}", True, (218, 232, 248))
        left_txt = ui_font.render(f"Enemies: {len(enemies)}", True, (218, 232, 248))
        screen.blit(hp_txt, (28, 24))
        screen.blit(score_txt, (28, 50))
        screen.blit(left_txt, (160, 50))

        controls = small_font.render("WASD move | LMB shoot | ESC menu", True, (220, 236, 255))
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
