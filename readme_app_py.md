"""
SCOTTISH COUNTRY DANCE DATABASE (SCDDB)
=======================================

ОСНОВНОЕ ПРИЛОЖЕНИЕ: app.py

ОПИСАНИЕ ПРОЕКТА:
-----------------
Веб-приложение для управления базой данных шотландских танцев с поддержкой
PostgreSQL и SQLite, загрузкой файлов и CRUD операциями.

КОНФИГУРАЦИЯ:
-------------
- Поддерживает PostgreSQL (основная) и SQLite (резервная) БД
- Автоматическое определение доступной БД
- Загрузка файлов в папку dance_files/
- Максимальный размер файла: 16MB

МОДЕЛИ БАЗЫ ДАННЫХ:
-------------------

class BaseModel (Абстрактный класс):
    - id: Integer (primary_key)
    - get_all(): получить все записи
    - get_by_id(id): получить запись по ID
    - get_or_create(**kwargs): получить или создать запись

class SetType (Типы сетов):
    - name: String(100) - название типа
    - description: Text - описание

class DanceFormat (Форматы сетов):
    - name: String(100) - название формата
    - description: Text - описание

class DanceType (Типы танцев):
    - name: String(50) - название типа
    - code: String(1) - код типа
    - description: Text - описание

class Dance (Танцы):
    - name: String(255) - название танца
    - author: String(255) - автор
    - dance_type_id: Integer - ID типа танца
    - size_id: Integer - размер
    - count_id: Integer - счет
    - dance_format_id: Integer - ID формата
    - dance_couple: String(50) - танцующая пара
    - set_type_id: Integer - ID типа сета
    - description: Text - описание
    - published: String(255) - публикация
    - note: Text - примечание

ОСНОВНЫЕ МАРШРУТЫ:
------------------

ГЛАВНАЯ СТРАНИЦА И ТАНЦЫ:
- GET  /                    - главная страница (список танцев)
- GET  /add                 - форма добавления танца
- POST /add                 - обработка добавления танца
- GET  /dance/<id>          - просмотр танца
- GET  /dance/<id>/edit     - редактирование танца
- POST /dance/<id>/edit     - обработка редактирования
- POST /dance/<id>/delete   - удаление танца
- POST /delete-dances       - массовое удаление танцев
- POST /dance/<id>/delete-single - удаление одного танца (JS)

УПРАВЛЕНИЕ ТИПАМИ СЕТОВ:
- GET  /set-types           - список типов сетов
- GET  /set-types/add       - форма добавления типа
- POST /set-types/add       - обработка добавления
- GET  /set-types/<id>/edit - редактирование типа
- POST /set-types/<id>/edit - обработка редактирования
- POST /set-types/<id>/delete - удаление типа

УПРАВЛЕНИЕ ФОРМАТАМИ СЕТОВ:
- GET  /dance-formats           - список форматов
- GET  /dance-formats/add       - форма добавления
- POST /dance-formats/add       - обработка добавления
- GET  /dance-formats/<id>/edit - редактирование
- POST /dance-formats/<id>/edit - обработка редактирования
- POST /dance-formats/<id>/delete - удаление

УПРАВЛЕНИЕ ТИПАМИ ТАНЦЕВ:
- GET  /dance-types           - список типов
- GET  /dance-types/add       - форма добавления
- POST /dance-types/add       - обработка добавления
- GET  /dance-types/<id>/edit - редактирование
- POST /dance-types/<id>/edit - обработка редактирования
- POST /dance-types/<id>/delete - удаление

РАБОТА С ФАЙЛАМИ:
- GET  /dance/<id>/files               - просмотр файлов
- POST /dance/<id>/upload              - загрузка файла
- GET  /dance/<id>/files/<filename>    - скачивание файла
- POST /dance/<id>/files/<filename>/delete - удаление файла

СТАТИСТИКА:
- GET  /stats - статистика БД

ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ:
-----------------------

РАБОТА С ФАЙЛАМИ:
- allowed_file(filename) - проверка разрешенных расширений
- get_dance_files_path(dance_id, dance_name) - путь к файлам
- ensure_dance_folder(dance_id, dance_name) - создание папки
- get_dance_files(dance_id, dance_name) - список файлов

БАЗА ДАННЫХ:
- check_postgres_connection() - проверка подключения PostgreSQL
- setup_database() - настройка БД
- init_database() - инициализация БД
- init_basic_data() - заполнение базовых данных
- safe_int(value, default) - безопасное преобразование в int

ФОРМЫ И ВАЛИДАЦИЯ:
- get_form_data() - данные для форм
- validate_dance_form(form_data) - валидация формы танца

КОНТЕКСТНЫЕ ПРОЦЕССОРЫ:
- format_datetime(timestamp, fmt) - форматирование даты
- db_type - тип текущей БД

КОНТЕКСТНЫЙ МЕНЕДЖЕР:
- db_session() - управление сессиями БД

ЗАПУСК ПРИЛОЖЕНИЯ:
------------------
1. Установите зависимости: pip install -r requirements.txt
2. Запустите приложение: python app.py
3. Приложение доступно по адресу: http://localhost:5000

ПРИМЕЧАНИЯ:
-----------
- При первом запуске автоматически создается структура БД
- Поддерживаются файлы: png, jpg, jpeg, gif, pdf, txt, doc, docx
- Папка для загрузок: dance_files/
- Поддерживается пагинация (25, 50, 100 записей на странице)
- Есть поиск по названию и автору
"""