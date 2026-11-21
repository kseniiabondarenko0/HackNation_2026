from django import template
from django.utils.html import format_html

register = template.Library()

SECTOR_COLORS = {
    "Zdrowie i medycyna": "var(--pink)", "Energia i środowisko": "var(--lime)",
    "Materiały i budownictwo": "var(--muted)", "IT i sztuczna inteligencja": "var(--purple)",
    "Edukacja": "var(--lime)", "Rolnictwo i żywność": "var(--lime)", "Lotnictwo i kosmos": "var(--purple)",
    "Motoryzacja": "var(--ink)", "Transport i mobilność": "var(--muted)",
    "Administracja i samorząd": "var(--ink)", "Pomoc społeczna i włączenie": "var(--pink)",
}


@register.simple_tag
def icon(name, cls=""):
    return format_html('<svg class="i {}" aria-hidden="true"><use href="#i-{}"/></svg>', cls, name)


@register.filter
def sector_color(sector):
    return SECTOR_COLORS.get(sector, "var(--ink)")


@register.filter
def refno(pk):
    return f"RI-{int(pk):04d}"


def _level(value):
    return "Wysoki" if value >= 70 else "Średni" if value >= 50 else "Niski"


@register.filter
def level(value):
    return _level(value) if isinstance(value, (int, float)) else ""


@register.inclusion_tag("web/_score.html")
def score(value, label=True):
    """Potential 0-100 as ten blocks; None renders 'brak danych' (missing data is not a low score)."""
    if not isinstance(value, (int, float)):  # None, or "" when the analysis itself is missing
        return {"value": None}
    return {"value": value, "level": _level(value), "label": label,
            "bars": [i < int(value / 10 + 0.5) for i in range(10)]}


@register.filter
def bars3(score):
    """Rubric score 0-3 as three blocks."""
    return [i < int(score) for i in range(3)]
