import random
import sys
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import pygame


SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

MAP_X = 16
MAP_Y = 16
TILE_SIZE = 48
GRID_COLS = 20
GRID_ROWS = 14
MAP_WIDTH = GRID_COLS * TILE_SIZE
MAP_HEIGHT = GRID_ROWS * TILE_SIZE
PANEL_X = MAP_X + MAP_WIDTH + 16
PANEL_WIDTH = SCREEN_WIDTH - PANEL_X - 16

PLAYER_VISION = 9
MAX_MOVE_STEPS_1_AP = 4
MAX_MOVE_STEPS_2_AP = 8

STATE_MENU = "menu"
STATE_GEOSCAPE = "geoscape"
STATE_BATTLE = "battle"
STATE_CAMPAIGN_OVER = "campaign_over"

Cell = tuple[int, int]


@dataclass
class CoverObject:
    kind: str
    hp: int


@dataclass
class ResearchProject:
    key: str
    name: str
    description: str
    cost: int
    progress: int = 0
    completed: bool = False


@dataclass
class MissionCard:
    mission_id: int
    title: str
    threat: int
    enemy_count: int
    pod_count: int
    reward_supplies: int
    reward_science: int
    reward_intel: int


@dataclass
class CampaignSoldier:
    sid: str
    name: str
    role: str
    max_hp: int
    hp: int
    aim: int
    defense: int
    level: int = 1
    xp: int = 0
    alive: bool = True


@dataclass
class BattleUnit:
    unit_id: str
    sid: Optional[str]
    name: str
    team: str
    role: str
    cell: Cell
    hp: int
    max_hp: int
    aim: int
    defense: int
    ap: int = 2
    alive: bool = True
    overwatch: bool = False
    suppressed: bool = False
    suppression_from: Optional[str] = None
    fortify: bool = False
    sync_shot: bool = False
    pod_id: int = -1
    active: bool = True
    enemy_type: str = "trooper"
    rewind_used: bool = False
    phase_visible: bool = True
    kills: int = 0


@dataclass
class BattleState:
    mission: MissionCard
    walls: set[Cell]
    covers: dict[Cell, CoverObject]
    player_units: list[BattleUnit]
    enemy_units: list[BattleUnit]
    selected_player_id: Optional[str] = None
    selected_enemy_id: Optional[str] = None
    turn_side: str = "player"
    turn_number: int = 1
    visible_cells: set[Cell] = field(default_factory=set)
    explored_cells: set[Cell] = field(default_factory=set)
    mission_result: Optional[str] = None
    pending_rewards: dict[str, int] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)


@dataclass
class CampaignState:
    supplies: int
    science: int
    intel: int
    mission_index: int
    threat: int
    lab_level: int
    armory_level: int
    relay_level: int
    passive_supplies: int
    squad: list[CampaignSoldier]
    research: list[ResearchProject]
    active_research_idx: int
    mission_cards: list[MissionCard] = field(default_factory=list)


@dataclass
class ShotPreview:
    chance: int
    crit: int
    cover_bonus: int
    cover_cell: Optional[Cell]
    flanked: bool
    blocked_by_phase: bool


class Button:
    def __init__(self, rect: pygame.Rect, text: str):
        self.rect = rect
        self.text = text

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, hovered: bool) -> None:
        bg = (42, 62, 98) if hovered else (24, 37, 66)
        outline = (136, 192, 255) if hovered else (92, 134, 186)
        pygame.draw.rect(surface, bg, self.rect, border_radius=12)
        pygame.draw.rect(surface, outline, self.rect, width=2, border_radius=12)
        label = font.render(self.text, True, (236, 246, 255))
        surface.blit(label, label.get_rect(center=self.rect.center))

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def cell_inside(cell: Cell) -> bool:
    return 0 <= cell[0] < GRID_COLS and 0 <= cell[1] < GRID_ROWS


def neighbors4(cell: Cell) -> list[Cell]:
    x, y = cell
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def cell_rect(cell: Cell) -> pygame.Rect:
    return pygame.Rect(
        MAP_X + cell[0] * TILE_SIZE,
        MAP_Y + cell[1] * TILE_SIZE,
        TILE_SIZE,
        TILE_SIZE,
    )


def cell_center(cell: Cell) -> tuple[int, int]:
    rect = cell_rect(cell)
    return rect.centerx, rect.centery


def screen_to_cell(pos: tuple[int, int]) -> Optional[Cell]:
    sx, sy = pos
    if sx < MAP_X or sy < MAP_Y or sx >= MAP_X + MAP_WIDTH or sy >= MAP_Y + MAP_HEIGHT:
        return None
    return (sx - MAP_X) // TILE_SIZE, (sy - MAP_Y) // TILE_SIZE


def bresenham_line(start: Cell, end: Cell) -> list[Cell]:
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


def has_los(start: Cell, end: Cell, walls: set[Cell], covers: dict[Cell, CoverObject]) -> bool:
    if start == end:
        return True
    line = bresenham_line(start, end)
    for cell in line[1:-1]:
        if cell in walls or cell in covers:
            return False
    return True


def add_log(state: BattleState, message: str) -> None:
    state.log.append(message)
    if len(state.log) > 12:
        state.log = state.log[-12:]


def role_color(role: str) -> tuple[int, int, int]:
    if role == "Chrono Shield":
        return (50, 171, 245)
    if role == "Paradox Tactician":
        return (139, 203, 88)
    if role == "Anomaly Engineer":
        return (243, 186, 72)
    return (188, 202, 220)


def enemy_color(enemy_type: str) -> tuple[int, int, int]:
    if enemy_type == "reverser":
        return (223, 93, 194)
    if enemy_type == "phantom":
        return (130, 170, 255)
    if enemy_type == "brute":
        return (219, 111, 71)
    return (218, 77, 77)


def get_unit_by_id(units: list[BattleUnit], unit_id: Optional[str]) -> Optional[BattleUnit]:
    if unit_id is None:
        return None
    for unit in units:
        if unit.unit_id == unit_id and unit.alive:
            return unit
    return None


def unit_at_cell(units: list[BattleUnit], cell: Cell) -> Optional[BattleUnit]:
    for unit in units:
        if unit.alive and unit.cell == cell:
            return unit
    return None


def active_research(campaign: CampaignState) -> Optional[ResearchProject]:
    if not campaign.research:
        return None
    idx = clamp(campaign.active_research_idx, 0, len(campaign.research) - 1)
    campaign.active_research_idx = idx
    project = campaign.research[idx]
    if project.completed:
        for i, candidate in enumerate(campaign.research):
            if not candidate.completed:
                campaign.active_research_idx = i
                return candidate
        return None
    return project


def cycle_active_research(campaign: CampaignState) -> None:
    if not campaign.research:
        return
    start = campaign.active_research_idx
    for offset in range(1, len(campaign.research) + 1):
        idx = (start + offset) % len(campaign.research)
        if not campaign.research[idx].completed:
            campaign.active_research_idx = idx
            return


