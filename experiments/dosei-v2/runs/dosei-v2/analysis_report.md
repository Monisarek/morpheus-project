# DOSE-I v2. Итоги запуска

На holdout из 34 пригодных записей модель ЭЭГ с контекстом получила AP 0,360 против 0,283 у модели по времени и дозе. Парная разность +0,078 (95% ДИ +0,020…+0,135), интервалы по записям. Оценка основана на 1 684 окнах с наблюдаемыми исходами, прошедших QC.

- [Научный отчёт](../../reports/SCIENTIFIC_REPORT.md) и [инструкция повтора](../../reports/REPRODUCIBILITY.md)
- [Публичный манифест](manifest.public.json), [QC разработки](qc_summary.json), [финальный QC](holdout_qc_summary.json)
- [Метрики разработки](metrics.json), [контроли](falsification.json), [траектории](trajectory.json), [эксперимент H01](variant_metrics.json)
- [Кандидат](candidate.json), [журнал открытия](holdout_release.json), [финальные метрики](holdout_metrics.json), [график](average_precision.svg)
