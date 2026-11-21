from django import forms

MIN_TEXT = 150


class SubmitForm(forms.Form):
    title = forms.CharField(label="Tytuł", max_length=300, required=False)
    url = forms.URLField(label="Adres strony z opisem (opcjonalnie)", max_length=800, required=False)
    text = forms.CharField(label="Opis rozwiązania", max_length=20000, required=False,
                           widget=forms.Textarea(attrs={"rows": 10}))

    def clean(self):
        data = super().clean()
        text, url = (data.get("text") or "").strip(), data.get("url")
        if not url and len(text) < MIN_TEXT:
            raise forms.ValidationError(
                f"Wklej opis (min. {MIN_TEXT} znaków) albo podaj adres strony, z której pobierzemy treść.")
        data["text"] = text
        return data
