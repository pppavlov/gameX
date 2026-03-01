# gameX

Simple Python prototype for the game concept from `tech.md`.

Implemented now:
- main menu (start/exit)
- playable top-down field
- movement (`WASD` / arrows)
- shooting (left mouse button)
- simple enemy AI
- procedural simple textures (ground/walls/sprites)
- Windows `.exe` build script

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

## Controls
- `WASD` or arrows: move
- Left mouse button: shoot
- `ESC`: back to menu
- `R`: restart after game over
