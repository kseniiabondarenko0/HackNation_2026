from django.db import models


def split_list(value):
    """'a, b ,c' -> ['a', 'b', 'c'] (lowercase, no empties, order kept)."""
    return [v for v in dict.fromkeys(p.strip().lower() for p in (value or "").split(",")) if v]


class Recipient(models.Model):
    """Profile of a potential user/partner/investor. Candidates only: a match is not consent."""
    TYPES = [("ctt", "Centrum transferu technologii"), ("samorzad", "Samorząd"), ("szkola", "Szkoła / oświata"),
             ("szpital", "Szpital / ochrona zdrowia"), ("firma", "Przedsiębiorstwo"),
             ("inwestor", "Inwestor / fundusz"), ("ibo", "Instytucja otoczenia biznesu"),
             ("agencja", "Agencja publiczna"), ("ngo", "Organizacja pozarządowa"), ("uczelnia", "Uczelnia"),
             ("osoba", "Osoba prywatna")]
    name = models.CharField(max_length=200)
    institution_type = models.CharField(max_length=20, choices=TYPES)
    region = models.CharField(max_length=100, blank=True)
    needs = models.TextField(help_text="Czego szuka odbiorca (pokazywane w uzasadnieniu dopasowania).")
    tags = models.CharField(max_length=500, help_text="Słowa kluczowe lub ich początki, po przecinku, np. „odpad, recykl, beton”.")
    sectors = models.CharField(max_length=300, blank=True,
                               help_text="Sektory z analizy, po przecinku, np. „Energia i środowisko”.")
    paths = models.CharField(max_length=100, blank=True,
                             help_text="Interesujące ścieżki: rozwoj, transfer, komercjalizacja, wdrozenie.")
    stages = models.CharField(max_length=100, blank=True,
                              help_text="Interesujące etapy: idea, prototype, pilot, in_use.")
    is_example = models.BooleanField(default=True,
                                     help_text="Profil przykładowy (typ instytucji), nie konkretna instytucja.")
    active = models.BooleanField(default=True)
    # Needs submitted by institutions themselves ("Zgłoś potrzebę"): the task lists organisations looking for
    # solutions among the system's users. Contact data is shown to staff only and stored only with consent.
    contact = models.CharField(max_length=200, blank=True, help_text="Kontakt (widoczny tylko dla zespołu).")
    consent = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "odbiorca"
        verbose_name_plural = "odbiorcy (profile)"

    def __str__(self):
        return self.name

    def tag_list(self):
        return split_list(self.tags)

    def sector_list(self):
        return split_list(self.sectors)

    def path_list(self):
        return split_list(self.paths)

    def stage_list(self):
        return split_list(self.stages)
