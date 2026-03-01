# gameX

3D top-down Python prototype of ECHO PROTOCOL.

Engine:
- `Panda3D` (no `pygame` in main runtime)

Implemented now (`main.py`):
- 3D scene with top-down/angled camera
- procedural 3D textures (ground, walls, cover, units)
- main menu
- WASD movement
- mouse shooting with ray-to-ground aiming
- enemies with chase/attack AI
- destructible cover blocks
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
- `ENTER`: start mission from menu / restart after result
- `ESC`: menu (during play) or exit (menu/result)
- `WASD`: move
- `LMB`: shoot
- `R`: restart after mission result

## Fix for "No graphics pipe is available"
If you still see this error:
1. Reinstall Panda3D:
   ```bash
   python -m pip install --force-reinstall panda3d==1.10.15
   ```
2. Run from project root (so `Config.prc` is found).
3. Prefer the new `onedir` build from `build_exe.bat` (it bundles Panda3D display plugins more reliably than onefile).
