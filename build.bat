@echo off
chcp 65001 >nul
echo ========================================
echo    英语每日记录 - 打包脚本
echo ========================================
echo.

echo [1/2] 安装 PyInstaller...
pip install pyinstaller -q

echo [2/2] 开始打包...
pyinstaller build.spec --clean

echo.
if exist "dist\英语每日记录.exe" (
    echo ========================================
    echo    打包成功！
    echo ========================================
    echo.
    echo 可执行文件位于: dist\英语每日记录.exe
    echo.
    echo 双击运行即可使用！
) else (
    echo 打包失败，请检查错误信息
)
echo.
pause
