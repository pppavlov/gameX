# gameX

Simple Python prototype for the game concept from `tech.md`.

Implemented now:
- main menu (start/exit)
- playable top-down field
- grid movement (`WASD` / arrows, step by tile)
- shooting (left mouse button)
- simple enemy AI
- procedural simple textures (ground/walls/sprites)
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
- `WASD` or arrows: move by grid cells
- Left mouse button: shoot
- `ESC`: back to menu
- `R`: restart after game over
