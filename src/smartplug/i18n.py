"""Tiny translation layer. Source strings are English; `_()` returns the
translation for the current language (currently English and Ukrainian).

Usage:  _("Voltage")  ->  "Напруга" when the language is "uk".
        _("{n} min", n=5)  -> placeholders are filled after translating.
"""

from __future__ import annotations

LANGUAGES: dict[str, str] = {"en": "English", "uk": "Українська"}
DEFAULT_LANGUAGE = "en"

_current = DEFAULT_LANGUAGE

UK: dict[str, str] = {
    # window / top bar
    "SmartPlug — smart plug monitor": "SmartPlug — монітор розетки",
    " [DEMO]": " [ДЕМО]",
    "Period:": "Період:",
    "⟳ Refresh": "⟳ Оновити",
    "⚙ Settings": "⚙ Налаштування",
    "Language:": "Мова:",
    "No device selected": "Пристрій не вибрано",
    "1 hour": "1 година",
    "6 hours": "6 годин",
    "24 hours": "24 години",
    "7 days": "7 днів",
    "30 days": "30 днів",
    # cards
    "Power at home": "Електрика вдома",
    "Plug": "Розетка",
    "Power": "Потужність",
    "Voltage": "Напруга",
    "Current": "Струм",
    "Energy for period": "Енергія за період",
    "Yes ✓": "Є ✓",
    "plug is online": "розетка на зв'язку",
    "Offline": "Offline",
    "maybe no electricity": "можливо, немає світла",
    "no connection for {d}": "немає зв'язку {d}",
    "On": "Увімкнена",
    "Off": "Вимкнена",
    "relay not found": "реле не знайдено",
    "Turn off": "Вимкнути",
    "Turn on": "Увімкнути",
    "No connection": "Немає зв'язку",
    "out of range": "поза нормою",
    "plug without metering": "розетка без вимірювання",
    "W": "Вт",
    "V": "В",
    "A": "А",
    "kWh": "кВт·год",
    # charts
    "Power ({unit})": "Потужність ({unit})",
    # stats
    "<b>Voltage:</b> min {mn:.0f} V · avg {avg:.0f} V · max {mx:.0f} V":
        "<b>Напруга:</b> мін {mn:.0f} В · сер {avg:.0f} В · макс {mx:.0f} В",
    "<b>Power:</b> avg {avg:.0f} W · peak {mx:.0f} W":
        "<b>Потужність:</b> сер {avg:.0f} Вт · пік {mx:.0f} Вт",
    "<b>Online:</b> {pct:.0f}% of the time": "<b>На зв'язку:</b> {pct:.0f}% часу",
    "<b>Outages:</b> {o} · <b>voltage events:</b> {d}":
        "<b>Відключень:</b> {o} · <b>стрибків напруги:</b> {d}",
    "No data for this period yet — history builds up while the app is running.":
        "Ще немає даних за цей період — історія накопичується, поки програма працює.",
    # events table
    "Start": "Початок",
    "Duration": "Тривалість",
    "Event": "Подія",
    "Value": "Значення",
    " (ongoing)": " (триває)",
    "Plug offline (maybe no electricity)": "Розетка offline (можливо, немає світла)",
    "Voltage dip": "Просідання напруги",
    "Overvoltage": "Підвищена напруга",
    # status bar
    "Updating…": "Оновлення…",
    "Updated at {t} · next in {s} s": "Оновлено о {t} · наступне через {s} с",
    "Sending command…": "Надсилаю команду…",
    "Open ⚙ Settings and paste the keys from iot.tuya.com":
        "Відкрий ⚙ Налаштування і встав ключі з iot.tuya.com",
    # tray
    "Open": "Відкрити",
    "Quit": "Вийти",
    "Running in the tray. To quit: right-click the icon → Quit.":
        "Працюю у треї. Вийти: ПКМ на іконці → Вийти.",
    "Plug offline — maybe no electricity": "Розетка offline — можливо, немає світла",
    "Power OK · {p} · {v}": "Світло є · {p} · {v}",
    # switch confirmation
    "Turn on the plug “{name}”?": "Увімкнути розетку «{name}»?",
    "Turn off the plug “{name}”?": "Вимкнути розетку «{name}»?",
    "\n\nEverything connected to it will lose power.":
        "\n\nВсе, що підключено до розетки, знеструмиться.",
    "plug": "розетка",
    # notices
    "⚠️ Plug is offline": "⚠️ Розетка не на зв'язку",
    "Electricity or internet at home may be down.": "Можливо, вдома зникло світло або інтернет.",
    "✅ Plug is back online": "✅ Розетка знову online",
    "It was offline for {d}.": "Не було зв'язку {d}.",
    "⚡ Voltage dip": "⚡ Просідання напруги",
    "{v:.0f} V (normal from {lim:.0f} V).": "{v:.0f} В (норма від {lim:.0f} В).",
    "⚡ Overvoltage": "⚡ Підвищена напруга",
    "{v:.0f} V (normal up to {lim:.0f} V).": "{v:.0f} В (норма до {lim:.0f} В).",
    # durations
    "{h} h {m} min": "{h} год {m} хв",
    "{m} min {s} s": "{m} хв {s} с",
    "{s} s": "{s} с",
    # devices
    "Power strip": "Подовжувач",
    "Switch": "Вимикач",
    "Breaker": "Автомат",
    "Device": "Пристрій",
    "online": "online",
    "offline": "offline",
    "Demo plug": "Демо-розетка",
    # cloud errors
    "Access ID or Access Secret is missing": "Не вказано Access ID або Access Secret",
    "Could not sign in to Tuya Cloud: {err}. Check the keys and the data center.":
        "Не вдалося авторизуватися в Tuya Cloud: {err}. Перевір ключі та регіон дата-центру.",
    "no response from Tuya Cloud": "немає відповіді від Tuya Cloud",
    "Network error: {err}": "Помилка мережі: {err}",
    "The device has no controllable relay (switch_1)":
        "Пристрій не має керованого реле (switch_1)",
    "Unexpected error: {err}": "Неочікувана помилка: {err}",
    "Could not switch: {err}": "Не вдалося перемкнути: {err}",
    # settings dialog
    "Settings — SmartPlug": "Налаштування — SmartPlug",
    "<b>Where to get the keys:</b> iot.tuya.com → Cloud → Development → Create Cloud Project "
    "(Data Center: <i>Central Europe</i>) → Devices → Link App Account → scan the QR code "
    "in Smart Life (Me → scanner icon). Access ID and Access Secret are on the project's "
    "Overview tab.<br>The keys are stored only on this computer in "
    "~/.config/smartplug/config.json (mode 600).":
        "<b>Де взяти ключі:</b> iot.tuya.com → Cloud → Development → Create Cloud Project "
        "(Data Center: <i>Central Europe</i>) → Devices → Link App Account → відскануй QR "
        "у Smart Life (Я → значок сканера). Access ID та Access Secret — на вкладці Overview "
        "проєкту.<br>Ключі зберігаються лише на цьому комп'ютері у "
        "~/.config/smartplug/config.json (права 600).",
    "e.g. 7xk3...": "наприклад, 7xk3...",
    "Show / hide": "Показати / сховати",
    "Connect and find devices": "Підключитись і знайти пристрої",
    "How often to ask the cloud. More often = more API requests.":
        "Як часто питати хмару. Частіше = більше запитів до API.",
    " s": " с",
    " V": " В",
    "Ask for confirmation before switching": "Питати підтвердження перед перемиканням",
    "Notify about outages and voltage problems": "Сповіщення про відключення та стрибки напруги",
    "Data center:": "Дата-центр:",
    "Device:": "Пристрій:",
    "Poll every:": "Опитувати кожні:",
    "Nominal voltage:": "Номінальна напруга:",
    "Allowed deviation:": "Допустиме відхилення:",
    "Connected, but no devices found. Make sure the Smart Life account is linked to the "
    "project (Devices → Link App Account) and the right data center is selected.":
        "Підключення є, але пристроїв не знайдено. Перевір, що акаунт Smart Life прив'язаний "
        "до проєкту (Devices → Link App Account) і вибрано правильний дата-центр.",
    "Enter the Access ID and Access Secret.": "Вкажи Access ID та Access Secret.",
    "Click “Connect and find devices” and choose the plug.":
        "Натисни «Підключитись і знайти пристрої» і вибери розетку.",
    # regions
    "Central Europe": "Центральна Європа",
    "Western Europe": "Західна Європа",
    "Western America": "Західна Америка",
    "Eastern America": "Східна Америка",
    "India": "Індія",
    "Singapore": "Сінгапур",
    "China": "Китай",
    # cli
    "Monitor and control a Tuya / Smart Life smart plug":
        "Монітор і керування розумною розеткою Tuya / Smart Life",
    "simulated plug, no keys needed": "симульована розетка, ключі не потрібні",
    "poll interval in seconds (this run only)": "інтервал опитування в секундах (для цього запуску)",
    "interface language": "мова інтерфейсу",
}

_CATALOGS = {"uk": UK}


def set_language(lang: str | None) -> str:
    global _current
    _current = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
    return _current


def get_language() -> str:
    return _current


def _(text: str, **kw) -> str:
    out = _CATALOGS.get(_current, {}).get(text, text)
    return out.format(**kw) if kw else out
