# Как выложить проект на GitHub

Все файлы проекта находятся в папке `book-translation-agent`. Публиковать нужно
только её: родительская папка с книгами для этого не подходит.

Git — это сохранённые версии проекта на компьютере. GitHub — сайт, куда их можно
отправить. Подготовка локального репозитория сама по себе ничего не публикует.

## Готовые название и описание

Название:

```text
book-translation-agent
```

Описание на английском:

```text
Research-first book translation for Codex: a capable lead model, smaller workers, researched glossaries, and checked EPUBs.
```

Темы для поля Topics: `codex`, `translation`, `epub`, `glossary`, `ai-agents`,
`python`, `humanities`.

## Самый простой способ — GitHub Desktop

1. Установи [GitHub Desktop](https://desktop.github.com/) и войди в свой аккаунт.
2. В меню выбери **File → Add Local Repository** и укажи подготовленную папку
   `book-translation-agent`. Если начинаешь с распакованного ZIP, сначала создай
   локальный репозиторий из этой папки через Desktop.
3. Если видишь подготовленные, но ещё не сохранённые изменения, проверь список
   файлов и сохрани их кнопкой Commit с описанием `Prepare initial public release`.
4. Нажми **Publish repository**. Вставь название и описание выше. Галочка
   **Keep this code private** оставляет проект закрытым; убери её, если хочешь
   сделать его общедоступным. Именно окончательное нажатие **Publish Repository**
   отправляет файлы на сайт.

Основа инструкции — официальные руководства GitHub:
[добавление папки](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-a-repository-from-your-local-computer-to-github-desktop)
и [публикация проекта](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-an-existing-project-to-github-using-github-desktop).

Перед открытой публикацией должны быть выбраны лицензия и публичные данные
автора коммитов. Лицензия агента относится к его коду и инструкциям; она не даёт
права распространять переводимые книги.

## Что увидят другие люди

Главная страница — английский [README](../README.md). В нём есть русская версия,
установка, пример запроса, объяснение выбора моделей и честные ограничения.
Скрытые `.agents`, `.codex`, `.github` — необходимые части проекта; Desktop
отправляет их вместе с остальными файлами.

После публикации во вкладке **Actions** должны пройти проверки **Checks**.
Они проверяют программу и сборку EPUB, не переводят книги и не используют лимиты
моделей. Пока проверки не запускались на GitHub, не называй их пройденными.

Настрой также [закрытый приём сообщений об уязвимостях](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository),
чтобы люди могли сообщать о проблемах без публичного раскрытия деталей.

## Как хранить свои книги

Создай внутри проекта папку `books` и складывай исходники и результаты туда.
Она исключена из Git. Перед отправкой новых изменений всё равно просматривай
список файлов: исключения не защищают от намеренного добавления или от файлов,
которые уже попали в историю.

Для ZIP есть отдельная команда; её может выполнить Codex:

```sh
python3 tools/release.py --update-manifest
python3 tools/release.py --check --zip dist/book-translation-agent.zip
```

Она берёт только файлы из заранее заданного списка. ZIP содержит весь агент,
включая скрытые папки, и не содержит историю Git и личные книги.
