@echo off
chcp 65001 >nul
title 药鉴 - Windows 打包脚本
echo ============================================
echo   药鉴 - 一键打包（Windows）
echo ============================================
echo.
cd /d %~dp0..
echo [1/2] 正在用 PyInstaller 打包（约 2~5 分钟）...
venv\Scripts\pyinstaller.exe build\app.spec --noconfirm --workpath build\work --distpath dist
if errorlevel 1 (
    echo 打包失败，请检查上方错误信息。
    pause
    exit /b 1
)
echo.
echo [2/2] 打包完成！产物在 dist\YaoJian\ 目录
echo   - YaoJian.exe 双击即可运行
echo   - 分发给他人时把整个 YaoJian 文件夹压缩成 zip 即可
echo.
pause
