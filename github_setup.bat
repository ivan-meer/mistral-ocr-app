@echo off
echo Инициализация Git репозитория для Mistral OCR App

echo Создание Git репозитория...
git init

echo Добавление файлов в репозиторий...
git add .

echo Создание первого коммита...
git commit -m "Initial commit: Mistral OCR App"

echo --------------------------------------
echo Теперь вам нужно создать репозиторий на GitHub и связать его с локальным.
echo Выполните следующие команды:
echo.
echo git remote add origin https://github.com/YourUsername/mistral-ocr-app.git
echo git branch -M main
echo git push -u origin main
echo.
echo Не забудьте заменить YourUsername на ваше имя пользователя на GitHub!
echo --------------------------------------
