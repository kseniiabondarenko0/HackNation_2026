# V0.1 — weryfikacja działania

Data: 21.11.2026, 13:12 Europe/Warsaw. Środowisko: Windows, Docker Compose, Python 3.12, Django 5.1.15. Bez płatnych API.

## Wynik

Web jest zdrowy, worker działa w tle. Pierwsze źródła powstały automatycznie podczas startu. Kolektor sam pobrał 19 publikacji i zapisał ich tekst w trwałej bazie SQLite.

| Źródło | Pierwszy zakończony przebieg | Linki | Nowe / pobrane | Błędy |
|---|---|---:|---:|---:|
| PWr — Aktualności | 13:05:43–13:06:05 | 8 | 8 / 8 | 0 |
| UR — Aktualności | 13:07:14–13:07:44 | 11 | 11 / 11 | 0 |

Przy aktualizacji kontenerów pierwszy przebieg UR został przerwany. Historia zachowała status „Przerwany”, blokada została zwolniona, a nowy worker automatycznie powtórzył pracę. Nie usuwano bazy ani wolumenu.

Po zleceniu wcześniejszego terminu w harmonogramie oba źródła ponownie sprawdził **worker**, bez ręcznego uruchamiania komendy zbierania:

| Źródło | Powtórny przebieg | Linki | Nowe | Błędy |
|---|---|---:|---:|---:|
| PWr | 13:10:07–13:10:10 | 8 | 0 | 0 |
| UR | 13:10:10–13:10:12 | 11 | 0 | 0 |

Po powtórzeniu pozostało 19 rekordów, 19 pobranych tekstów, 0 duplikatów i 0 zapisanych błędów artykułów. Deduplikację identycznego tekstu pod różnymi URL dodatkowo sprawdzają testy offline.

## Jakość treści

Weryfikacja w przeglądarce ujawniła wspólny blok promocyjny PWr dopisywany do tekstów. Dodano adapter oddzielający główny artykuł od bocznych bloków, z zachowaniem metadanych. Osiem istniejących tekstów PWr ponownie wyodrębniono bez tworzenia nowych rekordów. Dwa przejściowe ConnectTimeout podczas tej operacji ustąpiły po ponowieniu. W końcowym stanie nie pozostały błędy.

Sprawdzono pełny tekst publikacji o betonie z PET: bez wspólnej reklamy, z datą publikacji i odnośnikiem do oryginału. Zebrane publikacje mogą dotyczyć zwykłych wydarzeń; ich ocena jako potencjalnych innowacji należy do V0.2.

## Kontrole

- `python manage.py test tests --noinput`: **28 testów, OK**. Testy uruchomiono w izolowanej bazie przez kontener z aktualnymi plikami projektu. Ostrzeżenie o katalogu staticfiles dotyczyło montowanego katalogu testowego; uruchomienie web wykonuje collectstatic.
- `python manage.py check`: brak problemów.
- `python manage.py makemigrations --check --dry-run`: brak brakujących migracji.
- `pip check`: brak konfliktów zależności.
- `/`, `/zrodla/`, `/przebiegi/`, `/a/5/`, `/health/`, `/api/status/`: HTTP 200.
- W przeglądarce sprawdzono listę, wyszukiwanie, pełny tekst, harmonogram oraz tabelę historii; układ historii sprawdzono wizualnie.

Testy obejmują m.in. HTML/RSS/sitemap, indeks sitemap, URL i hash tekstu, kolejkę zaległych adresów, ponowną kontrolę, awarie parsowania, blokady współbieżności, przerwanie procesu, robots.txt, zachowanie starego tekstu i daty przy błędzie oraz uprawnienia do zlecania zbierania.

## Dalsza praca kolektora

Źródła mają interwał 60 minut, worker sprawdza terminy co 15 sekund. Następne sprawdzenia po próbie: około **14:10 Europe/Warsaw**. Zbieranie wymaga uruchomionego komputera, Docker i obu kontenerów. Podczas wyłączenia komputera kolektor nie pracuje; po uruchomieniu podejmie zaległe terminy.

V0.1 realizuje kolekcję ze skonfigurowanych publicznych źródeł. Analiza AI, ocena potencjału, rekomendacje rozwoju i wyszukiwanie podobnych rozwiązań pozostają kolejnym etapem. Ollama nie była wymagana ani benchmarkowana w tej weryfikacji.
