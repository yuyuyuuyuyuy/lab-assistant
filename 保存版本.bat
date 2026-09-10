@echo off
chcp 65001 >nul
title 药鉴 - 保存版本
echo ============================================
echo   药鉴 - 保存版本（本机快照）
echo ============================================
echo.
cd /d %~dp0
git add -A
git commit -m "保存版本 %date:~0,10% %time:~0,5%"
if errorlevel 1 (
    echo.
    echo 提示：没有检测到代码改动，或存档失败。
    echo （如果刚才确实改过代码，请把本窗口内容截图发给 Claude 处理）
    pause
    exit /b 1
)
echo.
echo ============================================
echo   ✓ 版本已保存！共 %date:~0,10% %time:~0,5%
echo   想备份到云端（Gitee）请再双击「同步云端.bat」
echo ============================================
pause
