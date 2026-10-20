# Test plan — شاشة تلفزيونك

For a tester (human or agent) with a Linux/macOS machine, `adb`, and an Android TV on the same network.
Every step has an exact action and the expected result. Record **PASS / FAIL + note + screenshot** for each ID.

Screenshots: `adb exec-out screencap -p > ID.png`
Logs on failure: `adb logcat -d -t 300 | grep -iE "urtv|chromium|AndroidRuntime" > ID.log`

---

## 0. Setup

| ID | Action | Expected |
|---|---|---|
| S1 | On the TV: Settings → Device preferences → About → press Build 7× → Developer options → enable **USB/Network debugging**. Note the TV's IP. | Debugging on |
| S2 | `adb connect <TV_IP>:5555` then `adb devices` | Device listed as `device` |
| S3 | `curl -L -o urtv-screensaver.apk https://github.com/tshi-dev/UrTV/releases/download/apk-latest/urtv-screensaver.apk` | ~2–5 MB file |
| S4 | `adb uninstall sa.yourtv.screensaver` and `adb uninstall com.abdullah.tvsaver` (ignore "not installed") | The pre-rename app is gone (it would show twice) |
| S5 | `adb install urtv-screensaver.apk` | `Success` |
| S6 | `adb shell dumpsys package sa.urtv.screensaver \| grep versionName` | `versionName=2.<number>` |

## 1. Settings screen

Open: `adb shell am start -n sa.urtv.screensaver/.SettingsActivity`
Navigate with the remote, or `adb shell input keyevent DPAD_DOWN|DPAD_UP|DPAD_CENTER|BACK`.

| ID | Action | Expected |
|---|---|---|
| A1 | Open the app from the TV launcher | Banner «شاشة تلفزيونك»; settings list opens, right-to-left, first row focused |
| A2 | Move through every row with D-pad | Every row focusable and highlighted; nothing unreachable |
| A3 | المدينة → open | First item «بحث عن مدينة أو قرية…», then 13 regions with counts |
| A4 | Region «منطقة الرياض» → pick «الخرج» | Dialog closes, row shows «المدينة: الخرج» |
| A5 | المدينة → search → type `ابها` or `Abha` | Results list from the internet; pick one → row updates |
| A6 | المدينة → search → type `zzzzqq` | Toast «لا توجد نتائج» |
| A7 | الفرق المتابعة → «تصفح الدوريات…» → each league one by one, and «المنتخبات» | Each opens at once, even offline, with every club of the last two seasons in Arabic (MLS: 30). **Record any league that is short or shows «لا توجد نتائج»** |
| A8 | الفرق المتابعة → «تصفح الدوريات…» → دوري روشن → pick «النصر» | Toast «تمت متابعة النصر» right away (no network needed), row shows «النصر» |
| A9 | الفرق المتابعة → «بحث عن أي فريق أو منتخب…» → `Real Madrid`, then `الاهلي`, `العين`, `atletico` | Results at once: «ريال مدريد»; the Saudi «الأهلي» first, then «الأهلي المصري»; the Saudi «العين» before «العين الإماراتي»; «أتلتيكو مدريد». Pick one → row shows its Arabic name |
| A10 | الفرق المتابعة → دوري يلو | Every club of the league, «الزلفي» among them |
| A11 | التصنيفات → tick دراما + كوميديا → حفظ | Row lists both |
| A12 | اللغات → tick الإنجليزية → حفظ | Row shows it |
| A13 | مسلسلات مختارة → «إضافة مسلسل» → `The Last of Us` → pick | Toast «تمت إضافة …», row lists the show (English title) |
| A14 | مسلسلات مختارة → untick it → حفظ | Removed |
| A15 | أقل تقييم → 8 | Row shows 8 |
| A16 | التحديث التلقائي → press | Toggles يعمل/متوقف; set back to يعمل |
| A17 | تحقق من التحديث الآن | Toast «تم التحديث» or «الصفحة محدثة» (not «لا يوجد اتصال») |
| A18 | إعدادات شاشة التوقف في التلفاز | TV screensaver settings open |
| A19 | Force-close and reopen: `adb shell am force-stop sa.urtv.screensaver` then A1 | All choices from A4–A15 kept |

