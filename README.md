# Radar Innowacji — V0.1: automatyczny kolektor

Działający etap zbierania publikacji z publicznych stron. Kolektor sam odnajduje adresy na skonfigurowanych stronach, pobiera tekst, zapisuje wyniki i powtarza sprawdzenie według harmonogramu. V0.1 zbiera publikacje; analiza AI i ocena potencjału innowacji są następnym etapem.

## Start w Windows PowerShell

```powershell
Set-Location "C:\Project\HackNation\radar"
# Tylko jeśli .env jeszcze nie istnieje:
Copy-Item .env.example .env
# Ustaw własny DJANGO_SECRET_KEY w .env.
docker compose up -d --build --wait
```

Przy kolejnym uruchomieniu zachowaj istniejący `.env`. Docker automatycznie wykonuje migracje, dodaje dwa początkowe źródła (PWr i UR), a następnie uruchamia web i kolektor. Istniejące ustawienia źródeł nie są nadpisywane.

- Publikacje: http://localhost:8000/
- Harmonogram i błędy źródeł: http://localhost:8000/zrodla/
- Historia rzeczywistych przebiegów: http://localhost:8000/przebiegi/
- Stan JSON: http://localhost:8000/api/status/

Pierwsze pobieranie trwa zwykle kilkadziesiąt sekund, zależnie od stron. Widok źródeł odświeża się co 30 sekund. Domyślny interwał źródła to 60 minut; worker sprawdza harmonogram co 15 sekund.

```powershell
docker compose ps
docker compose logs --tail=50 worker
docker compose exec web python manage.py createsuperuser
```

Zaloguj się w `/admin/`, aby dodawać/wyłączać źródła, zmieniać interwał i prefiks. Zalogowany administrator może też zlecić sprawdzenie na stronie źródeł. Przycisk zmienia harmonogram; pracę wykonuje worker.

## Ręczna kontrola i testy

```powershell
docker compose exec worker python manage.py collect_sources --once --all
docker compose exec web python manage.py test tests --noinput
docker compose exec web python manage.py check
```

`--all` pomija termin następnego sprawdzenia, ale respektuje blokadę trwającego przebiegu. Niedawno pobrane artykuły nie są ponownie ściągane. Znane artykuły trafiają do ponownej kontroli po 24 godzinach.

Aby zatrzymać: `docker compose stop`. Aby wrócić: `docker compose up -d`. Komputer i Docker muszą działać, aby zbieranie odbywało się automatycznie. Dane są w trwałym wolumenie `radar-data`.

## Mechanizmy i ograniczenia

- HTML-lista, RSS/Atom, sitemap i ograniczone indeksy sitemap.
- Reguły robots.txt, publiczne HTTP(S), kontrola adresów/redirectów, limit rozmiaru i czasu odpowiedzi.
- Jednoczesny drugi przebieg tego samego źródła jest blokowany. Po przerwaniu blokada wygasa; niedokończone adresy pozostają w bazie.
- Błąd parsowania jednej publikacji nie przerywa całego worker. Nieudane pobrania mają ograniczenie prób i opóźnienie ponowienia.
- Unikalność URL i identycznego tekstu, osobne daty publikacji/odkrycia/pobrania.
- `lastmod` sitemap nie jest datą publikacji.
- Pobieranie nie używa płatnego API. Nie jest to indeks całego internetu: działa w zakresie skonfigurowanych źródeł.
- PDF, skany, strony wymagające logowania/JS i semantyczne łączenie podobnych projektów pozostają poza V0.1.
- Ochrona URL to podstawowa warstwa dla lokalnego narzędzia; publiczne wdrożenie wymaga dodatkowej kontroli sieci, w tym ochrony przed DNS rebinding.

## Lokalnie bez kontenerów

Python 3.12+ i osobne dwa terminale. Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_sources
python manage.py runserver
# Drugi terminal z aktywnym tym samym środowiskiem:
python manage.py collect_sources
```

Przy lokalnym uruchomieniu plik `.env` nie jest automatycznie wczytywany przez Django: zmienne ustaw w środowisku terminala. Baza domyślnie powstaje w katalogu projektu. Docker jest zalecaną, sprawdzaną ścieżką uruchomienia.
