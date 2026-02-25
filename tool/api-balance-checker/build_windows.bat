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

echo [1/3] 安装依赖...
%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 (
  echo 依赖安装失败
  pause
  exit /b 1
)

echo [2/3] 安装打包工具...
%PY_CMD% -m pip install pyinstaller
if errorlevel 1 (
  echo PyInstaller 安装失败
  pause
  exit /b 1
)

echo [3/3] 开始打包...
%PY_CMD% -m PyInstaller --noconfirm --clean --onefile --windowed --name "API余额查询" main.py
if errorlevel 1 (
  echo 打包失败
  pause
  exit /b 1
)

echo.
echo 打包完成：dist\API余额查询.exe
pause