## 2. Preview / screen content

Open: «معاينة الشاشة» row, or `adb shell am start -n sa.urtv.screensaver/.MainActivity`. Wait 60 s for data.

| ID | Check | Expected |
|---|---|---|
| B1 | Overall | Full screen, photo background, no white flash, no scrollbars, no cursor, all text Arabic except show titles and «S&P 500» |
| B2 | Clock | 12-hour Arabic digits, no two digits touching (e.g. ٤٨), gold colon, small gold ص/م at the **upper left**; centred between the card and the right edge; matches the real Riyadh time |
| B3 | Under clock | «بتوقيت <chosen city>» |
| B4 | Top right | Hijri date (with هـ) over Gregorian date (Gregorian month name, e.g. أكتوبر) |
| B5 | Top left (no boxes) | Temperature ° + condition word (or «غبار» in gold); city · high/low; gold line from the left edge; تاسي / S&P 500 / بيتكوين each with ▲ green or ▼ red (or no arrow — never a dash) |
| B6 | Markets accuracy | Compare arrows with today's TASI, S&P 500 and BTC 24h direction on any finance site |
| B7 | هذا الأسبوع | Up to 5 shows matching A11–A15 filters, with season/episode, rating, weekday. Changes page every 25 s |
| B7b | Settings → بجانب الساعة → each option, then preview | مواقيت الصلاة: 6 rows, next prayer gold, past ones dim · طقس الأيام القادمة: اليوم, غداً, then weekdays with condition and high/low · مباريات فرقك: every followed team's games this week in time order · آية أو حديث اليوم: a verse with surah and ayah, or a hadith with its source; no empty boxes · لا شيء: no card |
| B8 | الصلاة القادمة | Next prayer name + time + «بعد …». Compare with https://www.ummulqura.org.sa or the Aladhan site for the chosen city: within 1–2 min |
| B9 | رمضان panel | «رمضان ١٤٤٨», day count, start date. (In Ramadan: الإفطار/الإمساك instead) |
| B10 | المباريات | Team 1 on the right, team 2 on the left, side by side, divider between. Slot hidden if no match within 7 days. Both hidden → «لا شيء هذا الأسبوع» |
| B11 | Team names | Arabic for all clubs. A non-preset club may show a rough spelling for a few seconds, then the official Arabic name |
| B12 | No credit on screen | Photo credits are only in docs/PHOTO-CREDITS.md |
| B13 | Any remote key | Preview closes |
| B14 | Change city to جدة (A4/A5), reopen preview | Prayer times, weather and «بتوقيت جدة» change |

## 3. Time-based behaviour

Use the TV's clock or wait for the real moment; take a screenshot at each.

| ID | When | Expected |
|---|---|---|
| C1 | Within 25 min after any adhan (10 min after Maghrib) | Prayer panel glows gold: «حان الآن», prayer name, «الإقامة بعد … دقيقة» |
| C2 | Friday before Dhuhr | Prayer name «الجمعة»; no iqama countdown after it |
| C3 | Between 21:00 and 07:00 | Screen gradually dimmer; darkest 23:00–05:00 |
| C4 | During a live match of a chosen team | Score + «مباشر · الدقيقة …», updates within ~2 min of real goals |
| C5 | Within 24 h after that match | «النتيجة النهائية · <day>» with the final score |
| C6 | After midnight | New background photo; dates, prayers, shows refreshed |
| C7 | Leave it running 2+ hours | Text shifts a few pixels every 4 min (burn-in protection); no freeze; clock still correct |

## 4. Screensaver (dream)

| ID | Action | Expected |
|---|---|---|
| D1 | TV Settings → screensaver → choose «شاشة تلفزيونك», or `adb shell settings put secure screensaver_components sa.urtv.screensaver/.ScreenDream` | Selected |
| D2 | Start now: `adb shell am start -n "com.android.systemui/.Somnambulator"` (or wait for the idle timer) | The screen appears full screen |
| D3 | Press any remote key | Screensaver exits |
| D4 | Leave the TV idle for the timer set in TV settings | Starts by itself |

