@echo off
chcp 65001 >nul
title 实验室助手 - Windows 打包脚本
echo ============================================
echo   实验室助手 - 一键打包（Windows）
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
echo [2/2] 打包完成！产物在 dist\LabAssistant\ 目录
echo   - LabAssistant.exe 双击即可运行
echo   - 分发给他人时把整个 LabAssistant 文件夹压缩成 zip 即可
echo.
pause
