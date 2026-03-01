@echo off
setlocal

echo [1/3] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo [2/3] Building EXE...
pyinstaller --noconfirm --clean --windowed --onedir --name EchoProtocolPrototype --collect-all panda3d --add-data "Config.prc;." main.py

echo [3/3] Done.
echo EXE path: dist\EchoProtocolPrototype\EchoProtocolPrototype.exe
pause
