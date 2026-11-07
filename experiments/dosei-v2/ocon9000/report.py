"""Render aggregate average precision and recording-bootstrap intervals."""

from html import escape
import json


def plot(run):
    files = [run / "metrics.json"]
    if (run / "holdout_metrics.json").exists():
        files.append(run / "holdout_metrics.json")
    cohorts = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    models = list(cohorts[0]["models"])
    height = 115 + 54 * len(models)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="810" height="{height}" viewBox="0 0 810 {height}" role="img">',
             '<title>Average precision with 95% recording-bootstrap intervals</title>',
             '<rect width="100%" height="100%" fill="#fff"/>',
             '<g font-family="Arial, sans-serif" fill="#14283d">',
             '<text x="25" y="34" font-size="22" font-weight="bold">Average precision · DOSE-I v2</text>',
             '<text x="25" y="57" font-size="14">Intervals resample recordings. All models use the same eligible windows.</text>']
    for tick in range(6):
        x = 225 + 540 * tick / 5
        parts.append(f'<line x1="{x}" x2="{x}" y1="83" y2="{height - 35}" stroke="#d8e1eb"/>')
        parts.append(f'<text x="{x}" y="{height - 15}" text-anchor="middle" font-size="12">{tick / 5:.1f}</text>')
    for i, model in enumerate(models):
        y = 100 + 54 * i
        parts.append(f'<text x="25" y="{y + 10}" font-size="13">{escape(model.replace("_", " "))}</text>')
        for cohort, color, dy in zip(cohorts, ("#235aab", "#bb4a28"), (0, 15)):
            metric = cohort["models"][model]["average_precision"]
            lo, hi = [225 + 540 * value for value in metric["ci95"]]
            point = 225 + 540 * metric["value"]
            title = f'{cohort["evaluation_split"]}: {metric["value"]:.3f}'
            parts.append(f'<g><title>{escape(title)}</title><line x1="{lo:.2f}" x2="{hi:.2f}" y1="{y + dy}" y2="{y + dy}" '
                         f'stroke="{color}" stroke-width="2"/><circle cx="{point:.2f}" cy="{y + dy}" r="4.5" fill="{color}"/></g>')
    parts.append('<text x="590" y="36" fill="#235aab" font-size="13">Validation</text>')
    if len(cohorts) == 2:
        parts.append('<text x="680" y="36" fill="#bb4a28" font-size="13">Holdout</text>')
    parts.extend(("</g>", "</svg>"))
    output = run / "average_precision.svg"
    output.write_text("\n".join(parts), encoding="utf-8")
    return output