## 5. Offline

| ID | Action | Expected |
|---|---|---|
| E1 | Disconnect the TV from Wi-Fi/Ethernet, open preview | Clock, both dates, prayer countdown (computed on device), Ramadan panel all shown. Markets arrows hidden, no dash; weather shows only the city; no error text |
| E2 | Reconnect, wait 2 min, reopen | Live data returns |

## 6. Auto-update

| ID | Action | Expected |
|---|---|---|
| F1 | Press A17 twice in a row | First «تم التحديث», second «الصفحة محدثة» (the page is cached and unchanged) |
| F2 | Ask the developer to push a visible change (or note the latest commit), then A17 | Toast «تم التحديث»; preview shows the change |
| F3 | `adb shell dumpsys jobscheduler \| grep -A3 urtv` | A periodic, persisted job listed |

## 7. Power cycle (TCL)

| ID | Action | Expected |
|---|---|---|
| G1 | Unplug the TV for 30 s, power on, **do not open the app**, wait for the idle timer | Screensaver starts. If not: note it, open the app once, retest D4 |
| G2 | `adb logcat -d \| grep -iE "dream\|urtv" > G1.log` after G1 | Attach the log |

## 8. Browser (no app)

| ID | Action | Expected |
|---|---|---|
| H1 | On a computer open `https://raw.githack.com/tshi-dev/UrTV/master/dist/urtv.html` or download `dist/urtv.html` and double-click | Same screen in the browser; `F` toggles full screen |
| H2 | Add `#city=جدة&lat=21.5433&lon=39.1728&teams=136013` to the URL | Jeddah times; only one match slot |
| H3 | Resize the window to 1280×720 | Layout holds, nothing overlaps |

## 9. Home-screen card (launcher)

| ID | Action | Expected |
|---|---|---|
| L1 | Fresh install of both apps, press Home | No card on the home screen (off by default) |
| L2 | Screensaver settings → «بطاقة على الشاشة الرئيسية» → مواقيت الصلاة, then Home | Card under the pills on the left: today's prayers, next one gold. D-pad never lands on it |
| L3 | Repeat L2 with each option, then «لا شيء» | Card follows the choice; «لا شيء» removes it |
| L8 | Long-press OK on any app → «ترتيب المفضلة…» (also: screensaver settings → «ترتيب التطبيقات المفضلة») | List of favourites, numbered, first one focused |
| L9 | OK on the 3rd app, ▲ twice, OK; then Back | It turns gold, moves to the top, drops; home row shows it first |
| L10 | «إزالة» beside an app (▶/◀ to reach it); then «+» on an app under «إضافة تطبيق» | Removed / added at the end; never below 5 or above 10 (a message says so) |
| L5 | `optimize/dock.sh apps`, then `optimize/dock.sh set <3 packages from that list>`, then `optimize/dock.sh show` | Home screen redraws at once with those three first, topped up to 5; `show` lists them |
| L6 | `optimize/dock.sh set com.not.installed` | `error: none of these apps are on this TV's home screen`; row unchanged |
| L7 | `optimize/dock.sh reset` | Row back to the defaults |
| L4 | Open any app with the card on, then `adb shell top -n 1 \| grep urtv.home` | Launcher idle while the app is in front (card paused) |
| L10 | An app with only a phone launcher activity (an OEM store or settings app, Aptoide): `adb shell cmd package query-activities -a android.intent.action.MAIN -c android.intent.category.LAUNCHER` lists it, the LEANBACK_LAUNCHER query doesn't | It is in the grid once, opens with OK, and can be added to the favourites; TV apps are not listed twice; the stock home and its setup app are not in the grid |

---

## Report format

```
ID | PASS/FAIL | note | screenshot file
A7 | FAIL | "الدوري الهولندي" shows لا توجد نتائج | A7.png
```

Send back the table plus every FAIL screenshot/log.
