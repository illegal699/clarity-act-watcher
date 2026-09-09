# CLARITY Act Vote Watcher

Automatycznie sledzi glosowanie w Senacie USA nad **H.R. 3633 (Digital Asset
Market Clarity Act)** i wysyla powiadomienia na Telegram: kiedy glosowanie sie
zaczyna, na biezaco w trakcie (zmiana licznika Tak/Nie) oraz wynik koncowy.

Kontekst (stan na wrzesien 2026): 15 wrzesnia 2026 ok. **14:15 czasu
wschodniego USA (20:15 czasu polskiego)** ma odbyc sie glosowanie nad cloture
(zamknieciem debaty) na motion to proceed do H.R. 3633 - wymaga 60 glosow.
To NIE jest jeszcze finalne glosowanie nad ustawa, tylko krok proceduralny
otwierajacy debate. Skrypt wykryje **kazde** glosowanie zwiazane z HR 3633 w
biezacej sesji Senatu (rowniez ewentualne pozniejsze glosowanie finalne), bo
dopasowuje po numerze ustawy, a nie po konkretnym numerze roll-call.

Zrodlo danych: publiczne pliki XML Senate.gov (Legislative Information
System) - brak potrzeby klucza API.

## 1. Stworz bota Telegram

1. W Telegramie napisz do **@BotFather** -> `/newbot` -> nadaj nazwe.
2. Zapisz **token** bota (wyglada jak `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxx`).
3. Napisz cokolwiek do swojego nowego bota (musi miec z Toba otwarty czat).
4. W przegladarce wejdz na:
   `https://api.telegram.org/bot<TWOJ_TOKEN>/getUpdates`
   i znajdz w odpowiedzi `"chat":{"id":123456789,...}` - to jest Twoj
   `chat_id`.

## 2. Wrzuc ten folder na GitHub

Zalecane: **publiczne** repozytorium - wtedy GitHub Actions jest calkowicie
bezplatne bez limitu minut (na prywatnym repo darmowy plan ma limit 2000
min/miesiac, co przy pollingu co 15 min moze byc ciasne). `state.json` nie
zawiera zadnych sekretow, wiec bycie publicznym jest bezpieczne.

```bash
cd clarity-act-watcher
git init
git add .
git commit -m "Initial commit: CLARITY Act vote watcher"
git branch -M main
git remote add origin https://github.com/<TWOJ_LOGIN>/clarity-act-watcher.git
git push -u origin main
```

(Najpierw utworz puste repo o tej nazwie na github.com/new.)

## 3. Dodaj sekrety w repo

W repo na GitHub: **Settings -> Secrets and variables -> Actions -> New
repository secret**, dodaj dwa sekrety:

- `TELEGRAM_BOT_TOKEN` - token z kroku 1
- `TELEGRAM_CHAT_ID` - Twoj chat_id z kroku 1

## 4. Test

Zakladka **Actions** w repo -> wybierz workflow "CLARITY Act Vote Watcher" ->
**Run workflow** (recznie), zeby sprawdzic, czy wszystko dziala (dopoki nie ma
jeszcze pasujacego glosowania, dostaniesz w logach "Brak pasujacych glosowan
na razie" - to normalne, oznacza ze polaczenie z Senate.gov i logika dzialaja).

Po tym workflow uruchamia sie sam co 15 minut (`schedule` w
`.github/workflows/watch.yml`). Gdy wykryje glosowanie zwiazane z HR 3633,
przez do 25 minut w ramach jednego uruchomienia bedzie odpytywac Senate.gov co
~25 sekund i wysylac aktualizacje na Telegram, az pojawi sie wynik koncowy.

## Znane ryzyko: senate.gov/congress.gov moga blokowac ruch spoza USA

Test polaczenia z Polski (zwykle domowe/komorkowe IP, nie serwerownia) zwrocil
**HTTP 403 Forbidden** zarowno z `curl`, jak i z Pythona, z i bez naglowkow
udajacych przegladarke. To wskazuje na **geoblokade USA-only** po stronie
tych serwisow rzadowych (dosc powszechna praktyka na stronach .gov), a nie na
blokade botow po samych naglowkach.

To oznacza:

- **Uruchomienie lokalnie w Polsce prawdopodobnie nigdy nie zadziala** -
  zawsze bedziesz laczyc sie z polskiego IP. Nie warto tego probowac jako
  planu B.
- **GitHub Actions ma sens jako plan A** (tak jak juz skonfigurowano ponizej) -
  jego runnery zwykle dzialaja z adresow w USA, wiec powinny ominac ten
  konkretny blok. Nie da sie tego potwierdzic z gory bez dostepu do
  amerykanskiego IP - **jedyny pewny test to krok 4 (Run workflow)**.

**Jesli krok 4 tez zwroci `HTTP Error 403: Forbidden`** - to sygnal, ze blok
nie jest (tylko) geograficzny, tylko ogolny anty-bot niezalezny od lokalizacji.
W takim wypadku potrzebny bylby inny zrodlo danych (np. oficjalne API
congress.gov z kluczem, ktore bywa mniej restrykcyjne niz strona HTML, albo
zewnetrzny agregator typu GovTrack/ProPublica) - daj znac, dopisze to wtedy.

## Dostrajanie

- `LIVE_POLL_INTERVAL_SECONDS` / `LIVE_POLL_BUDGET_SECONDS` w
  [watch_vote.py](watch_vote.py) - czestotliwosc i dlugosc "zywego" pollingu.
- `cron` w [watch.yml](.github/workflows/watch.yml) - jak czesto sprawdzac,
  czy jakies nowe glosowanie sie pojawilo (GitHub nie pozwala czesciej niz co
  5 min, i moze opozniac uruchomienia przy duzym obciazeniu serwisu - dlatego
  faktyczna "zywosc" w trakcie glosowania zapewnia wewnetrzna petla w
  skrypcie, nie sama czestotliwosc crona).
- `KEYWORDS` w watch_vote.py - slowa/numery po ktorych rozpoznawane jest
  glosowanie na liscie Senatu.
