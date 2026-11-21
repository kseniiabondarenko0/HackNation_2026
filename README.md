# Radar Innowacji — V0.1 (kolektor)
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate && python manage.py createsuperuser
python manage.py seed_sources            # 2 kandydatów: PWr, UR — zweryfikuj discovery_type w /admin
python manage.py collect_sources --once --all
python manage.py runserver               # http://127.0.0.1:8000
python manage.py test tests              # 10 testów offline (fixtures)
```
Worker ciągły: `caffeinate -i python manage.py collect_sources` (pętla wg next_run_at).

## Docker
```
cp .env.example .env            # ustaw DJANGO_SECRET_KEY
docker compose up --build       # web :8000 + worker (kolektor w pętli)
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_sources
```
Ollama działa na Macu (nie w kontenerze): `OLLAMA_URL=http://host.docker.internal:11434`. Dane SQLite w wolumenie `radar-data`.
