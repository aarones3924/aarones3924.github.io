@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
  where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
  echo 未检测到 Python 3。
  echo 请先安装 Python 3.10+，并勾选 "Add Python to PATH"。
  pause
  exit /b 1
)

echo 正在安装/检查依赖...
%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 (
  echo 依赖安装失败，请检查网络或权限。
  pause
  exit /b 1
)

echo 正在启动程序...
%PY_CMD% main.py

echo.
echo 程序已退出。如有报错，请把上面的报错截图发我。
pause
