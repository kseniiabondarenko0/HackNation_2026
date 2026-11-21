from django import forms
from analysis.regions import CHOICES as REGION_CHOICES

MIN_TEXT = 150
# Who can use the site: public institutions from the task, and also schools, private firms and private persons.
SUBMITTER_CHOICES = [("school", "Szkoła / przedszkole"), ("university", "Uczelnia"), ("local_gov", "Samorząd (gmina, powiat, województwo)"),
                     ("agency", "Inna instytucja publiczna"), ("research", "Instytut badawczy"), ("company", "Firma prywatna"),
                     ("ngo", "Organizacja pozarządowa"), ("person", "Osoba prywatna")]
CONSENT_LABEL = ("Zgadzam się na przetwarzanie podanych danych osobowych (imię i nazwisko, kontakt) w celu obsługi "
                 "zgłoszenia przez zespół Radaru Innowacji (RODO, art. 6 ust. 1 lit. a). Zgodę można wycofać.")


class HoneypotMixin:
    """Public forms: a hidden field people never fill. Bots do, and their post is refused."""
    def clean_strona_www(self):
        if self.cleaned_data.get("strona_www"):
            raise forms.ValidationError("Formularz odrzucony.")
        return ""


class SubmitForm(HoneypotMixin, forms.Form):
    submitter_type = forms.ChoiceField(label="Kto zgłasza", choices=SUBMITTER_CHOICES, initial="school", required=False)
    organization = forms.CharField(label="Nazwa instytucji lub firmy (puste dla osoby prywatnej)", max_length=200,
                                   required=False)
    region = forms.ChoiceField(label="Województwo", required=False,
                               choices=[("", "nie podaję / cała Polska")] + REGION_CHOICES)
    title = forms.CharField(label="Tytuł", max_length=300, required=False)
    url = forms.URLField(label="Adres strony z opisem (opcjonalnie)", max_length=800, required=False)
    text = forms.CharField(label="Opis rozwiązania", max_length=20000, required=False,
                           widget=forms.Textarea(attrs={"rows": 10}))
    author_name = forms.CharField(label="Autor lub autorka (opcjonalnie)", max_length=200, required=False)
    show_name = forms.BooleanField(label="Pokaż imię i nazwisko publicznie na karcie innowacji", required=False)
    contact = forms.CharField(label="Kontakt: e-mail lub telefon (opcjonalnie, widoczny tylko dla zespołu)",
                              max_length=200, required=False)
    consent = forms.BooleanField(label=CONSENT_LABEL, required=False)
    strona_www = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
                                 label="Nie wypełniaj tego pola")

    def clean(self):
        data = super().clean()
        if (data.get("author_name") or data.get("contact")) and not data.get("consent"):
            raise forms.ValidationError("Podając imię i nazwisko lub kontakt, zaznacz zgodę na przetwarzanie danych "
                                        "albo usuń te dane.")
        text, url = (data.get("text") or "").strip(), data.get("url")
        if not url and len(text) < MIN_TEXT:
            raise forms.ValidationError(
                f"Wklej opis (min. {MIN_TEXT} znaków) albo podaj adres strony, z której pobierzemy treść.")
        data["text"] = text
        return data


class NeedForm(HoneypotMixin, forms.Form):
    """An institution describes what it is looking for; the radar then suggests matching innovations."""
    from analysis.core import PATHS as _PATHS
    from analysis.rules import SECTORS as _SECTORS
    from matching.models import Recipient as _R
    name = forms.CharField(label="Instytucja, firma lub imię (osoba prywatna)", max_length=200)
    institution_type = forms.ChoiceField(label="Typ instytucji", choices=_R.TYPES)
    from analysis.regions import CHOICES as _REGIONS
    region = forms.ChoiceField(label="Województwo", required=False,
                               choices=[("", "cała Polska / bez znaczenia")] + _REGIONS,
                               help_text="Innowacje z tego województwa dostają dodatkowy punkt dopasowania.")
    needs = forms.CharField(label="Czego szukacie? Opisz problem lub potrzebę", max_length=3000,
                            widget=forms.Textarea(attrs={"rows": 5}))
    tags = forms.CharField(label="Słowa kluczowe (po przecinku)", max_length=500,
                           help_text="np. „odpady, energia, oświetlenie” — wystarczą początki słów.")
    sectors = forms.MultipleChoiceField(label="Obszary", required=False, widget=forms.CheckboxSelectMultiple,
                                        choices=[(k, k) for k in _SECTORS])
    paths = forms.MultipleChoiceField(label="Czego oczekujecie", required=False, widget=forms.CheckboxSelectMultiple,
                                      choices=list(_PATHS.items()))
    contact = forms.CharField(label="Kontakt (e-mail lub telefon, opcjonalnie)", max_length=200, required=False)
    consent = forms.BooleanField(label="Zgadzam się na przetwarzanie podanego kontaktu wyłącznie w celu przekazania "
                                       "informacji o pasujących innowacjach (RODO, art. 6 ust. 1 lit. a).", required=False)
    strona_www = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
                                 label="Nie wypełniaj tego pola")

    def clean(self):
        data = super().clean()
        if data.get("contact") and not data.get("consent"):
            raise forms.ValidationError("Aby zapisać kontakt, zaznacz zgodę na jego przetwarzanie albo usuń kontakt.")
        if not data.get("sectors") and not (data.get("tags") or "").strip():
            raise forms.ValidationError("Podaj słowa kluczowe lub zaznacz co najmniej jeden obszar.")
        return data
