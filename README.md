# Запуск сервиса

Сначала настраивается окружение для сервиса (значения по умолчанию указаны в файле `.env.example').  

```bash
cp .env.example .env
./start.sh
```

## Остановка и повторный запуск

```bash
./stop.sh
./start.sh
```

Все данные сохраняются в Docker-томе `server_data` и сохраняются между перезапусками.  

# Формат DISC-опроса

Опрос - JSON-файл (см. `examples/disc_survey_example.json`):

```json
{
  "title": "Мой DISC-опрос",
  "description": "необязательно",
  "scales": {"D": "Доминирование", "I": "Влияние", "S": "Постоянство", "C": "Соответствие"},
  "questions": [
    {
      "id": "q1",
      "text": "Текст вопроса",
      "options": [
        {"text": "Вариант 1", "scores": {"D": 3, "I": 1}},
        {"text": "Вариант 2", "scores": {"S": 2}}
      ]
    }
  ]
}
```

# Структура проекта

```
app/            Flask-приложение
  templates/    Jinja-шаблоны
  static/       CSS/JS
scripts/        Python-скрипты, не относящиеся к сервису
examples/       Пример DISC-опроса
web-server, docker-compose.yml, start.sh, stop.sh
```
