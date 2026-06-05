@echo off
echo Starting Android Emulator (Medium_Phone_API_36.0)...
call C:\Users\natas\AppData\AndroidCLI\android.exe emulator start Medium_Phone_API_36.0
echo.
echo Installing and deploying Athena APK...
call C:\Users\natas\AppData\AndroidCLI\android.exe run --apks="c:\Users\natas\.gemini\antigravity-ide\scratch\athena.apk"
echo.
echo Launch complete.
pause
