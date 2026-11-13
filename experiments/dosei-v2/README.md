# MORPHEUS / О-СОЗНАНИЕ-9000

## EEG-002 v2

Повторный аудит и поисковое моделирование используют все доступные записи EEG-001, включая прежнюю финальную группу. [Отчёт EEG-002](reports/EEG_002_REPORT.md) · [Протокол](EEG_002_PROTOCOL.md) · [Внешние данные](reports/EEG_002_EXTERNAL.md)

Команды из каталога эксперимента. `LOCAL_RUN` — локальный каталог исходного EEG-001 с полными выгрузками разработки и holdout. `LOCAL_ARCHIVE` — исходный `data.zip` DOSE-I v2.

```text
python -m tools.replicate_eeg001 LOCAL_ARCHIVE LOCAL_RUN runs/eeg-002-replay local-replication.json
python -m tools.audit_eeg002 --run LOCAL_RUN --archive LOCAL_ARCHIVE --output local-qc-audit.json
python -m tools.explore_eeg002 --source LOCAL_RUN --output local-eeg-002
python -m tools.audit_duplicate_timestamps LOCAL_ARCHIVE LOCAL_RUN runs/duplicate-audit local-duplicate-audit.json
python reports/eeg_002_external_qc.py
python -m unittest discover -s tests
```

## EEG-001

Локальный CLI для изучения клинически размеченных переходов поведенческой отзывчивости в DOSE-I v2. Модели рассчитаны на ретроспективное исследование. Единица группировки и интервалов — запись DOSE-I.

## Запуск в PowerShell

Нужны Python 3.10 и [DOSE-I v2](https://zenodo.org/records/22145442). Поместите `data.zip` и `metadata.zip` в `data/dose-i/` с учётом [условий использования](DATA_SOURCES.md). Распаковывать архивы не требуется. Команды выполнять из корня проекта.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m unittest discover -s tests
$MorpheusPython = '.\.venv\Scripts\python.exe'
& $MorpheusPython -m ocon9000 inspect
& $MorpheusPython -m ocon9000 freeze --run runs/dosei-v2-replay
& $MorpheusPython -m ocon9000 build --run runs/dosei-v2-replay
& $MorpheusPython -m ocon9000 baseline --run runs/dosei-v2-replay
& $MorpheusPython -m ocon9000 trajectory --run runs/dosei-v2-replay
& $MorpheusPython -m ocon9000 falsify --run runs/dosei-v2-replay
& $MorpheusPython -m ocon9000 report --run runs/dosei-v2-replay
```

`freeze` проверяет опубликованный MD5 архива и записывает его SHA-256 и полный сплит. `build` пишет профили условий, сводку QC, исходные события и таблицу окон только для train/validation. `baseline` сравнивает методы на общей когорте. Подробности о целевой переменной, когорте и ограничениях есть в [протоколе](RESEARCH_PROTOCOL.md). Актуальные результаты и статусы есть в [журнале](PROGRESS.md) и [бэклоге](BACKLOG.md).

В зарегистрированном запуске команда `experiment` проверяет гипотезу из `research/hypotheses.jsonl`. После рецензии в `research/decisions.jsonl` команда `seal` фиксирует кандидата. Команда `holdout` выполняет одно открытие на каталог запуска. Для повтора расчётов разработки используйте команды выше, сохраняя финальный holdout закрытым в повторных каталогах.
