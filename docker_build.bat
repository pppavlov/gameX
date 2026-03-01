@echo off
setlocal

echo [1/2] Build Docker image...
docker compose build build
if errorlevel 1 exit /b 1

echo [2/2] Build game artifact in container...
docker compose run --rm build
if errorlevel 1 exit /b 1

echo Done. Artifact: dist\EchoProtocolPrototype
pause
