@echo off
color 0a
title 罗根一键追爆
setlocal enabledelayedexpansion
chcp 936
cls

REM 切换到脚本所在目录

REM 激活虚拟环境
CALL "miniconda3\Scripts\activate.bat" avatar

REM 设置FFMPEG环境变量
SET "FFMPEG_PATH=ffmpeg\bin"
SET "PATH=%PATH%;%FFMPEG_PATH%"

REM 设置ImageMagick环境变量
SET "IMAGE_PATH=ImageMagick-7.1.1-Q16-HDRI"
SET "PATH=%PATH%;%IMAGE_PATH%"
SET "IMAGEMAGICK_BINARY=ImageMagick-7.1.1-Q16-HDRI\magick.exe"

REM 启动后端服务
START /b "" "%~dp0miniconda3\envs\avatar\python.exe" "%~dp0combined_launcher.py"

REM 等待服务器启动
ECHO 正在等待服务器启动，请稍等...
timeout /t 5 /nobreak

REM 查找Chrome浏览器路径
SET "CHROME_PATH="

IF "%CHROME_PATH%"=="" (
    IF EXIST "C:\Program Files\Google\Chrome\Application\chrome.exe" (
        SET "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
    ) ELSE IF EXIST "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
        SET "CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ) ELSE IF EXIST "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
        SET "CHROME_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
    )
)

REM 启动浏览器或提示手动访问
IF "%CHROME_PATH%"=="" (
    ECHO 未找到Chrome浏览器，请手动打开浏览器并访问 http://127.0.0.1:8000
    ECHO 服务器已在后台启动，您可以使用任何浏览器访问上述地址。
) ELSE (
    SET "CHROME_USER_DATA=%LOCALAPPDATA%\Google\Chrome\User Data"
    ECHO 启动Chrome浏览器: %CHROME_PATH%
    ECHO 使用Chrome配置目录: %CHROME_USER_DATA%
    START "" "%CHROME_PATH%" --remote-debugging-port=9222 --user-data-dir="%CHROME_USER_DATA%" http://127.0.0.1:8000
)

ECHO.
ECHO 罗根一键追爆服务已启动，您可以关闭此窗口。
ECHO 如需退出程序，请关闭Python服务器窗口和浏览器。
