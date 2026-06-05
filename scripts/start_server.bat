@echo off
chcp 65001 >nul
echo ========================================
echo   智扫通 Agent API 启动脚本
echo ========================================
echo.

:: 1. 清理残留进程
echo [1/2] 清理残留进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do (
    echo   发现占用 8000 端口的进程 PID=%%a，正在终止...
    taskkill //F //PID %%a >nul 2>&1
)
echo   完成
echo.

:: 2. 等待端口释放
echo [2/2] 等待端口释放...
timeout /t 2 /nobreak >nul

:: 3. 启动服务
echo 启动 API 服务...
echo.
python api_server.py

pause
