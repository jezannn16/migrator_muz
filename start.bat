@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Перенос лайков Yandex -> YT Music ===
echo Проверка зависимостей...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
echo Запуск интерфейса...
python app.py
pause
