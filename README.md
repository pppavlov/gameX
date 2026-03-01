# gameX

3D top-down Python prototype of ECHO PROTOCOL.

Engine:
- `Panda3D` (no `pygame` in main runtime)

Implemented now (`main.py`):
- 3D scene with top-down/angled camera
- turn-based tactical loop (player turn / enemy turn)
- AP system (2 AP), unit selection, end turn
- grid movement with path cost (1 AP short move, 2 AP long move)
- hit chance / crit / cover / flank calculation
- overwatch and fortify actions
- procedural 3D textures (ground, walls, trees, rocks, houses, units)
- proper main menu (buttons Start/Exit + keyboard shortcuts)
- soldier models with weapon
- shooting animation (muzzle flash + recoil)
- mouse tactical controls (select / move / shoot)
- enemies with turn-based AI
- destructible environment objects (cover, trees, rocks, houses)
- mission complete / mission failed flow
- Windows `.exe` build script
- Docker build workflow

Legacy:
- previous 2D alpha is kept in `main_2d_alpha.py`

## Run (dev)
1. Install Python 3.11+.
2. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
3. Start:
   ```bash
   python main.py
   ```

## Build EXE (Windows)
```bat
build_exe.bat
```

Output:
`dist\EchoProtocolPrototype\EchoProtocolPrototype.exe`

## Build in Docker
Check code:
```bash
docker compose run --rm check
```

Build artifact:
```bash
docker compose run --rm build
```

Windows shortcut:
```bat
docker_build.bat
```

Docker artifact:
`dist/EchoProtocolPrototype/` (Linux app directory)

## Controls
- Menu: `ENTER` start, `ESC` exit, or click buttons
- Battle:
- `LMB`: select soldier / attack enemy
- `RMB`: move selected soldier
- `TAB`: next soldier
- `O`: overwatch
- `F`: fortify
- `E` or `SPACE`: end turn
- `SHIFT + LMB` on object: shoot cover/object
- Camera:
- `WASD` or arrows: pan camera
- `Q` / `E`: rotate camera
- Mouse wheel: zoom
- `ESC`: back to menu (during play/game over)
- `R`: restart after mission result

## Fix for "No graphics pipe is available"
If you still see this error:
1. Reinstall Panda3D:
   ```bash
   python -m pip install --force-reinstall panda3d==1.10.15
   ```
2. Run from project root (so `Config.prc` is found).
3. Prefer the new `onedir` build from `build_exe.bat` (it bundles Panda3D display plugins more reliably than onefile).
