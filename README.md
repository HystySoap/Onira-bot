 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/README.md b/README.md
index fdb1044af490f2a1945d8a2e644209303b26fce3..62474852e27cc1eb17107a71eb5ad8f3078fea42 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,41 @@
-# Onira-bot
\ No newline at end of file
+# Onira-bot
+
+Telegram-бот для бережного разбора снов с помощью Gemini.
+
+## Настройка
+
+Для запуска боту нужны две переменные окружения:
+
+- `TELEGRAM_TOKEN` — токен бота от BotFather;
+- `GEMINI_KEY` — ключ Google Gemini API;
+
+Для приёма платежей дополнительно задайте `PROVIDER_TOKEN` — платёжный токен
+ЮKassa из BotFather. Без него бот продолжит работать, но вместо счёта покажет
+контакт поддержки.
+
+По умолчанию используется модель `gemini-flash-latest`. При необходимости её
+можно переопределить необязательной переменной `GEMINI_MODEL` без изменения кода.
+
+Не добавляйте настоящие токены в репозиторий. Если токен уже попадал в историю
+Git, отзовите его и выпустите новый.
+
+## Локальный запуск
+
+```bash
+python -m pip install -r requirements.txt
+export TELEGRAM_TOKEN="..."
+export GEMINI_KEY="..."
+export PROVIDER_TOKEN="..."
+python bot.py
+```
+
+После запуска бот принимает Telegram-обновления через polling, а на порту `8080`
+поднимается служебная Flask-страница для проверки доступности процесса.
+
+## Ошибка Render: `handle_callback is not defined`
+
+Эта ошибка означает, что Render запустил старую версию `bot.py`. В текущей
+версии обработчик определён до запуска приложения. В Render откройте **Events**,
+нажмите **Manual Deploy → Deploy latest commit** и убедитесь, что сервис подключён
+к ветке с последним коммитом. После успешного запуска в журнале появится строка
+`ONIRA пробудилась`.
 
EOF
)
