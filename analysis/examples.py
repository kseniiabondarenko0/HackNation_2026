"""Labeled examples for the 'interesting innovation' filter (synthetic, styled on PWr/UR news).

label: True = should reach the main list or human review (an innovation worth a look),
       False = should be rejected (event, award, admin news, research without a solution).
"""

EXAMPLES = [
    # --- interesting (True) ---
    dict(id="beton-pet", label=True, title="Beton z odpadów PET",
         text="Naukowcy z Politechniki Wrocławskiej opracowali nowy beton z dodatkiem rozdrobnionych butelek PET. "
              "Problemem gmin jest składowanie odpadów tworzyw sztucznych, których przybywa co roku. "
              "Materiał przetestowano na odcinku chodnika w warunkach rzeczywistych przez 12 miesięcy. "
              "Wytrzymałość wzrosła o 15%, a koszt produkcji spadł o 10% w porównaniu z tradycyjnym betonem. "
              "Rozwiązanie jest skalowalne i może trafić do innych gmin. "
              "Autorem pomysłu jest dr inż. Jan Kowalski z Wydziału Budownictwa."),
    dict(id="biopreparat", label=True, title="Biopreparat chroni uprawy przed grzybami",
         text="Zespół z Uniwersytetu Rzeszowskiego opracował biopreparat, który chroni uprawy ziemniaka przed chorobami grzybowymi. "
              "Rolnicy od lat zmagają się z problemem odporności patogenów na środki chemiczne. "
              "Preparat był testowany w pilotażu w trzech gospodarstwach na Podkarpaciu. "
              "Wyniki pokazują zmniejszenie strat plonu o 30% przy niższym zużyciu fungicydów. "
              "Uczelnia złożyła zgłoszenie patentowe i prowadzi rozmowy licencyjne z producentem. "
              "Kierownikiem projektu jest prof. dr hab. Anna Nowak."),
    dict(id="czujnik-sepsy", label=True, title="Czujnik wykrywa sepsę w kilka minut",
         text="Badacze PWr skonstruowali czujnik, który pozwala wykryć sepsę u pacjentów w ciągu 15 minut. "
              "Szybka diagnoza jest dużym wyzwaniem dla szpitali, bo standardowe badania trwają nawet 48 godzin. "
              "Urządzenie przetestowano we współpracy ze szpitalem klinicznym na próbkach od pacjentów. "
              "Dokładność wyniosła 92%, a czas diagnozy skrócił się wielokrotnie. "
              "Technologię można przenieść do innych szpitali, a zainteresowanie wyraził inwestor z branży medycznej. "
              "Pracami kieruje Dr inż. Marta Wiśniewska."),
    dict(id="aplikacja-gmina", label=True, title="Aplikacja do zgłaszania usterek w gminie",
         text="W gminie Tyczyn wdrożono aplikację, która umożliwia mieszkańcom zgłaszanie usterek oświetlenia i dróg. "
              "Wcześniej problemem był długi czas reakcji urzędu na zgłoszenia telefoniczne. "
              "System jest już stosowany od roku i obsłużył ponad 1200 zgłoszeń. "
              "Średni czas naprawy skrócił się o 40%. "
              "Rozwiązanie zostało wdrożone w kolejnych dwóch gminach regionu."),
    dict(id="lazik", label=True, title="Studenci zbudowali łazik marsjański",
         text="Studenci z koła naukowego PWr zbudowali prototyp łazika, który samodzielnie pobiera próbki gruntu. "
              "Robot wykorzystuje autorski algorytm nawigacji opracowany przez zespół. "
              "Prototyp przetestowano w laboratorium i na torze testowym uczelni. "
              "Zespół planuje udoskonalić system chwytaka przed kolejnymi testami w terenie."),
    dict(id="odzysk-ciepla", label=True, title="Odzysk ciepła ze ścieków",
         text="Inżynierowie z Rzeszowa zaprojektowali instalację, która odzyskuje ciepło ze ścieków w budynkach wielorodzinnych. "
              "Rosnące koszty ogrzewania są problemem dla spółdzielni mieszkaniowych. "
              "Instalacja działa od marca w pilotażu w jednym budynku. "
              "Pomiary pokazują oszczędność energii na poziomie 25%. "
              "Rozwiązanie jest uniwersalne i można je zastosować w innych budynkach."),
    dict(id="ai-rtg", label=True, title="Algorytm AI wspiera analizę zdjęć RTG",
         text="Naukowcy opracowali algorytm sztucznej inteligencji, który analizuje zdjęcia RTG płuc. "
              "Lekarze radiolodzy są przeciążeni, a kolejki do opisu badań wydłużają się. "
              "Model został zweryfikowany na 5000 zdjęć z dwóch szpitali. "
              "Czułość wykrywania zmian wyniosła 94%, a czas opisu skrócił się o połowę. "
              "Zespół prowadzi rozmowy o licencji z firmą medyczną."),
    dict(id="koncepcja-powietrze", label=True, title="Koncepcja sieci czujników powietrza",
         text="Zespół z UR przygotował koncepcję systemu monitorowania jakości powietrza w szkołach. "
              "Problemem jest brak danych o stężeniu pyłów w salach lekcyjnych. "
              "System ma wykorzystywać tanie czujniki i aplikację dla nauczycieli. "
              "Autorzy planują zbudować prototyp w przyszłym roku."),
    dict(id="nagroda-wynalazek", label=True, title="Złoty medal dla wynalazku z PWr",
         text="Wynalazek naukowców PWr zdobył złoty medal na targach innowacji w Genewie. "
              "Nagrodzony system to urządzenie, które umożliwia bezinwazyjny pomiar poziomu cukru we krwi. "
              "Urządzenie przetestowano na grupie 60 pacjentów z cukrzycą w poradni diabetologicznej. "
              "Błąd pomiaru był mniejszy niż 8%. "
              "Rozwiązanie jest objęte zgłoszeniem patentowym."),
    # --- not interesting (False) ---
    # --- interesting, non-technological (task: organisational, educational, social, process innovations) ---
    dict(id="szkola-matematyka", label=True, title="Nowa metoda nauczania matematyki w SP 3",
         text="Nauczyciele Szkoły Podstawowej nr 3 w Krośnie wprowadzili autorski program nauczania matematyki przez gry terenowe. "
              "Problemem był niski wynik uczniów z egzaminu ósmoklasisty. "
              "Program prowadzono przez dwa lata w czterech klasach. Średni wynik z matematyki wzrósł o 18%. "
              "Materiały udostępniono innym szkołom w powiecie, które mogą wdrożyć program bez dodatkowych kosztów."),
    dict(id="gmina-decyzje", label=True, title="Gmina skróciła czas wydawania decyzji",
         text="Urząd Gminy Jasło wprowadził nowy sposób obsługi wniosków budowlanych: jeden urzędnik prowadzi sprawę od początku do końca, "
              "a mieszkańcy śledzą jej status online. Wcześniej mieszkańcy czekali średnio 45 dni. "
              "Po roku czas wydania decyzji skrócił się do 21 dni. Rozwiązanie zostało już przejęte przez dwie sąsiednie gminy."),
    dict(id="mops-seniorzy", label=True, title="Senioralna sieć wsparcia",
         text="Miejski Ośrodek Pomocy Społecznej w Sanoku uruchomił program, w którym wolontariusze-studenci raz w tygodniu odwiedzają "
              "samotnych seniorów. Problemem była izolacja osób starszych. W pilotażu wzięło udział 60 seniorów, "
              "liczba interwencji pogotowia spadła o 25%. Program można przenieść do innych miast."),
    dict(id="szpital-kolejka", label=True, title="Szpital zmienił organizację przyjęć",
         text="Szpital powiatowy w Mielcu zreorganizował izbę przyjęć: pielęgniarka koordynująca wstępnie ocenia pacjentów "
              "i kieruje ich do właściwej ścieżki. Celem było rozwiązanie problemu wielogodzinnych kolejek. "
              "Nowa procedura funkcjonuje od marca, średni czas oczekiwania skrócił się z 5 do 2 godzin. "
              "Model pracy opisano w poradniku, który udostępniono innym szpitalom w regionie."),
    dict(id="przedszkole-dwujezyczne", label=True, title="Przedszkole uczy przez projekty",
         text="Przedszkole Miejskie nr 2 w Jarosławiu przygotowało program edukacji przez projekty badawcze dla dzieci 5-letnich. "
              "Dzieci pracują w grupach nad pytaniami, które same zadają, a nauczyciele dokumentują postępy. "
              "Program prowadzono przez rok w trzech grupach, a rodzice ocenili zajęcia lepiej niż wcześniejsze o 30%. "
              "Scenariusze zajęć są dostępne bezpłatnie dla innych przedszkoli."),
    # --- not interesting: school / local government news without a solution ---
    dict(id="dozynki", label=False, title="Dożynki gminne 2026",
         text="Wójt Gminy zaprasza wszystkich mieszkańców na dożynki gminne, które odbędą się w niedzielę na stadionie. "
              "W programie msza, korowód wieńców, koncert zespołu ludowego i loteria fantowa. Wstęp wolny."),
    dict(id="konkurs-recytatorski", label=False, title="Wyniki konkursu recytatorskiego",
         text="Uczniowie naszej szkoły zdobyli wyróżnienia w powiatowym konkursie recytatorskim. "
              "Gratulujemy laureatom i dziękujemy nauczycielom za przygotowanie uczniów. Dyplomy wręczono podczas apelu."),
    dict(id="remont-drogi", label=False, title="Zakończono remont drogi gminnej",
         text="Zakończono remont drogi gminnej w miejscowości Wola. Wykonawca położył nową nawierzchnię asfaltową na odcinku 1,2 km. "
              "Inwestycja kosztowała 800 tys. zł i została sfinansowana z budżetu gminy."),
    dict(id="sesja-rady", label=False, title="Sesja Rady Gminy",
         text="Informujemy, że kolejna sesja Rady Gminy odbędzie się w czwartek o godzinie 10:00 w sali konferencyjnej urzędu. "
              "W porządku obrad: zmiany w budżecie, uchwała w sprawie opłat za odpady oraz sprawozdanie wójta."),
    dict(id="zbiorka", label=False, title="Szkolna zbiórka dla schroniska",
         text="Samorząd uczniowski organizuje zbiórkę karmy i koców dla schroniska dla zwierząt. "
              "Dary można przynosić do biblioteki szkolnej do końca miesiąca. Zachęcamy do udziału całe rodziny."),
    dict(id="inauguracja", label=False, title="Inauguracja roku akademickiego",
         text="W poniedziałek odbyła się uroczysta inauguracja roku akademickiego. "
              "Rektor powitał studentów pierwszego roku i wręczył indeksy najlepszym kandydatom. "
              "Wykład inauguracyjny wygłosił profesor z Wydziału Chemii. "
              "Uroczystość uświetnił koncert chóru akademickiego."),
    dict(id="dzien-otwarty", label=False, title="Dzień otwarty uczelni",
         text="Zapraszamy uczniów szkół średnich na dzień otwarty uczelni. "
              "Na kandydatów czekają pokazy w laboratoriach, spotkania ze studentami i informacje o rekrutacji. "
              "Wstęp wolny, rejestracja na stronie wydziału."),
    dict(id="wybory-rektora", label=False, title="Wybory rektora",
         text="Kolegium elektorów wybrało nowego rektora uczelni na kadencję 2028-2032. "
              "Nowy rektor zapowiedział rozwój współpracy z przemysłem i wsparcie dla młodych naukowców. "
              "Senat uczelni pogratulował wyboru."),
    dict(id="stypendia", label=False, title="Stypendia ministra dla studentów",
         text="Pięcioro studentów otrzymało stypendia ministra za wybitne osiągnięcia. "
              "Laureaci zostali wyróżnieni za wyniki w nauce i działalność w kołach naukowych. "
              "Gratulujemy wszystkim nagrodzonym."),
    dict(id="konferencja", label=False, title="Konferencja o energetyce",
         text="Na uczelni odbyła się międzynarodowa konferencja poświęcona transformacji energetycznej. "
              "W konferencji wzięło udział 200 uczestników z 15 krajów. "
              "Dyskutowano o wyzwaniach związanych z odnawialnymi źródłami energii. "
              "Organizatorzy zapraszają na kolejną edycję w przyszłym roku."),
    dict(id="grant-badania", label=False, title="Grant na badania podstawowe",
         text="Naukowczyni z UR otrzymała grant Narodowego Centrum Nauki na badania nad białkami roślin. "
              "Projekt potrwa trzy lata, a jego budżet wynosi 1,2 mln zł. "
              "Celem badań jest lepsze poznanie mechanizmów odporności roślin na suszę."),
    dict(id="ranking", label=False, title="Uczelnia awansowała w rankingu",
         text="Politechnika awansowała o 12 miejsc w rankingu szkół wyższych. "
              "Wyższą pozycję zawdzięcza wzrostowi liczby publikacji i umiędzynarodowieniu kadry. "
              "Ranking jest publikowany co roku."),
    dict(id="warsztaty", label=False, title="Warsztaty z programowania dla dzieci",
         text="Wydział Informatyki zaprasza dzieci na warsztaty z programowania robotów. "
              "Zajęcia poprowadzą studenci, a zapisy trwają do końca miesiąca. "
              "Uczestnicy poznają podstawy algorytmów i zbudują proste konstrukcje z klocków."),
    dict(id="remont", label=False, title="Remont biblioteki",
         text="Biblioteka główna będzie zamknięta od 1 do 14 grudnia z powodu remontu. "
              "W tym czasie zwroty książek przyjmuje czytelnia wydziałowa. "
              "Przepraszamy za utrudnienia."),
    dict(id="raport-rynek-pracy", label=False, title="Raport o rynku pracy",
         text="Eksperci uczelni opracowali raport o sytuacji na rynku pracy w regionie. "
              "Dokument pokazuje, że firmom brakuje specjalistów IT, a liczba ofert wzrosła o 18%. "
              "Autorzy analizują też potrzeby pracodawców z branży przemysłowej. "
              "Raport zostanie przedstawiony podczas konferencji w grudniu."),
]
