@echo off
echo ======================================
echo Updating ChurchHub to GitHub
echo ======================================

git status

set /p msg=Enter commit message:

git add .
git commit -m "%msg%"
git push origin main

echo.
echo ======================================
echo GitHub Updated Successfully
echo ======================================
pause