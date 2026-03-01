# gameX

Python alpha prototype for the `tech.md` concept (XCOM-style loop + echo setting).

Implemented now:
- main menu and campaign flow
- geoscape/base screen (missions, resources, research, room upgrades)
- turn-based tactical combat on grid
- AP system (2 AP per soldier)
- hit chance + crit + cover (half/full) + flanking
- fog of war + enemy pod activation
- overwatch + suppression
- destructible cover
- soldier classes and mission progression (XP/levels)
- Windows `.exe` build script
- Docker build workflow

## Run (dev)
1. Install Python 3.11+.
2. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
3. Start game:
   ```bash
   python main.py
   ```

## Build EXE (Windows)
Run:
```bat
build_exe.bat
```

After build, executable will be in:
`dist\EchoProtocolPrototype.exe`

## Build in Docker
Check code:
```bash
docker compose run --rm check
```

Build artifact in container:
```bash
docker compose run --rm build
```

Shortcut for Windows:
```bat
docker_build.bat
```

After Docker build, artifact will be in:
`dist\EchoProtocolPrototype` (Linux binary)

## Controls
### Geoscape
- `1` / `2` / `3`: launch mission
- `R`: switch active research
- `L`: upgrade Lab
- `A`: upgrade Armory
- `Y`: upgrade Relay
- `ESC`: back to menu

### Battle
- `LMB`: select unit / shoot enemy
- `RMB`: move selected unit
- `Shift + LMB` on cover: shoot cover
- `TAB`: cycle soldiers
- `O`: overwatch
- `P`: suppression (on selected enemy)
- `F`: class ability
- `E` or `SPACE`: end turn
- `ENTER`: continue after mission result