def create_initial_campaign(rng: random.Random) -> CampaignState:
    squad = [
        CampaignSoldier("s1", "Iris", "Chrono Shield", max_hp=11, hp=11, aim=64, defense=12),
        CampaignSoldier("s2", "Vex", "Paradox Tactician", max_hp=9, hp=9, aim=73, defense=4),
        CampaignSoldier("s3", "Nova", "Anomaly Engineer", max_hp=9, hp=9, aim=69, defense=6),
    ]
    research = [
        ResearchProject("ballistics_ai", "Ballistics AI", "+5 aim for all soldiers.", cost=90),
        ResearchProject("reinforced_plating", "Reinforced Plating", "+2 max HP for all soldiers.", cost=110),
        ResearchProject("relay_optimization", "Relay Optimization", "+15 passive supplies after missions.", cost=80),
    ]
    campaign = CampaignState(
        supplies=120,
        science=0,
        intel=20,
        mission_index=0,
        threat=1,
        lab_level=1,
        armory_level=1,
        relay_level=1,
        passive_supplies=0,
        squad=squad,
        research=research,
        active_research_idx=0,
    )
    campaign.mission_cards = generate_mission_cards(campaign, rng)
    return campaign


def generate_mission_cards(campaign: CampaignState, rng: random.Random) -> list[MissionCard]:
    names = [
        "Rift Station",
        "Cold Transit",
        "Shattered Relay",
        "Neon Breach",
        "Temporal Yard",
        "Ghost District",
        "Broken Signal",
    ]
    cards: list[MissionCard] = []
    for i in range(3):
        threat = clamp(campaign.threat + rng.randint(-1, 1), 1, 7)
        enemy_count = 4 + threat * 2 + rng.randint(0, 1)
        pod_count = clamp(2 + threat // 2, 2, 4)
        reward_supplies = 35 + threat * 14 + rng.randint(0, 16)
        reward_science = 20 + threat * 10 + rng.randint(0, 12)
        reward_intel = 8 + threat * 4 + rng.randint(0, 6)
        cards.append(
            MissionCard(
                mission_id=campaign.mission_index * 10 + i + 1,
                title=names[(campaign.mission_index + i) % len(names)],
                threat=threat,
                enemy_count=enemy_count,
                pod_count=pod_count,
                reward_supplies=reward_supplies,
                reward_science=reward_science,
                reward_intel=reward_intel,
            )
        )
    return cards


def generate_battlefield(seed: int) -> tuple[set[Cell], dict[Cell, CoverObject], list[Cell], list[Cell]]:
    rng = random.Random(seed)
    walls: set[Cell] = set()
    covers: dict[Cell, CoverObject] = {}

    for x in range(GRID_COLS):
        walls.add((x, 0))
        walls.add((x, GRID_ROWS - 1))
    for y in range(GRID_ROWS):
        walls.add((0, y))
        walls.add((GRID_COLS - 1, y))

    for _ in range(8):
        rw = rng.randint(1, 3)
        rh = rng.randint(1, 3)
        rx = rng.randint(5, GRID_COLS - rw - 6)
        ry = rng.randint(2, GRID_ROWS - rh - 3)
        for y in range(ry, ry + rh):
            for x in range(rx, rx + rw):
                walls.add((x, y))

    forbidden = set(walls)
    for _ in range(56):
        cell = (rng.randint(2, GRID_COLS - 3), rng.randint(1, GRID_ROWS - 2))
        if cell in forbidden:
            continue
        if cell[0] <= 4 or cell[0] >= GRID_COLS - 5:
            continue
        kind = "full" if rng.random() < 0.32 else "half"
        hp = 4 if kind == "full" else 2
        covers[cell] = CoverObject(kind=kind, hp=hp)
        forbidden.add(cell)

    player_spawns = [(2, 4), (2, 6), (2, 8), (3, 5), (3, 7), (3, 9)]
    enemy_spawns = [(GRID_COLS - 3, y) for y in range(2, GRID_ROWS - 2)] + [
        (GRID_COLS - 4, y) for y in range(2, GRID_ROWS - 2)
    ]
    player_spawns = [cell for cell in player_spawns if cell not in walls and cell not in covers]
    enemy_spawns = [cell for cell in enemy_spawns if cell not in walls and cell not in covers]
    return walls, covers, player_spawns, enemy_spawns


def build_battle_state(campaign: CampaignState, mission: MissionCard, rng: random.Random) -> Optional[BattleState]:
    alive_soldiers = [soldier for soldier in campaign.squad if soldier.alive]
    if not alive_soldiers:
        return None

    walls, covers, player_spawns, enemy_spawns = generate_battlefield(mission.mission_id)
    if len(player_spawns) < len(alive_soldiers):
        return None

    player_units: list[BattleUnit] = []
    for idx, soldier in enumerate(alive_soldiers):
        player_units.append(
            BattleUnit(
                unit_id=f"p_{soldier.sid}",
                sid=soldier.sid,
                name=soldier.name,
                team="player",
                role=soldier.role,
                cell=player_spawns[idx],
                hp=soldier.hp,
                max_hp=soldier.max_hp,
                aim=soldier.aim,
                defense=soldier.defense,
            )
        )

    enemy_templates = [
        ("trooper", 7, 63, 4),
        ("reverser", 8, 60, 8),
        ("phantom", 6, 69, 2),
        ("brute", 10, 57, 10),
    ]
    enemy_units: list[BattleUnit] = []
    used_spawn_cells: set[Cell] = set(unit.cell for unit in player_units)
    spawn_pool = [cell for cell in enemy_spawns if cell not in used_spawn_cells]
    rng.shuffle(spawn_pool)

    pods = [idx % mission.pod_count for idx in range(mission.enemy_count)]
    rng.shuffle(pods)
    for idx in range(min(mission.enemy_count, len(spawn_pool))):
        enemy_type, hp, aim, defense = enemy_templates[idx % len(enemy_templates)]
        enemy_units.append(
            BattleUnit(
                unit_id=f"e_{mission.mission_id}_{idx}",
                sid=None,
                name=enemy_type.title(),
                team="enemy",
                role="Alien",
                cell=spawn_pool[idx],
                hp=hp + mission.threat // 2,
                max_hp=hp + mission.threat // 2,
                aim=aim + mission.threat,
                defense=defense,
                pod_id=pods[idx],
                active=False,
                enemy_type=enemy_type,
                phase_visible=True,
            )
        )

    state = BattleState(
        mission=mission,
        walls=walls,
        covers=covers,
        player_units=player_units,
        enemy_units=enemy_units,
        selected_player_id=player_units[0].unit_id if player_units else None,
        pending_rewards={
            "supplies": mission.reward_supplies,
            "science": mission.reward_science,
            "intel": mission.reward_intel,
        },
    )
    update_enemy_phase_flags(state)
    refresh_visibility_and_pods(state)
    add_log(state, f"Mission started: {mission.title}")
    add_log(state, "Player turn 1")
    return state


def update_enemy_phase_flags(state: BattleState) -> None:
    for enemy in state.enemy_units:
        if enemy.enemy_type == "phantom":
            enemy.phase_visible = state.turn_number % 2 == 1
        else:
            enemy.phase_visible = True


def refresh_visibility_and_pods(state: BattleState) -> None:
    visible: set[Cell] = set()
    for unit in state.player_units:
        if not unit.alive:
            continue
        for y in range(max(0, unit.cell[1] - PLAYER_VISION), min(GRID_ROWS, unit.cell[1] + PLAYER_VISION + 1)):
            for x in range(max(0, unit.cell[0] - PLAYER_VISION), min(GRID_COLS, unit.cell[0] + PLAYER_VISION + 1)):
                cell = (x, y)
                if manhattan(unit.cell, cell) > PLAYER_VISION:
                    continue
                if has_los(unit.cell, cell, state.walls, state.covers):
                    visible.add(cell)
    state.visible_cells = visible
    state.explored_cells |= visible

    newly_activated: set[int] = set()
    seen_pods = {enemy.pod_id for enemy in state.enemy_units if enemy.alive and enemy.cell in state.visible_cells}
    for enemy in state.enemy_units:
        if enemy.alive and enemy.pod_id in seen_pods and not enemy.active:
            enemy.active = True
            newly_activated.add(enemy.pod_id)
    for pod in sorted(newly_activated):
        add_log(state, f"Enemy pod {pod + 1} activated")


def blocked_cells(state: BattleState, ignore_unit: Optional[str] = None) -> set[Cell]:
    blocked = set(state.walls) | set(state.covers.keys())
    for unit in state.player_units + state.enemy_units:
        if not unit.alive:
            continue
        if ignore_unit is not None and unit.unit_id == ignore_unit:
            continue
        blocked.add(unit.cell)
    return blocked


def bfs_path(start: Cell, goal: Cell, blocked: set[Cell]) -> list[Cell]:
    if start == goal:
        return [start]
    queue: deque[Cell] = deque([start])
    prev: dict[Cell, Optional[Cell]] = {start: None}

    while queue:
        cur = queue.popleft()
        for nxt in neighbors4(cur):
            if not cell_inside(nxt) or nxt in blocked or nxt in prev:
                continue
            prev[nxt] = cur
            if nxt == goal:
                queue.clear()
                break
            queue.append(nxt)

    if goal not in prev:
        return []

    path: list[Cell] = []
    cursor: Optional[Cell] = goal
    while cursor is not None:
        path.append(cursor)
        cursor = prev[cursor]
    path.reverse()
    return path


def movement_ap_cost(step_count: int) -> int:
    if step_count <= 0:
        return 0
    if step_count <= MAX_MOVE_STEPS_1_AP:
        return 1
    if step_count <= MAX_MOVE_STEPS_2_AP:
        return 2
    return 999


def try_move_player(state: BattleState, unit: BattleUnit, target: Cell) -> bool:
    if state.turn_side != "player" or state.mission_result is not None:
        return False
    if not unit.alive or unit.ap <= 0 or target == unit.cell or not cell_inside(target):
        return False

    blocked = blocked_cells(state, ignore_unit=unit.unit_id)
    if target in blocked:
        return False
    path = bfs_path(unit.cell, target, blocked)
    if not path:
        return False
    steps = len(path) - 1
    cost = movement_ap_cost(steps)
    if cost > unit.ap:
        return False

    unit.cell = target
    unit.ap -= cost
    unit.overwatch = False
    unit.fortify = False
    add_log(state, f"{unit.name} moved {steps} tiles (-{cost} AP)")
    refresh_visibility_and_pods(state)
    return True


def cover_strength_for_cell(cell: Cell, state: BattleState) -> int:
    if cell in state.walls:
        return 40
    cover = state.covers.get(cell)
    if cover is None:
        return 0
    return 40 if cover.kind == "full" else 20


def compute_cover(attacker_cell: Cell, target_cell: Cell, state: BattleState) -> tuple[int, Optional[Cell], bool]:
    dx = attacker_cell[0] - target_cell[0]
    dy = attacker_cell[1] - target_cell[1]
    directions: list[Cell] = []
    if dx != 0:
        directions.append((sign(dx), 0))
    if dy != 0:
        directions.append((0, sign(dy)))
    if not directions:
        directions.append((0, 0))

    best_bonus = 0
    best_cell: Optional[Cell] = None
    for step in directions:
        cover_cell = (target_cell[0] + step[0], target_cell[1] + step[1])
        bonus = cover_strength_for_cell(cover_cell, state)
        if bonus > best_bonus:
            best_bonus = bonus
            best_cell = cover_cell

    has_any_adjacent_cover = any(cover_strength_for_cell(cell, state) > 0 for cell in neighbors4(target_cell))
    flanked = has_any_adjacent_cover and best_bonus == 0
    return best_bonus, best_cell, flanked


def shot_preview(state: BattleState, attacker: BattleUnit, target: BattleUnit, reaction: bool) -> ShotPreview:
    if target.enemy_type == "phantom" and not target.phase_visible:
        return ShotPreview(0, 0, 0, None, False, True)

    base = attacker.aim
    if attacker.sync_shot:
        base += 15
    if attacker.suppressed:
        base -= 20
    if reaction:
        base -= 15
    base -= max(0, manhattan(attacker.cell, target.cell) - 6) * 6

    cover_bonus, cover_cell, flanked = compute_cover(attacker.cell, target.cell, state)
    target_defense = target.defense + (20 if target.fortify else 0)
    if target.suppressed:
        target_defense = max(0, target_defense - 10)
    if flanked:
        base += 20
        effective_cover = 0
    else:
        effective_cover = cover_bonus
        base -= effective_cover
    base -= target_defense

    chance = clamp(int(base), 5, 95)
    crit = clamp(10 + (20 if flanked else 0), 0, 70)
    return ShotPreview(chance, crit, effective_cover, cover_cell, flanked, False)


def damage_cover(state: BattleState, cell: Optional[Cell], amount: int = 1) -> None:
    if cell is None:
        return
    cover = state.covers.get(cell)
    if cover is None:
        return
    cover.hp -= amount
    if cover.hp <= 0:
        del state.covers[cell]
        add_log(state, f"Cover at {cell[0]},{cell[1]} destroyed")


def resolve_shot(
    state: BattleState,
    attacker: BattleUnit,
    target: BattleUnit,
    rng: random.Random,
    reaction: bool = False,
) -> bool:
    if not attacker.alive or not target.alive:
        return False
    if not has_los(attacker.cell, target.cell, state.walls, state.covers):
        add_log(state, f"{attacker.name} has no line of sight")
        attacker.sync_shot = False
        return False

    preview = shot_preview(state, attacker, target, reaction)
    if preview.blocked_by_phase:
        add_log(state, f"{target.name} phased out")
        attacker.sync_shot = False
        return False

    roll = rng.randint(1, 100)
    hit = roll <= preview.chance
    if hit:
        dmg = rng.randint(2, 4)
        crit = rng.randint(1, 100) <= preview.crit
        if crit:
            dmg += 2
        if target.enemy_type == "reverser" and not target.rewind_used and target.hp - dmg <= 0:
            target.hp = 1
            target.rewind_used = True
            add_log(state, f"{target.name} rewound fatal damage")
        else:
            target.hp -= dmg
            suffix = " CRIT" if crit else ""
            add_log(state, f"{attacker.name} hit {target.name} for {dmg}{suffix}")
        if target.hp <= 0:
            target.alive = False
            attacker.kills += 1
            add_log(state, f"{target.name} eliminated")
            if target.unit_id == state.selected_enemy_id:
                state.selected_enemy_id = None
    else:
        add_log(state, f"{attacker.name} missed {target.name} ({preview.chance}%)")
        if preview.cover_cell is not None and rng.random() < 0.65:
            damage_cover(state, preview.cover_cell, amount=1)

    attacker.sync_shot = False
    return hit


def shoot_cover(state: BattleState, attacker: BattleUnit, cover_cell: Cell, rng: random.Random) -> bool:
    if cover_cell not in state.covers or attacker.ap < 1:
        return False
    if not has_los(attacker.cell, cover_cell, state.walls, state.covers):
        return False
    attacker.ap -= 1
    chance = clamp(attacker.aim - max(0, manhattan(attacker.cell, cover_cell) - 5) * 8, 20, 95)
    if rng.randint(1, 100) <= chance:
        dmg = 2 if rng.random() < 0.25 else 1
        damage_cover(state, cover_cell, amount=dmg)
        add_log(state, f"{attacker.name} damaged cover ({dmg})")
    else:
        add_log(state, f"{attacker.name} missed cover shot")
    return True


def apply_class_ability(state: BattleState, unit: BattleUnit) -> bool:
    if unit.ap <= 0:
        return False
    if unit.role == "Chrono Shield":
        unit.ap -= 1
        unit.fortify = True
        add_log(state, f"{unit.name} used Fortify (+20 defense)")
        return True
    if unit.role == "Paradox Tactician":
        unit.ap -= 1
        unit.sync_shot = True
        add_log(state, f"{unit.name} prepared Sync Shot (+15 aim)")
        return True
    if unit.role == "Anomaly Engineer":
        unit.ap -= 1
        for ally in state.player_units:
            ally.suppressed = False
            ally.suppression_from = None
        add_log(state, f"{unit.name} stabilized squad")
        return True
    return False


def set_overwatch(state: BattleState, unit: BattleUnit) -> bool:
    if unit.ap < 1:
        return False
    unit.ap -= 1
    unit.overwatch = True
    add_log(state, f"{unit.name} on overwatch")
    return True


def apply_suppression(state: BattleState, unit: BattleUnit, target: BattleUnit) -> bool:
    if unit.ap < 2 or not target.alive:
        return False
    if not has_los(unit.cell, target.cell, state.walls, state.covers):
        return False
    unit.ap -= 2
    target.suppressed = True
    target.suppression_from = unit.unit_id
    add_log(state, f"{unit.name} suppressed {target.name}")
    return True


def trigger_overwatch_on_enemy_move(state: BattleState, enemy: BattleUnit, rng: random.Random) -> None:
    watchers = [unit for unit in state.player_units if unit.alive and unit.overwatch]
    for watcher in watchers:
        if not enemy.alive:
            break
        if manhattan(watcher.cell, enemy.cell) > 9:
            continue
        if not has_los(watcher.cell, enemy.cell, state.walls, state.covers):
            continue
        add_log(state, f"Overwatch: {watcher.name} fires at {enemy.name}")
        resolve_shot(state, watcher, enemy, rng, reaction=True)
        watcher.overwatch = False


def best_enemy_target(state: BattleState, enemy: BattleUnit) -> Optional[BattleUnit]:
    candidates: list[BattleUnit] = []
    for unit in state.player_units:
        if not unit.alive:
            continue
        if manhattan(enemy.cell, unit.cell) > 10:
            continue
        if not has_los(enemy.cell, unit.cell, state.walls, state.covers):
            continue
        candidates.append(unit)
    if not candidates:
        return None
    return min(candidates, key=lambda unit: (unit.hp, manhattan(enemy.cell, unit.cell)))


def choose_enemy_step(state: BattleState, enemy: BattleUnit, target: BattleUnit) -> Cell:
    blocked = blocked_cells(state, ignore_unit=enemy.unit_id)
    blocked.discard(target.cell)
    path = bfs_path(enemy.cell, target.cell, blocked)
    if len(path) >= 2:
        return path[1]

    candidates: list[Cell] = []
    for nxt in neighbors4(enemy.cell):
        if not cell_inside(nxt) or nxt in blocked:
            continue
        candidates.append(nxt)
    if not candidates:
        return enemy.cell
    return min(candidates, key=lambda cell: manhattan(cell, target.cell))


def check_mission_end(state: BattleState) -> None:
    if state.mission_result is not None:
        return
    alive_players = [unit for unit in state.player_units if unit.alive]
    alive_enemies = [unit for unit in state.enemy_units if unit.alive]
    if not alive_enemies:
        state.mission_result = "victory"
        add_log(state, "Mission complete")
    elif not alive_players:
        state.mission_result = "defeat"
        add_log(state, "Squad wiped")


def begin_new_player_turn(state: BattleState, advance_round: bool) -> None:
    if advance_round:
        state.turn_number += 1
    state.turn_side = "player"
    update_enemy_phase_flags(state)
    for unit in state.player_units:
        if not unit.alive:
            continue
        unit.ap = 2
        unit.overwatch = False
        unit.fortify = False
        unit.sync_shot = False
    state.selected_player_id = next((u.unit_id for u in state.player_units if u.alive), None)
    refresh_visibility_and_pods(state)
    add_log(state, f"Player turn {state.turn_number}")


def enemy_turn(state: BattleState, rng: random.Random) -> None:
    state.turn_side = "enemy"
    update_enemy_phase_flags(state)
    add_log(state, "Enemy turn")

    for enemy in state.enemy_units:
        if not enemy.alive or not enemy.active:
            continue
        enemy.ap = 2
        while enemy.ap > 0 and enemy.alive:
            target = best_enemy_target(state, enemy)
            if target is not None:
                enemy.ap -= 1
                resolve_shot(state, enemy, target, rng, reaction=False)
                check_mission_end(state)
                if state.mission_result is not None:
                    return
                continue

            closest = min(
                [unit for unit in state.player_units if unit.alive],
                key=lambda unit: manhattan(enemy.cell, unit.cell),
                default=None,
            )
            if closest is None:
                break

            move_cost = 2 if enemy.suppressed else 1
            if enemy.ap < move_cost:
                break

            step = choose_enemy_step(state, enemy, closest)
            if step == enemy.cell:
                break
            enemy.ap -= move_cost
            enemy.cell = step
            add_log(state, f"{enemy.name} moved")
            trigger_overwatch_on_enemy_move(state, enemy, rng)
            check_mission_end(state)
            if state.mission_result is not None:
                return

    for enemy in state.enemy_units:
        enemy.suppressed = False
        enemy.suppression_from = None

    begin_new_player_turn(state, advance_round=True)


def next_player_unit_with_ap(state: BattleState) -> Optional[str]:
    alive = [unit for unit in state.player_units if unit.alive]
    if not alive:
        return None
    current = state.selected_player_id
    if current is None:
        candidate = next((unit.unit_id for unit in alive if unit.ap > 0), None)
        return candidate or alive[0].unit_id
    order = [unit.unit_id for unit in alive]
    if current not in order:
        candidate = next((unit.unit_id for unit in alive if unit.ap > 0), None)
        return candidate or alive[0].unit_id
    start = order.index(current)
    for shift in range(1, len(order) + 1):
        idx = (start + shift) % len(order)
        unit = get_unit_by_id(state.player_units, order[idx])
        if unit is not None and unit.ap > 0:
            return unit.unit_id
    return current


def apply_research_bonus(campaign: CampaignState, key: str) -> None:
    if key == "ballistics_ai":
        for soldier in campaign.squad:
            soldier.aim += 5
    elif key == "reinforced_plating":
        for soldier in campaign.squad:
            soldier.max_hp += 2
            soldier.hp = min(soldier.max_hp, soldier.hp + 2)
    elif key == "relay_optimization":
        campaign.passive_supplies += 15


def apply_battle_result(campaign: CampaignState, battle: BattleState, rng: random.Random) -> None:
    by_sid = {soldier.sid: soldier for soldier in campaign.squad}
    for unit in battle.player_units:
        if unit.sid is None or unit.sid not in by_sid:
            continue
        soldier = by_sid[unit.sid]
        if not unit.alive:
            soldier.alive = False
            soldier.hp = 0
            continue
        soldier.hp = clamp(unit.hp, 1, soldier.max_hp)
        xp_gain = unit.kills * 5 + (6 if battle.mission_result == "victory" else 2)
        soldier.xp += xp_gain
        while soldier.xp >= soldier.level * 12:
            soldier.xp -= soldier.level * 12
            soldier.level += 1
            soldier.max_hp += 1 + (1 if soldier.role == "Chrono Shield" else 0)
            soldier.aim += 2
            if soldier.role == "Chrono Shield":
                soldier.defense += 1
            soldier.hp = min(soldier.max_hp, soldier.hp + 2)

    if battle.mission_result == "victory":
        campaign.supplies += battle.pending_rewards["supplies"] + campaign.passive_supplies
        campaign.science += battle.pending_rewards["science"] + campaign.lab_level * 6
        campaign.intel += battle.pending_rewards["intel"] + campaign.relay_level
        campaign.threat = clamp(campaign.threat + 1, 1, 7)
    else:
        campaign.supplies += battle.pending_rewards["supplies"] // 3
        campaign.science += battle.pending_rewards["science"] // 3
        campaign.intel += battle.pending_rewards["intel"] // 2
        campaign.threat = max(1, campaign.threat - 1)

    project = active_research(campaign)
    if project is not None and not project.completed:
        progress_gain = (20 + campaign.lab_level * 5) if battle.mission_result == "victory" else (8 + campaign.lab_level * 2)
        project.progress += progress_gain
        if project.progress >= project.cost:
            project.completed = True
            apply_research_bonus(campaign, project.key)

    for soldier in campaign.squad:
        if soldier.alive and soldier.hp < soldier.max_hp:
            soldier.hp = min(soldier.max_hp, soldier.hp + campaign.armory_level)

    campaign.mission_index += 1
    campaign.mission_cards = generate_mission_cards(campaign, rng)


def attempt_room_upgrade(campaign: CampaignState, room_key: str) -> str:
    if room_key == "lab":
        cost = 90 + campaign.lab_level * 40
        if campaign.supplies < cost:
            return f"Need {cost} supplies for Lab upgrade"
        campaign.supplies -= cost
        campaign.lab_level += 1
        return f"Lab upgraded to {campaign.lab_level}"
    if room_key == "armory":
        cost = 80 + campaign.armory_level * 35
        if campaign.supplies < cost:
            return f"Need {cost} supplies for Armory upgrade"
        campaign.supplies -= cost
        campaign.armory_level += 1
        for soldier in campaign.squad:
            if soldier.alive:
                soldier.hp = min(soldier.max_hp, soldier.hp + 2)
        return f"Armory upgraded to {campaign.armory_level}"
    if room_key == "relay":
        cost = 70 + campaign.relay_level * 30
        if campaign.supplies < cost:
            return f"Need {cost} supplies for Relay upgrade"
        campaign.supplies -= cost
        campaign.relay_level += 1
        return f"Relay upgraded to {campaign.relay_level}"
    return "Unknown room"


def make_grass_texture(size: int) -> pygame.Surface:
    rng = random.Random(1337)
    surf = pygame.Surface((size, size))
    surf.fill((42, 98, 60))
    for _ in range(260):
        x = rng.randrange(size)
        y = rng.randrange(size)
        shade = rng.randrange(-16, 16)
        color = (45 + shade, 106 + shade, 63 + shade)
        surf.set_at((x, y), color)
    return surf


def make_wall_texture(size: int) -> pygame.Surface:
    surf = pygame.Surface((size, size))
    surf.fill((83, 87, 97))
    for row in range(0, size, max(8, size // 5)):
        pygame.draw.line(surf, (68, 72, 80), (0, row), (size, row), 1)
    for col in range(0, size, max(10, size // 4)):
        pygame.draw.line(surf, (98, 102, 112), (col, 0), (col, size), 1)
    return surf


def make_cover_texture(size: int, kind: str) -> pygame.Surface:
    surf = pygame.Surface((size, size))
    if kind == "full":
        base = (128, 112, 84)
        edge = (88, 72, 52)
    else:
        base = (114, 141, 92)
        edge = (74, 98, 58)
    surf.fill(base)
    pygame.draw.rect(surf, edge, (0, 0, size, size), width=3)
    pygame.draw.rect(surf, (150, 160, 142), (6, 6, size - 12, size - 12), width=1)
    return surf


def draw_menu(
    screen: pygame.Surface,
    title_font: pygame.font.Font,
    menu_font: pygame.font.Font,
    body_font: pygame.font.Font,
    start_button: Button,
    quit_button: Button,
    mouse_pos: tuple[int, int],
) -> None:
    for y in range(SCREEN_HEIGHT):
        t = y / SCREEN_HEIGHT
        color = (int(7 + 18 * t), int(14 + 32 * t), int(29 + 64 * t))
        pygame.draw.line(screen, color, (0, y), (SCREEN_WIDTH, y))

    title = title_font.render("ECHO PROTOCOL", True, (236, 246, 255))
    subtitle = body_font.render("Alpha: XCOM-style tactical loop", True, (190, 214, 236))
    screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 170)))
    screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 225)))

    start_button.draw(screen, menu_font, start_button.contains(mouse_pos))
    quit_button.draw(screen, menu_font, quit_button.contains(mouse_pos))

    controls = [
        "Battle controls: LMB select/shoot, RMB move, O overwatch, P suppress, F class skill",
        "End turn: E or SPACE | Tab: next soldier | Shift+LMB on cover: destroy cover",
    ]
    for idx, line in enumerate(controls):
        text = body_font.render(line, True, (199, 220, 241))
        screen.blit(text, (28, SCREEN_HEIGHT - 70 + idx * 24))


