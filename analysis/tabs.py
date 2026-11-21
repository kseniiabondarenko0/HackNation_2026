"""The three lists of the radar. One definition for the views, the overview, the export and the storage policy,
so a counter can never disagree with the list it belongs to.

  glowna      Interesujące    - confirmed by the AI (score >= threshold, current date, verified quote)
  weryfikacja Do weryfikacji  - temporary queue: waiting for the AI, or analysed but still unconfirmed (e.g. unknown date)
  wszystkie   Wszystkie       - everything that went through the AI check and was not removed (the two groups above
                                without items still waiting for their first analysis)
Items the AI rejected (score < threshold, not an innovation, too old) are deleted by analysis.retention."""
from django.db.models import Q

TABS = {"glowna": "Interesujące", "weryfikacja": "Do weryfikacji", "wszystkie": "Wszystkie"}

INTERESTING = Q(analysis__verdict="glowna")
WAITING = Q(analysis__isnull=True) | Q(analysis__verdict__in=("weryfikacja", ""))
CHECKED = Q(analysis__verdict__in=("glowna", "weryfikacja"))


def tab_q(view):
    return {"glowna": INTERESTING, "weryfikacja": WAITING, "wszystkie": CHECKED}[view]