def draw_geoscape(
    screen: pygame.Surface,
    campaign: CampaignState,
    title_font: pygame.font.Font,
    ui_font: pygame.font.Font,
    small_font: pygame.font.Font,
    status_line: str,
) -> None:
    screen.fill((12, 18, 30))
    pygame.draw.rect(screen, (20, 30, 46), (0, 0, SCREEN_WIDTH, 92))
    pygame.draw.line(screen, (58, 87, 122), (0, 92), (SCREEN_WIDTH, 92), 2)

    title = title_font.render("Geoscape / Base", True, (230, 242, 255))
    screen.blit(title, (24, 20))
    resources = ui_font.render(
        f"Supplies: {campaign.supplies}   Science: {campaign.science}   Intel: {campaign.intel}",
        True,
        (198, 221, 243),
    )
    screen.blit(resources, (410, 30))

    left_panel = pygame.Rect(24, 120, 420, 560)
    right_panel = pygame.Rect(460, 120, 796, 560)
    pygame.draw.rect(screen, (18, 27, 41), left_panel, border_radius=10)
    pygame.draw.rect(screen, (18, 27, 41), right_panel, border_radius=10)
    pygame.draw.rect(screen, (58, 87, 122), left_panel, width=2, border_radius=10)
    pygame.draw.rect(screen, (58, 87, 122), right_panel, width=2, border_radius=10)

    screen.blit(ui_font.render("Base Rooms", True, (232, 241, 255)), (40, 138))
    rooms = [
        f"[L] Lab Level {campaign.lab_level}",
        f"[A] Armory Level {campaign.armory_level}",
        f"[Y] Relay Level {campaign.relay_level}",
    ]
    for idx, line in enumerate(rooms):
        screen.blit(small_font.render(line, True, (200, 223, 245)), (40, 172 + idx * 24))

    screen.blit(ui_font.render("Research", True, (232, 241, 255)), (40, 264))
    project = active_research(campaign)
    if project is None:
        screen.blit(small_font.render("All projects completed", True, (149, 215, 170)), (40, 298))
    else:
        pct = int((project.progress / project.cost) * 100)
        screen.blit(small_font.render(f"Active: {project.name} ({pct}%)", True, (205, 227, 246)), (40, 298))
        screen.blit(small_font.render(project.description, True, (173, 201, 226)), (40, 324))
        bar_rect = pygame.Rect(40, 352, 360, 20)
        pygame.draw.rect(screen, (42, 58, 82), bar_rect, border_radius=8)
        fill = pygame.Rect(bar_rect.x, bar_rect.y, int(bar_rect.width * min(1.0, project.progress / project.cost)), bar_rect.height)
        pygame.draw.rect(screen, (101, 174, 238), fill, border_radius=8)
        pygame.draw.rect(screen, (94, 133, 175), bar_rect, width=2, border_radius=8)
        screen.blit(small_font.render("[R] Switch active research", True, (193, 216, 237)), (40, 382))

    screen.blit(ui_font.render("Squad", True, (232, 241, 255)), (40, 432))
    for idx, soldier in enumerate(campaign.squad):
        color = (199, 225, 247) if soldier.alive else (160, 117, 117)
        line = (
            f"{soldier.name} | {soldier.role} | L{soldier.level} | "
            f"HP {soldier.hp}/{soldier.max_hp} | AIM {soldier.aim}"
        )
        if not soldier.alive:
            line += " | KIA"
        screen.blit(small_font.render(line, True, color), (40, 466 + idx * 26))

    screen.blit(ui_font.render("Available Missions", True, (232, 241, 255)), (478, 138))
    for idx, mission in enumerate(campaign.mission_cards):
        rect = pygame.Rect(478, 172 + idx * 170, 760, 150)
        pygame.draw.rect(screen, (23, 35, 53), rect, border_radius=10)
        pygame.draw.rect(screen, (73, 108, 148), rect, width=2, border_radius=10)
        screen.blit(ui_font.render(f"[{idx + 1}] {mission.title}", True, (228, 241, 255)), (496, rect.y + 14))
        row1 = f"Threat: {mission.threat}   Enemies: {mission.enemy_count}   Pods: {mission.pod_count}"
        row2 = (
            f"Reward -> Supplies {mission.reward_supplies}, "
            f"Science {mission.reward_science}, Intel {mission.reward_intel}"
        )
        screen.blit(small_font.render(row1, True, (198, 220, 242)), (496, rect.y + 56))
        screen.blit(small_font.render(row2, True, (198, 220, 242)), (496, rect.y + 82))
        screen.blit(small_font.render("Press number key to launch mission", True, (160, 194, 223)), (496, rect.y + 112))

    footer = small_font.render(
        "XCOM loop alpha: mission -> rewards -> base upgrades/research -> next mission",
        True,
        (171, 201, 229),
    )
    screen.blit(footer, (24, SCREEN_HEIGHT - 28))
    if status_line:
        screen.blit(small_font.render(status_line, True, (227, 226, 174)), (460, SCREEN_HEIGHT - 28))


def draw_unit_icon(screen: pygame.Surface, unit: BattleUnit, selected: bool, font: pygame.font.Font) -> None:
    cx, cy = cell_center(unit.cell)
    radius = TILE_SIZE // 2 - 6
    if unit.team == "player":
        fill = role_color(unit.role)
        edge = (18, 42, 70)
    else:
        fill = enemy_color(unit.enemy_type)
        edge = (74, 20, 20)
    if unit.team == "enemy" and unit.enemy_type == "phantom" and not unit.phase_visible:
        fill = (88, 101, 131)

    pygame.draw.circle(screen, fill, (cx, cy), radius)
    pygame.draw.circle(screen, edge, (cx, cy), radius, 3)
    if selected:
        pygame.draw.circle(screen, (240, 244, 255), (cx, cy), radius + 4, 2)

    hp_ratio = max(0.0, unit.hp / unit.max_hp if unit.max_hp > 0 else 0)
    bar_w = TILE_SIZE - 10
    bar_h = 6
    bar_x = cx - bar_w // 2
    bar_y = cy + radius + 2
    pygame.draw.rect(screen, (42, 42, 48), (bar_x, bar_y, bar_w, bar_h))
    pygame.draw.rect(screen, (92, 224, 129), (bar_x, bar_y, int(bar_w * hp_ratio), bar_h))

    flags: list[str] = []
    if unit.overwatch:
        flags.append("O")
    if unit.suppressed:
        flags.append("S")
    if unit.fortify:
        flags.append("F")
    if unit.sync_shot:
        flags.append("X")
    if flags:
        txt = font.render("".join(flags), True, (247, 242, 188))
        screen.blit(txt, (cx - txt.get_width() // 2, cy - radius - 16))


def draw_battle(
    screen: pygame.Surface,
    state: BattleState,
    grass_tile: pygame.Surface,
    wall_tile: pygame.Surface,
    half_cover_tile: pygame.Surface,
    full_cover_tile: pygame.Surface,
    ui_font: pygame.font.Font,
    small_font: pygame.font.Font,
    mouse_pos: tuple[int, int],
) -> None:
    screen.fill((11, 18, 30))

    for y in range(GRID_ROWS):
        for x in range(GRID_COLS):
            rect = cell_rect((x, y))
            screen.blit(grass_tile, rect.topleft)
            pygame.draw.rect(screen, (70, 92, 112), rect, width=1)

    for wall in state.walls:
        rect = cell_rect(wall)
        screen.blit(wall_tile, rect.topleft)
        pygame.draw.rect(screen, (46, 48, 52), rect, width=2)

    for cell, cover in state.covers.items():
        rect = cell_rect(cell)
        tile = full_cover_tile if cover.kind == "full" else half_cover_tile
        screen.blit(tile, rect.topleft)
        pygame.draw.rect(screen, (46, 50, 55), rect, width=2)

    selected_player = get_unit_by_id(state.player_units, state.selected_player_id)
    selected_enemy = get_unit_by_id(state.enemy_units, state.selected_enemy_id)
    flag_font = pygame.font.SysFont("consolas", 14, bold=True)

    for enemy in state.enemy_units:
        if not enemy.alive:
            continue
        if enemy.cell not in state.visible_cells and enemy.active:
            continue
        if enemy.cell not in state.explored_cells:
            continue
        draw_unit_icon(screen, enemy, selected_enemy is not None and enemy.unit_id == selected_enemy.unit_id, flag_font)

    for unit in state.player_units:
        if unit.alive:
            draw_unit_icon(screen, unit, selected_player is not None and unit.unit_id == selected_player.unit_id, flag_font)

    for y in range(GRID_ROWS):
        for x in range(GRID_COLS):
            cell = (x, y)
            rect = cell_rect(cell)
            if cell not in state.explored_cells:
                fog = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                fog.fill((4, 7, 12, 240))
                screen.blit(fog, rect.topleft)
            elif cell not in state.visible_cells:
                fog = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                fog.fill((8, 12, 20, 145))
                screen.blit(fog, rect.topleft)

    hover_cell = screen_to_cell(mouse_pos)
    if hover_cell is not None and cell_inside(hover_cell):
        pygame.draw.rect(screen, (240, 243, 180), cell_rect(hover_cell), width=2)

    panel = pygame.Rect(PANEL_X, MAP_Y, PANEL_WIDTH, MAP_HEIGHT)
    pygame.draw.rect(screen, (17, 25, 38), panel, border_radius=10)
    pygame.draw.rect(screen, (62, 92, 126), panel, width=2, border_radius=10)

    screen.blit(ui_font.render(f"Turn {state.turn_number} - {state.turn_side.upper()}", True, (232, 241, 255)), (PANEL_X + 12, MAP_Y + 12))
    screen.blit(
        small_font.render(f"Enemies left: {sum(1 for enemy in state.enemy_units if enemy.alive)}", True, (198, 220, 241)),
        (PANEL_X + 12, MAP_Y + 44),
    )

    y = MAP_Y + 76
    if selected_player is not None:
        screen.blit(ui_font.render(selected_player.name, True, role_color(selected_player.role)), (PANEL_X + 12, y))
        screen.blit(
            small_font.render(
                f"{selected_player.role} | HP {selected_player.hp}/{selected_player.max_hp} | AP {selected_player.ap}",
                True,
                (200, 223, 244),
            ),
            (PANEL_X + 12, y + 28),
        )
        screen.blit(
            small_font.render(f"AIM {selected_player.aim} DEF {selected_player.defense}", True, (187, 211, 234)),
            (PANEL_X + 12, y + 50),
        )
        y += 80

    if selected_player is not None and selected_enemy is not None and selected_enemy.alive:
        preview = shot_preview(state, selected_player, selected_enemy, reaction=False)
        cover_label = "none"
        if preview.cover_bonus == 20:
            cover_label = "half"
        elif preview.cover_bonus == 40:
            cover_label = "full"
        flank_label = "YES" if preview.flanked else "no"
        screen.blit(
            small_font.render(
                f"Shot -> Hit {preview.chance}% | Crit {preview.crit}% | Cover {cover_label} | Flank {flank_label}",
                True,
                (232, 238, 184) if preview.chance >= 60 else (243, 182, 142),
            ),
            (PANEL_X + 12, y),
        )
        y += 28

    controls = [
        "LMB: select / shoot target",
        "RMB: move selected soldier",
        "Shift+LMB on cover: shoot cover",
        "TAB: next soldier",
        "O: overwatch   P: suppression",
        "F: class ability",
        "E or SPACE: end turn",
    ]
    for line in controls:
        screen.blit(small_font.render(line, True, (170, 202, 230)), (PANEL_X + 12, y))
        y += 22

    screen.blit(ui_font.render("Combat Log", True, (226, 240, 253)), (PANEL_X + 12, MAP_Y + 370))
    for idx, line in enumerate(state.log[-10:]):
        color = (194, 215, 238)
        if "eliminated" in line or "complete" in line:
            color = (169, 224, 169)
        if "missed" in line or "Need" in line:
            color = (228, 186, 150)
        screen.blit(small_font.render(line, True, color), (PANEL_X + 12, MAP_Y + 402 + idx * 20))

    if state.mission_result is not None:
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((4, 7, 14, 184))
        screen.blit(overlay, (0, 0))
        if state.mission_result == "victory":
            title = ui_font.render("MISSION SUCCESS", True, (162, 236, 177))
            rewards = (
                f"Rewards: +{state.pending_rewards['supplies']} supplies, "
                f"+{state.pending_rewards['science']} science, +{state.pending_rewards['intel']} intel"
            )
        else:
            title = ui_font.render("MISSION FAILED", True, (244, 157, 157))
            rewards = "Partial recovery applied"
        tip = small_font.render("Press ENTER to return to Geoscape", True, (212, 226, 244))
        reward_line = small_font.render(rewards, True, (210, 220, 236))
        screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 320)))
        screen.blit(reward_line, reward_line.get_rect(center=(SCREEN_WIDTH // 2, 360)))
        screen.blit(tip, tip.get_rect(center=(SCREEN_WIDTH // 2, 394)))


def handle_player_click(
    state: BattleState,
    mouse_cell: Optional[Cell],
    button: int,
    mods: int,
    rng: random.Random,
) -> None:
    if state.turn_side != "player" or state.mission_result is not None or mouse_cell is None:
        return

    selected = get_unit_by_id(state.player_units, state.selected_player_id)
    clicked_player = unit_at_cell(state.player_units, mouse_cell)
    clicked_enemy = unit_at_cell(state.enemy_units, mouse_cell)

    if button == 1:
        if clicked_player is not None:
            state.selected_player_id = clicked_player.unit_id
            return
        if clicked_enemy is not None and clicked_enemy.alive:
            state.selected_enemy_id = clicked_enemy.unit_id
            if selected is not None and selected.ap >= 1:
                if clicked_enemy.cell not in state.visible_cells:
                    add_log(state, "Target hidden in fog")
                    return
                resolve_shot(state, selected, clicked_enemy, rng)
                selected.ap = max(0, selected.ap - 1)
                check_mission_end(state)
            return
        if mods & pygame.KMOD_SHIFT and selected is not None and selected.ap >= 1 and mouse_cell in state.covers:
            shoot_cover(state, selected, mouse_cell, rng)
            check_mission_end(state)
            return

    if button == 3 and selected is not None:
        try_move_player(state, selected, mouse_cell)
        check_mission_end(state)


def main() -> None:
    pygame.init()
    pygame.display.set_caption("ECHO PROTOCOL - Alpha")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    title_font = pygame.font.SysFont("consolas", 52, bold=True)
    menu_font = pygame.font.SysFont("consolas", 30, bold=True)
    ui_font = pygame.font.SysFont("consolas", 25, bold=True)
    small_font = pygame.font.SysFont("consolas", 18)

    grass_tile = make_grass_texture(TILE_SIZE)
    wall_tile = make_wall_texture(TILE_SIZE)
    half_cover_tile = make_cover_texture(TILE_SIZE, "half")
    full_cover_tile = make_cover_texture(TILE_SIZE, "full")

    start_button = Button(pygame.Rect(SCREEN_WIDTH // 2 - 150, 330, 300, 64), "Start Campaign")
    quit_button = Button(pygame.Rect(SCREEN_WIDTH // 2 - 150, 414, 300, 64), "Exit")

    rng = random.Random(20260301)
    app_state = STATE_MENU
    campaign: Optional[CampaignState] = None
    battle: Optional[BattleState] = None
    geoscape_status = ""
    running = True
    pending_battle_commit = False

    while running:
        _ = clock.tick(FPS)
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if app_state == STATE_MENU:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if start_button.contains(mouse_pos):
                        campaign = create_initial_campaign(rng)
                        battle = None
                        geoscape_status = "Campaign initialized"
                        pending_battle_commit = False
                        app_state = STATE_GEOSCAPE
                    elif quit_button.contains(mouse_pos):
                        running = False

            elif app_state == STATE_GEOSCAPE and campaign is not None:
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        idx = int(event.unicode) - 1
                        if 0 <= idx < len(campaign.mission_cards):
                            battle = build_battle_state(campaign, campaign.mission_cards[idx], rng)
                            if battle is not None:
                                app_state = STATE_BATTLE
                                pending_battle_commit = False
                            else:
                                geoscape_status = "Cannot launch mission (invalid squad/spawn)"
                    elif event.key == pygame.K_r:
                        cycle_active_research(campaign)
                        project = active_research(campaign)
                        geoscape_status = f"Active research: {project.name}" if project else "All research complete"
                    elif event.key == pygame.K_l:
                        geoscape_status = attempt_room_upgrade(campaign, "lab")
                    elif event.key == pygame.K_a:
                        geoscape_status = attempt_room_upgrade(campaign, "armory")
                    elif event.key == pygame.K_y:
                        geoscape_status = attempt_room_upgrade(campaign, "relay")
                    elif event.key == pygame.K_ESCAPE:
                        app_state = STATE_MENU
                alive_count = sum(1 for soldier in campaign.squad if soldier.alive)
                if alive_count == 0:
                    app_state = STATE_CAMPAIGN_OVER

            elif app_state == STATE_BATTLE and battle is not None and campaign is not None:
                if event.type == pygame.KEYDOWN:
                    if battle.mission_result is not None and event.key == pygame.K_RETURN:
                        if not pending_battle_commit:
                            apply_battle_result(campaign, battle, rng)
                            pending_battle_commit = True
                        alive_count = sum(1 for soldier in campaign.squad if soldier.alive)
                        geoscape_status = f"Mission result: {battle.mission_result}"
                        battle = None
                        app_state = STATE_CAMPAIGN_OVER if alive_count == 0 else STATE_GEOSCAPE
                        continue

                    if event.key == pygame.K_ESCAPE:
                        app_state = STATE_GEOSCAPE
                        continue

                    if battle.turn_side == "player" and battle.mission_result is None:
                        selected = get_unit_by_id(battle.player_units, battle.selected_player_id)
                        selected_enemy = get_unit_by_id(battle.enemy_units, battle.selected_enemy_id)
                        if event.key == pygame.K_TAB:
                            battle.selected_player_id = next_player_unit_with_ap(battle)
                        elif event.key in (pygame.K_e, pygame.K_SPACE):
                            enemy_turn(battle, rng)
                            check_mission_end(battle)
                        elif event.key == pygame.K_o and selected is not None:
                            set_overwatch(battle, selected)
                        elif event.key == pygame.K_p and selected is not None and selected_enemy is not None:
                            apply_suppression(battle, selected, selected_enemy)
                        elif event.key == pygame.K_f and selected is not None:
                            apply_class_ability(battle, selected)

                if event.type == pygame.MOUSEBUTTONDOWN and battle.mission_result is None:
                    handle_player_click(
                        battle,
                        screen_to_cell(mouse_pos),
                        event.button,
                        pygame.key.get_mods(),
                        rng,
                    )

            elif app_state == STATE_CAMPAIGN_OVER:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    app_state = STATE_MENU

        if app_state == STATE_MENU:
            draw_menu(screen, title_font, menu_font, small_font, start_button, quit_button, mouse_pos)

        elif app_state == STATE_GEOSCAPE and campaign is not None:
            draw_geoscape(screen, campaign, ui_font, small_font, small_font, geoscape_status)

        elif app_state == STATE_BATTLE and battle is not None:
            draw_battle(
                screen,
                battle,
                grass_tile,
                wall_tile,
                half_cover_tile,
                full_cover_tile,
                ui_font,
                small_font,
                mouse_pos,
            )

        elif app_state == STATE_CAMPAIGN_OVER and campaign is not None:
            screen.fill((13, 19, 29))
            title = title_font.render("CAMPAIGN OVER", True, (245, 171, 171))
            subtitle = small_font.render("No soldiers remain. Press ENTER for main menu.", True, (207, 219, 235))
            stats = small_font.render(
                f"Completed missions: {campaign.mission_index} | Supplies: {campaign.supplies} | Intel: {campaign.intel}",
                True,
                (189, 208, 227),
            )
            screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 300)))
            screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 356)))
            screen.blit(stats, stats.get_rect(center=(SCREEN_WIDTH // 2, 388)))

        pygame.display.flip()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
