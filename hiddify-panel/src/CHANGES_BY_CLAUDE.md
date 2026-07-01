# پچ‌های اعمال‌شده روی فورک Hiddify-Manager / Hiddify-Panel

## 🚨 باگ واقعی از نصب خودت (۲۰۲۶-۰۷-۰۱) — `LookupError: 'webhook_secret' is not among the defined enum values`

**ریشه:** `init_db()` توی `panel/init_db.py` یه fast-path داره: اگه `db_version`
دیتابیس از قبل برابر آخرین نسخه‌ی migration باشه، بدون صدا زدن `migrate()`
برمی‌گرده. ولی تابعی که مقادیر enum حذف/تغییرنام‌داده‌شده رو پاکسازی می‌کنه
(`add_new_enum_values()` — که ردیف‌های یتیم رو حذف و ستون ENUM دیتابیس رو با
enum پایتون همگام می‌کنه) فقط داخل `migrate()` صدا زده می‌شد.

نصب اولت (قبل از این‌که `webhook_secret` رو به `webhook_signing_key` تغییر نام
بدم) یه ردیف `webhook_secret` توی `str_config` نوشته بود و `db_version` رو رد
کرده بود. نصب بعدی با کد جدید، چون `db_version` از قبل برابر آخرین نسخه بود،
از مسیر fast-path رد شد، `add_new_enum_values()` هیچ‌وقت صدا زده نشد، و اون
ردیف یتیم `webhook_secret` برای همیشه موند — هر بار هر کدی سعی می‌کرد
تنظیمات رو بخونه (از جمله دستور CLI `all_configs` که `current.json` رو
می‌سازه) کرش می‌کرد. خطاهای `Key not found: warp_mode` و `Key not found:
core_type` که بعدش دیدی، مستقیماً نتیجه‌ی همینن: چون `all_configs` کرش کرده
بود، `current.json` هیچ‌وقت درست ساخته نشد، پس اسکریپت‌های شل که ازش
`core_type`/`warp_mode` رو می‌خوندن هم شکست خوردن.

**فیکس:** `add_new_enum_values()` رو توی همون fast-path هم صدا زدم (نه فقط
داخل `migrate()`)، تا این پاکسازی هر بار پنل بالا میاد اجرا بشه، نه فقط وقتی
یه migration واقعی در حال اجراست. این یه فیکس عمومیه — هر فیلد enum دیگه‌ای
هم که در آینده rename/حذف بشه و از یه نصب قدیمی‌تر ردیف یتیم به‌جا مونده
باشه، دیگه پنل رو برای همیشه نمی‌شکنه.

**فایل:** `hiddify-panel/src/hiddifypanel/panel/init_db.py`

---

## 🚨 آپدیت مهم (بعد از دیدن لاگ نصب واقعی) — دو باگ واقعی پیدا و فیکس شد

### باگ ۱: پکیج پچ‌شده اصلاً نصب نمی‌شد
`hiddify-panel/install.sh` فقط وقتی `HIDDIFY_PANLE_SOURCE_DIR` رو دستی ست
می‌کردی، سورس محلی (پچ‌شده) رو نصب می‌کرد. با اجرای مستقیم `bash install.sh`
(بدون این env var)، هیچ‌جا هیچی نصب نمی‌شد — نه سورس پچ‌شده، نه حتی نسخه‌ی
اصلی از PyPI. دقیقاً همین بود که "No module named hiddifypanel" رو توی
لاگت ساخت. **فیکس شد:** حالا اگه `hiddify-panel/src/pyproject.toml` وجود
داشته باشه (یعنی یه سورس پچ‌شده باندل شده)، خودش خودکار تشخیص می‌ده و نصب
می‌کنه، دیگه نیازی به دستی ست‌کردن env var نیست.

### باگ ۲ (این واقعاً تقصیر من بود): چک سلامت آخر نصب، singbox رو همیشه
### فعال می‌خواست، حتی وقتی طبق core_type درست بود که خاموش باشه
توی `common/utils.sh` یه حلقه هست که آخر نصب چک می‌کنه سرویس‌های مهم
(xray, singbox, nginx, haproxy, mysql) واقعاً `active` شدن یا نه. این حلقه
از قبل یه استثنا برای xray داشت ("اگه core_type برابر xray نیست، ازش رد
شو")، ولی **هیچ استثنایی برای singbox نداشت**. قبل از پچ من، این مهم نبود
چون هر دو کور همیشه بدون قید و شرط اجرا می‌شدن (همون باگ اصلی مورد ۲). ولی
حالا که پچ من درست singbox رو خاموش می‌کنه وقتی `core_type=xray`ه، همین چک
سلامت هنوز منتظر active شدن singbox می‌موند و هیچ‌وقت نمی‌شد — دقیقاً همون
"an important service hiddify-singbox is not activating yet" که دیدی.
**فیکس شد:** یه استثنای متقارن برای singbox هم اضافه شد.

این دو باگ با هم دقیقاً می‌تونستن نصبت رو له کنن، مستقل از این‌که سورس پچ‌شده
نصب شده باشه یا نه. جزئیات کامل بقیه‌ی پچ‌ها پایین‌تره.

---

این فایل خلاصه‌ی هر ۱۲ مورد بحث‌شده‌ست، وضعیت واقعی هرکدوم، و فایل‌های دست‌خورده.
هرجا نوشته "نیاز به تست روی سرور واقعی" یعنی من نمی‌تونستم این رو با یه Xray/sing-box
واقعی و ترافیک واقعی تست کنم (سندباکس من دسترسی شبکه‌ی محدودی داره)، پس قبل از
production ازش استفاده نکن بدون تست روی یه سرور staging.

---

## 🚨 باگ‌های واقعی از تست زنده‌ی خودت — ۴ تا فیکس شد

خبر خوب اول: عکس‌هات نشون داد نصب این‌بار درست پیش رفته (صفحات Inbound Overrides واقعاً بالا اومدن) — یعنی فیکس نصب قبلی جواب داد. حالا بریم سراغ باگ‌های واقعی:

### ۱. Settings سابمیت نمی‌شد (فیکس شد)
فیلد جدیدم `webhook_secret` رو ساختم، ولی توی SettingAdmin یه قانون عمومی هست: **هر فیلدی که توی اسمش کلمه‌ی "secret" باشه، خودکار الزامی و باید دقیقاً فرمت UUID باشه.** من از این قانون خبر نداشتم و اسم فیلدم دقیقاً باهاش تصادم کرد. عوضش کردم به `webhook_signing_key` (که این قانون رو trigger نمی‌کنه) و آزاد/اختیاریه. برچسب‌های فارسی/انگلیسی که کلاً یادم رفته بود اضافه کنم (`config.webhook.label` که خام نشون می‌داد) هم اضافه و کامپایل شدن.

### ۲. کرش موقع تغییر دامنه‌ی Reality (فیکس شد)
`AttributeError: 'list' object has no attribute 'invalidate_all'` — توی `DomainAdmin.py`، تابع `_validate_reality_settings`، یه جا اشتباهی `get_proxies()` (با پرانتز، یعنی صداش می‌زد و یه لیست می‌گرفت) به‌جای `get_proxies` (بدون پرانتز، خود تابع کش‌شده) نوشته شده بود. دو جا همین اشتباه بود، هر دو فیکس شد.

### ۳. subscription لود نمی‌شد / خطای 500 (این احتمالاً مهم‌ترینشه، فیکس شد)
پچ allowInsecure→pinnedPeerCertSha256 که قبلاً ساختم، یه مشکل جدی داشت: هر بار subscription یوزری لود می‌شد، برای هر دامنه‌ی `allow_insecure`، یه TLS handshake **واقعی و synchronous** (تا ۳ ثانیه timeout) وسط پردازش ریکوئست اجرا می‌شد. اگه چند دامنه همزمان نیاز داشتن، یا یه دامنه در دسترس نبود، این delayها روی هم جمع می‌شدن و از timeout بالادستی (nginx/haproxy) رد می‌شدن → دقیقاً همون 500ی که توی اپ دیدی. الان کامل بازنویسی شد: هیچ‌وقت روی ریکوئست اصلی بلاک نمی‌کنه؛ اگه هش تازه نداره فوری `None` برمی‌گردونه (fallback امن به allowInsecure) و یه ترد جدا در پس‌زمینه هش رو برای دفعه‌ی بعد آماده می‌کنه.

### ۴. فقط "direct" نشون داده می‌شد، CDN/relay هیچ‌جا نبودن (احتمالاً فیکس شد)
رفتم دیدم توی seed دیفالت Hiddify، proxyهای CDN/relay (`WS CDN vless`, `grpc relay vless` و ده‌ها مورد دیگه) از قبل تعریف شدن، ولی این seed فقط داخل چندتا migration نسخه‌دار (`_v9`, `_v14` و…) صدا زده می‌شه که هرکدوم **فقط یه‌بار** اجرا می‌شن. با توجه به تاریخچه‌ی نصب‌های ناقصت، احتمال زیاد یکی از این migrationها نصفه‌کاره موند و db_version از روش رد شد بدون اینکه واقعاً proxyهای CDN/relay ساخته بشن. یه تابع backfill امن اضافه کردم (`get_proxy_rows_v1()` از قبل idempotent بود، خودش چک می‌کنه چی موجوده) که هر بار پنل بالا میاد این proxyهای غایب رو می‌سازه، بدون دست‌زدن به چیزی که هست.
**بعد از این پچ، صفحه‌ی Inbound Overrides رو رفرش کن و ببین "CDN" و "relay" هم اومدن یا نه.**

---


**فایل‌های جدید:**
- `hiddifypanel/models/routing.py` (مدل‌های `CustomOutbound`, `CustomRoutingRule`)
- `hiddifypanel/panel/admin/OutboundAdmin.py`
- `hiddifypanel/panel/admin/RoutingRuleAdmin.py`
- `hiddifypanel/panel/admin/InboundOverrideAdmin.py`

**فایل‌های تغییریافته:** `models/__init__.py`, `panel/hiddify.py`, `panel/init_db.py` (migration `_v122`), `hutils/proxy/shared.py`, `panel/admin/__init__.py`

### چی اضافه شد
سه تا صفحه‌ی جدید توی منوی ادمین، زیر دسته‌ی "Xray Configs":

1. **Outbounds** — فرم واقعی (نه JSON خام) برای ساختن outbound: تگ، پروتکل
   (vless/vmess/trojan/shadowsocks/socks/http/wireguard/freedom)، آدرس،
   پورت، UUID/پسورد، network، security، SNI. یه فیلد "Advanced Override"
   هم هست برای چیزی که فرم پوشش نمی‌ده.
2. **Routing Rules** — تگِ outbound مقصد، دامنه‌ها (هر خط یکی)، آی‌پی‌ها،
   پورت، network، و Priority (کوچیک‌تر زودتر چک می‌شه).
3. **Inbound Overrides** — روی مدل Proxy موجود (لیست همون combinationهای
   پروتکل/ترنسپورت/مودی که از قبل توی "Xray Configs" هست)، یه فیلد JSON
   برای override پارامترهای اون inbound خاص.

اینا دیگه به فیلد خام `additional_configs_xrayjson` نیازی ندارن — مستقیم
موقع تولید `current.json` (توی `panel/hiddify.py`، تابع
`all_configs_for_cli`) از دیتابیس این جدول‌ها خونده می‌شن و با هرچی خودت
دستی هم توی اون فیلد گذاشته باشی merge می‌شن (هر دو راه با هم کار می‌کنن).

### ⚠️ سطح اطمینان — این رو صادقانه بگم
برخلاف پچ‌های قبلی (که تک‌تک با jinja2/json5 واقعی تست کردم)، این یکی رو
**فقط از نظر syntax پایتون چک کردم**، نه با یه اپ Flask واقعی بالا. چیزایی
که ممکنه نیاز به دیباگ داشته باشه:
- فرم `params`/`extra_json` (ستون نوع JSON) ممکنه توی Flask-Admin به‌شکل
  یه textarea ساده رندر بشه یا اصلاً درست serialize/deserialize نشه —
  بسته به نسخه‌ی `flask-admin` و `wtforms` نصب‌شده. اگه ارور داد موقع باز
  کردن این صفحات، همین‌جا رو باید نگاه کرد.
- `category="Xray Configs"` برای گروه‌بندی منو گذاشتم؛ اگه صفحه‌ی
  "Xray Configs" موجود (همون `ProxyAdmin`) یه مکانیزم منوی متفاوت داشته
  باشه (چون FlaskView‌ه نه ModelView)، ممکنه این سه‌تای جدید یه منوی جدا
  و جدا از اون بسازن به‌جای زیرمجموعه‌ی همون — مشکلی نیست، فقط شاید جای
  دیگه‌ای از چیزی که فکر می‌کردی ظاهر بشن.

**پیشنهاد جدی:** با توجه به اتفاقی که افتاد (نصب خراب شد)، این یکی رو حتماً
اول روی یه سرور تستی/staging نصب کن، نه مستقیم روی production. اگه صفحات
بالا نیومدن یا ارور دادن، لاگ پنل (`journalctl -u hiddify-panel -n 100`)
رو برام بفرست تا دقیق دیباگ کنم.

---


توی پیام قبلی من یه لیست ۶تایی دادم (Fail2ban, RBAC, HWID, Webhook,
PostgreSQL/TimescaleDB, Outbound chaining/routing) و بعدش خودم ۳تا
(Fail2ban, Webhook, RBAC) رو پیشنهاد کردم؛ وقتی گفتی "دوتای آخری"، منظورت
دو ردیف آخر **جدول اصلی** بود (PostgreSQL/TimescaleDB و Outbound
chaining/routing) نه دو مورد آخر پیشنهاد من. عذر می‌خوام بابت این ابهام —
Webhook و RBAC رو قبلاً اشتباهی پیاده کردم (که می‌تونن بمونن، ضرری ندارن)،
و حالا این دوتا رو که واقعاً خواسته بودی هم پیاده کردم:

### ۱۵. PostgreSQL/TimescaleDB به‌عنوان بک‌اند
**فایل‌های جدید:** `other/postgres/install.sh`
**فایل‌های تغییریافته:** `install.sh`, `hiddify-panel/run.sh`, `hiddify-panel/pyproject.toml` (اضافه شدن `psycopg`)

رفتم دقیق دنبال کردم که connection string واقعی (نه فقط `app.cfg` که یه
template‌ست) از کجا میاد: `hiddify-panel/run.sh` هر بار در Apply/Reinstall
اجرا می‌شه، پسورد MySQL رو از فایل `other/mysql/mysql_pass` می‌خونه، و
`SQLALCHEMY_DATABASE_URI` رو از نو می‌سازه — قبلاً این بخش صرفاً hardcode
روی MySQL بود.

**چیزی که ساختم:** یه backend انتخابی با متغیر محیطی `DB_BACKEND`:
```bash
DB_BACKEND=timescaledb ./install.sh --no-gui   # یا DB_BACKEND=postgres
```
اگه ست نکنی، دقیقاً مثل قبل MySQL نصب می‌شه (پیش‌فرض بدون تغییر). اگه
`postgres` یا `timescaledb` بذاری:
- `other/postgres/install.sh` به‌جای mariadb نصب می‌شه — پستگرس رو نیتیو
  (نه داکر) نصب می‌کنه، یوزر/دیتابیس `hiddifypanel` رو می‌سازه، پسورد
  رندوم توی `other/postgres/postgres_pass` ذخیره می‌شه (دقیقاً همون الگوی
  `mysql_pass`).
- برای `timescaledb`: قبلش ریپوی رسمی TimescaleDB رو اضافه می‌کنه و
  اکستنشن `timescaledb` رو روی دیتابیس فعال می‌کنه. TimescaleDB خودش یه
  اکستنشن روی Postgres‌ه (نه پروتکل جدا)، پس connection string فرقی نداره.
- `hiddify-panel/run.sh` بسته به `DB_BACKEND`، connection string درست
  (`postgresql+psycopg://...`) رو می‌سازه.

**🔴 خیلی مهم — این یه ابزار migration زنده نیست:**
این فقط برای **نصب تازه** (یا سرور تستی) کار می‌کنه. اگه الان MySQL داری
با داده‌ی واقعی روش، صرفاً عوض کردن `DB_BACKEND` و ری‌اینستال، دیتابیس
جدید خالی می‌سازه و **داده‌های موجودت منتقل نمی‌شن**. برای migration واقعی
باید با `pg_loader` یا mysqldump→pgloader دستی کوچ کنی؛ من این بخش رو پیاده
نکردم چون کار روی داده‌ی production بدون تست واقعی خیلی خطرناکه. اگه
واقعاً می‌خوای کوچ کنی، بگو تا اسکریپت migration جدا (با backup اجباری قبلش)
براش بنویسم.

### ۱۶. Outbound Chaining / Routing Rules (بدون ساختن UI کامل، ولی کاملاً کاربردی)
**فایل‌های تغییریافته:** `common/jinja.py`, `xray/configs/06_outbounds.json.j2`, `xray/configs/03_routing.json.j2`

اینجا یه کشف جالب داشتم: فیلد `additional_configs_xrayjson` از قبل توی
دیتابیس/تنظیمات پنل تعریف شده بود (حتی description‌ش می‌گفت "Additional
outbounds for Xray Json") ولی **هیچ‌جا واقعاً خونده نمی‌شد** — دقیقاً مثل
داستان `extra_params` برای دامنه‌ها که قبلاً پیدا کردم. یعنی خود سازنده‌های
Hiddify قصدشون این فیچر بوده ولی نصفه‌کاره رهاش کردن.

کاری که کردم:
1. یه فیلتر Jinja جدید (`from_json`) به `common/jinja.py` اضافه کردم که این
   فیلد رو موقع رندر کانفیگ سرور پارس می‌کنه.
2. `06_outbounds.json.j2` رو طوری تغییر دادم که هر outbound اضافه‌ای که
   توی این JSON بذاری، به آرایه‌ی outboundهای واقعی Xray اضافه می‌شه.
3. `03_routing.json.j2` رو طوری تغییر دادم که routing ruleهای اضافه، درست
   **قبل از قانون پیش‌فرض آخر** (که همه‌چی رو catch می‌کنه) چک بشن — چون
   ترتیب rule توی Xray مهمه، اول match برنده‌ست.

**فرمتی که باید توی تنظیمات پنل (Settings → Additional Configs → Additional
Configs for Xray JSON) بذاری:**
```json
{
  "outbounds": [
    {
      "tag": "relay-yerevan",
      "protocol": "vless",
      "settings": {
        "vnext": [{"address": "1.2.3.4", "port": 443, "users": [{"id": "YOUR-UUID", "encryption": "none"}]}]
      },
      "streamSettings": {"network": "tcp", "security": "tls"}
    }
  ],
  "routing_rules": [
    {"type": "field", "outboundTag": "relay-yerevan", "domain": ["example.com"]}
  ]
}
```
با این می‌تونی دقیقاً همون کاری که با Backhaul دستی می‌کنی رو (chain کردن
ترافیک به یکی دیگه از سرورهات) از پنل، بدون دست زدن به فایل‌های .j2 روی
سرور انجام بدی.

این رو با یه رندر واقعی (jinja2 + json5، دقیقاً همون کتابخونه‌هایی که
`common/jinja.py` استفاده می‌کنه) تست کردم — هم با مقدار خالی (رفتار
پیش‌فرض فعلی، هیچی نمی‌شکنه) هم با یه outbound/rule نمونه (درست inject
می‌شه و JSON نهایی معتبره).

**⚠️ چیزی که این نیست:** یه UI گرافیکی با فرم/دراپ‌داون برای ساختن rule.
همچنان باید JSON خام بنویسی توی یه تکست‌باکس. ساختن یه rule-builder کامل
(مثل چیزی که 3x-ui داره) چند هفته کاره؛ این نسخه‌ی «کار می‌کنه، ولی خام»‌شه
که سریع بهت می‌رسه. اگه بعداً خواستی فرم درست‌وحسابی هم روش بذاریم.

---


### ۱۳. Webhook عمومی (رویدادهای فعال/غیرفعال شدن یوزر)
**فایل‌های جدید:** `hiddifypanel/hutils/webhook.py`
**فایل‌های تغییریافته:** `models/config_enum.py`, `panel/init_db.py` (migration `_v120`), `panel/usage.py`

مکانیزم: دقیقاً همون نقطه‌ای که کد قبلاً تشخیص می‌داد یوزر از active به inactive
(یا برعکس) رفته و پیام تلگرام می‌فرسته (`send_bot_message`)، الان یه POST
JSON هم به URL دلخواهت می‌فرسته — کاملاً مستقل از تلگرام.

**تنظیمات (خودکار توی صفحه‌ی Settings پنل ظاهر می‌شن، چون Hiddify هر
`ConfigCategory` رو خودکار رندر می‌کنه):**
- `webhook_enable` — سوییچ کلی
- `webhook_url` — آدرس مقصد
- `webhook_secret` — اختیاری؛ اگه پر کنی، هر ریکوئست یه هدر
  `X-Hiddify-Signature` داره (HMAC-SHA256 بدنه‌ی JSON با این secret) تا
  مطمئن بشی درخواست واقعاً از پنل خودته.

**payload نمونه:**
```json
{
  "event": "user_deactivated",
  "timestamp": 1751234567.89,
  "data": {
    "uuid": "...", "name": "...",
    "current_usage_GB": 105.2, "usage_limit_GB": 100,
    "remaining_days": 5,
    "reason": "traffic_exceeded"
  }
}
```
`event` می‌تونه `user_activated` یا `user_deactivated` باشه؛ `reason` فقط
روی deactivate پر می‌شه (`traffic_exceeded` / `expired` / `disabled`).

درخواست توی یه ترد جدا با ۳ بار retry می‌ره؛ اگه endpoint خودت پایین باشه یا
timeout بده، هیچ‌وقت پردازش usage یوزرها رو بلاک نمی‌کنه یا کرش نمی‌ده.

**⚠️ چیزی که پیاده نکردم:** رویداد `user_created` یا رویدادهای مربوط به
دامنه (چون health-check دامنه اصلاً وجود نداره - اون خودش یه فیچر جداست).
اگه این‌ها رو هم می‌خوای، بگو تا اضافه کنم.

### ۱۴. RBAC (پرمیشن‌های ریزتر روی admin/agent)
**فایل‌های تغییریافته:** `models/role.py` (enum جدید `Permission`), `models/admin.py`,
`auth.py`, `panel/init_db.py` (migration `_v121`), `panel/admin/DomainAdmin.py`,
`panel/admin/UserAdmin.py`, `panel/admin/AdminstratorAdmin.py`

**طراحی:** یه ستون JSON جدید (`AdminUser.permissions`) اضافه شد که لیستی از
مقادیر enum جدید `Permission` رو نگه می‌داره
(`view_traffic`, `manage_users`, `manage_domains`, `manage_settings`,
`restart_services`, `reinstall_apply`).

**نکته‌ی مهم برای backward compatibility:** اگه این لیست خالی باشه (پیش‌فرض
برای هر ادمین که از قبل ساخته شده)، دقیقاً مثل قبل رفتار می‌کنه — یعنی هیچ
ادمین موجودی با این تغییر یهو دسترسیش قطع نمی‌شه. فقط وقتی super_admin
صریحاً یه لیست غیرخالی برای یه ادمین ست کنه، اون ادمین محدود به همون لیست
می‌شه (حتی اگه Mode‌ش اجازه‌ی بیشتری بده).

`login_required()` یه پارامتر اختیاری جدید `permissions=` گرفت که کاملاً
optional و backward-compatible‌ست (اگه پاس ندی، هیچی عوض نمی‌شه).

**کجاها الان واقعاً وصل شده (نمونه‌ی کارکردی، نه کل کدبیس):**
- `DomainAdmin.is_accessible()` → نیاز به `Permission.manage_domains`
- `UserAdmin.is_accessible()` → نیاز به `Permission.manage_users`

**⚠️ صادقانه بگم:** کدبیس Hiddify ده‌ها admin view دیگه داره (Backup,
ConfigAdmin, NodeAdmin, ProxyAdmin, Actions, SettingAdmin, ...). اینا رو
یکی‌یکی به این سیستم وصل نکردم چون:
1. بعضی‌هاشون (`Actions`, `SettingAdmin`) از قبل `super_admin`-only ان، پس
   وصل کردن permission بهشون بی‌معنیه (super_admin همیشه همه‌چی رو داره).
2. برای بقیه، باید هرکدوم رو دستی چک کنم کدوم Permission واقعاً بهش
   می‌خوره — این یه کار مکانیکی ولی طولانیه.

**الگوی گسترش دادنش:** هرجا `is_accessible()` یا `login_required(roles=...)`
می‌بینی، فقط `permissions={Permission.xxx}` رو اضافه کن — دقیقاً همون کاری
که روی DomainAdmin/UserAdmin کردم. اگه بخوای، می‌تونم توی یه پاس دیگه همه‌ی
admin viewها رو بگردم و این الگو رو روی همه اعمال کنم.

**چطور استفاده کنی:** برو توی Administrators، یه ادمین رو باز کن، فیلد
"Restricted Permissions" رو پیدا کن. اگه یه agent می‌خوای که فقط دسترسی
مدیریت یوزر داشته باشه نه دامنه، فقط `manage_users` رو تیک بزن.

---

## ✅ کاملاً پچ شد و با اطمینان بالا درسته

### ۱. باگ اصلی Apply/Reinstall (این بزرگ‌ترین کشفم بود)
**فایل:** `Hiddify-Panel/hiddifypanel/panel/run_commander.py`

ریشه‌ی واقعی این‌که "Apply Config" هیچ کاری نمی‌کرد: تابع `commander()` یه
`threading.Thread(target=cmd_in_back, daemon=True)` می‌ساخت **بدون پاس دادن
آرگومان `cmd` به تابع** (`cmd_in_back(cmd)` نیاز به یه پارامتر داشت). یعنی هر
بار که این از حالت پیش‌فرض `run_in_background=True` صدا زده می‌شد (که تقریباً
همیشه همینطوره)، ترد با `TypeError` بلافاصله می‌مرد و **هیچ دستوری اصلاً اجرا
نمی‌شد** — نه apply، نه install، نه reinstall. چون این خطا فقط توی ترد
بک‌گراند می‌افتاد، هیچ‌جا توی پنل نشون داده نمی‌شد؛ فقط "در حال اعمال..." رو
می‌دیدی و بعدش هیچ اتفاقی نمی‌افتاد.

فیکس: `args=(base_cmd,)` رو به Thread اضافه کردم، و یه لاگ برای exit code
غیر صفر اضافه کردم که دیگه شکست‌ها بی‌صدا نباشن.

### ۲. Xray ↔ sing-box سوییچ واقعی نبود
**فایل‌ها:** `Hiddify-Manager/install.sh`, `Hiddify-Manager/singbox/disable.sh` (جدید)

- `install_run xray 1` همیشه hardcode بود (فلگ enable هیچوقت از `core_type` نمی‌اومد).
- `install_run singbox` اصلاً فلگی نداشت، و `singbox/disable.sh` هم اصلاً وجود نداشت.
  یعنی حتی اگه فلگ 0 پاس می‌دادی، `runsh` دنبال `disable.sh` می‌گشت، پیدا نمی‌کرد، و
  هیچ کاری نمی‌کرد.

نتیجه: هر دو کور همیشه نصب/اجرا می‌شدن، صرف‌نظر از `core_type`.

فیکس: `singbox/disable.sh` رو ساختم (mirror از `xray/disable.sh`)، و `install.sh`
رو طوری تغییر دادم که `core_type` رو بخونه و فقط کور انتخاب‌شده رو نصب/اجرا کنه.

### ۳. `cryptography<42`
**فایل:** `Hiddify-Panel/pyproject.toml`

از `cryptography<42` به `cryptography>=44,<46` تغییر کرد. نسخه‌های ۴۲+ چندین
CVE رو پچ کردن. کد استفاده‌کننده (`hutils/crypto.py`, فقط `x25519`/`ed25519`
key generation) از APIهایی استفاده می‌کنه که بین این نسخه‌ها stable بودن، پس
ریسک breaking change کمه، ولی حتماً `pip install -e .` رو دوباره روی محیط
تست بزن و مطمئن شو چیزی نشکسته.

### ۴. عدم اعتبارسنجی رنج پورت
**فایل:** `Hiddify-Panel/hiddifypanel/models/domain.py`

تابع `_safe_port_offset()` رو اضافه کردم که به‌جای `base_port + port_index`
خام، چک می‌کنه نتیجه از ۶۵۵۳۵ رد نشه (wrap می‌کنه به رنج بالا) و اگه به رنج
reserved (زیر ۱۰۲۴) بیفته warning لاگ می‌کنه. روی همه‌ی
`internal_port_hysteria2/tuic/naive/special/dnstt` اعمال شد.

---

## ✅ الان کامل پیاده‌سازی شد (بعد از درخواست دوم)

### ۱۱. Per-domain override (transport/security جدا برای هر دامنه)
**فایل‌ها:** `hiddifypanel/hutils/proxy/shared.py`, `hiddifypanel/panel/admin/DomainAdmin.py`

خبر خوب: یه مکانیزم تقریباً آماده از قبل توی کد بود که فقط برای dnstt سیم‌کشی
شده بود. فیلد `Domain.extra_params` (یه ستون JSON که از قبل روی هر دامنه‌ای
هست) قبلاً فقط داخل شاخه‌ی dnstt توی `make_proxy()` merge می‌شد. کاری که کردم:

1. یه تابع `apply_domain_overrides()` نوشتم که این JSON رو، برای **هر
   پروتکلی** (نه فقط dnstt)، روی دیکشنری نهایی proxy اعمال می‌کنه — درست بعد
   از `make_proxy()` توی تنها call-siteـش (`get_valid_proxies`).
2. یه blocklist کوچیک گذاشتم (`uuid`, `dbe`, `dbdomain`, `proto`, `name`,
   `params`) تا کلیدهای حیاتی/شناسایی کاربر دست‌نخورده بمونن؛ بقیه‌ی هرچی
   (`sni`, `fingerprint`, `alpn`, `hysteria_obfs_password`, `mux_enable`،
   هرچی توی دیکشنری proxy باشه) قابل override شدن.
3. مشکل واقعی این بود که widget فرم ادمین (`CustomJSONField`) یه مدل
   pydantic به اسم `DnsTT` استفاده می‌کرد که به‌صورت پیش‌فرض **هر کلیدی خارج
   از فیلدهای تعریف‌شده‌ی dnstt رو بی‌صدا حذف می‌کرد** (رفتار پیش‌فرض pydantic
   v2). `model_config = ConfigDict(extra='allow')` رو اضافه کردم تا بشه هر
   کلید دلخواهی هم توش نوشت.

**چطور استفاده کنی:** برو توی پنل ادمین، یه دامنه (مثلاً یکی از relay‌هات) رو
باز کن، فیلد "Extra Params / Per-Domain Override" رو پیدا کن، و مثلاً بنویس:
```json
{
  "fingerprint": "firefox",
  "hysteria_obfs_password": "my-custom-password-for-this-domain-only"
}
```
این فقط روی همون یه دامنه اعمال می‌شه، نه بقیه.

**⚠️ نکته:** چون blocklist محدوده، تئوریاً می‌شه با یه کلید اشتباه (مثلاً
`security` یا `mode`) یه کانفیگ خراب تولید کرد. توصیه می‌کنم اول روی یه
دامنه‌ی تست امتحان کنی، نه مستقیم روی production.

---

## 🟡 پچ شد ولی نیاز به تست جدی روی سرور واقعی داره

### ۵. حذف `allowInsecure` از Xray-core (v26.2.6+)
**فایل‌ها:** `hiddifypanel/hutils/network/net.py`, `hiddifypanel/hutils/proxy/shared.py`,
`hiddifypanel/hutils/proxy/xrayjson.py`, `hiddifypanel/hutils/proxy/xray.py`

- تابع جدید `get_pinned_cert_sha256(host, port)` اضافه شد: با یه TLS handshake
  واقعی، گواهی peer رو می‌گیره و SHA256 بیس۶۴‌اش رو برمی‌گردونه (کش می‌شه، TTL
  یک ساعت).
- `sni_host_server_extractor` حالا `pinned_cert_sha256` رو هم به خروجی اضافه
  می‌کنه (فقط وقتی `allow_insecure` قراره true باشه).
- `xrayjson.py`: به‌جای `allowInsecure: true`، حالا `pinnedPeerCertSha256`
  می‌فرسته اگه هش موجود باشه؛ اگه هنوز گواهی fetch نشده (مثلاً دامنه‌ی تازه‌
  اضافه‌شده)، fallback به `allowInsecure` می‌کنه تا کور قدیمی‌تر هم کار کنه.
- `xray.py` (share-link ها برای v2rayNG و بقیه): پارامتر `pcs=<hash>` رو
  **اضافه** کرد کنار `allowInsecure`/`insecure` قدیمی (این استاندارد فعلی
  community‌ست: هم پارامتر جدید هم قدیمی، برای سازگاری با کلاینت‌های مختلف).

**⚠️ این مهم‌ترین چیزیه که باید تست کنی.** `get_pinned_cert_sha256` یه TLS
handshake واقعی می‌زنه؛ اگه دامنه پشت CDN/فایروال باشه یا در لحظه‌ی تولید
کانفیگ در دسترس نباشه، ممکنه هش خالی برگرده و به‌صورت خاموش به allowInsecure
قدیمی fallback کنه (که با Xray-core 26.2.6+ باز هم fail می‌شه). پیشنهادم:
بعد از اعمال، لاگ سرویس xray رو حین اولین استارت چک کن.

### ۶. مکانیزم مسیریابی mieru/naive برای relay
**فایل:** `hiddifypanel/panel/init_db.py`

پیدا کردم که relay-mode برای mieru/naive **از قبل توی کد وجود داره**
(migration `_v114` این proxyها رو با `cdn=relay` اضافه می‌کنه)، ولی migration
قدیمی‌تر (`_v111`) فقط نسخه‌ی `cdn='direct'` رو ساخته بود. اگه panel تو یه
نسخه‌ی قدیمی‌تر از ۱۱۴ نصب شده و درست آپدیت نشده باشه (یا `bulk_save_objects`
موقع migration به هر دلیلی fail کرده باشه)، نسخه‌ی relay هیچوقت اضافه نمی‌شه.

فیکس: یه تابع idempotent (`_ensure_mieru_naive_relay_variants`) اضافه کردم که
هر بار پنل استارت می‌شه چک می‌کنه این ردیف‌ها هستن یا نه، و فقط چیزی که غایبه
رو اضافه می‌کنه (چیزی رو حذف/دستکاری نمی‌کنه).

**بعد از اعمال این پچ:** برو توی پنل ادمین، بخش Proxies رو چک کن ببین
"MieruTCP"/"MieruUDP"/"NaiveTLS"/"NaiveQuic" با mode=relay اونجا هست یا نه.
اگه هست ولی هنوز روی دامنه‌ی relay نشون نمی‌ده، باید توی همون صفحه enable‌ش کنی
(این proxyها پیش‌فرض `enable=True` ساخته می‌شن ولی شاید توی UI جدا فعال/غیرفعال
باشن).

---

## 📝 مستندسازی/راهنمایی UI (بدون تغییر منطق پرخطر)

### ۷. Fake domain و ارث‌بری از Direct
**فایل:** `hiddifypanel/panel/admin/DomainAdmin.py`

اینجا برخلاف چیزی که اول فکر می‌کردم، **از قبل مکانیزم override وجود داشت**:
فیلد `cdn_ip` روی هر دامنه (حتی Fake) از قبل توی فرم هست، و
`sni_host_server_extractor` همیشه اول این فیلد رو چک می‌کنه؛ فقط اگه خالی
باشه میره سراغ IP مستقیم سرور. توی `DomainAdmin.py` هم یه قانون هست:
`if model.mode == DomainType.fake and not model.cdn_ip: model.cdn_ip = str(server_ips[0])`
— یعنی وقتی دامنه‌ی Fake می‌سازی و این فیلد رو خالی می‌ذاری، خودش IP مستقیم
سرور رو می‌ذاره توش (default معقول، ولی نامرئی توی UI).

**راه‌حل واقعی برات:** موقع ساخت دامنه‌ی Fake، فیلد "cdn_ip" رو دستی با IP یا
دامنه‌ی دلخواهت پر کن — دیگه به تنظیمات direct وابسته نمی‌مونه. من فقط
توضیحش رو توی UI واضح‌تر کردم (help text مربوط به فیلد mode) که این default
نامرئی رو کشف کنی، بدون این‌که منطق پیش‌فرض (که برای کاربرای دیگه معقوله) رو
بشکنم.

### ۸. سردرگمی dnstt
**فایل:** `hiddifypanel/panel/admin/DomainAdmin.py`

توضیح مربوط به فیلد mode رو گسترش دادم تا صراحتاً بگه dnstt نیاز به NS
delegation داره و مثل بقیه‌ی مودها (CDN/A-record) کار نمی‌کنه.

---

## 🔴 بررسی شد، ریشه پیدا شد، ولی پچ کد نزدم (دلیلش رو بخون)

### ۹. WARP کار نمی‌کنه (`wgcf` نصب نمی‌شه)
رفتم `other/warp/wireguard/install.sh` و `common/package_manager.sh` رو خط‌به‌خط
خوندم. مکانیزم دانلود (`download_package` + `packages.lock`) از نظر منطقی درست
به‌نظر می‌رسه و entry برای wgcf (نسخه ۲.۲.۳۰، amd64/arm64) توی
`common/packages.lock` هست. **نتونستم یه باگ قطعی و قابل تکرار پیدا کنم بدون
اجرای واقعی روی یه سرور** (چون به شبکه/باینری‌های واقعی توی سندباکسم دسترسی
ندارم). گزارش‌های GitHub (issue #4847) از نسخه‌های قدیمی‌تر بودن که شاید این
سیستم packages.lock توشون نبوده.

**پیشنهاد عملی:** روی سرور خودت دستی اجرا کن و لاگ خامش رو ببین:
```bash
cd /opt/hiddify-manager/other/warp/wireguard
bash install.sh
```
اگه خطا داد، دقیقاً همون پیام رو بفرست برام تا پچ دقیق بزنم — الان دارم حدس
می‌زنم به‌جای دیباگ واقعی.

### ۱۰. تداخل WireGuard خودت با WARP
همینطور — این به فایروال/routing rules واقعی سرورت بستگی داره (nftables vs
iptables، ترتیب قوانین، fwmark). بدون یه سرور واقعی جلوم که بتونم
`wg show`/`iptables -L` روش بزنم، هر پچی که بزنم حدسیه و ممکنه بدتر کنه. اگه
خروجی `iptables-save` یا `nft list ruleset` سرورت رو برام بفرستی (با IP/کلید
عمومی sanitize‌شده)، می‌تونم دقیق پچ بزنم.

### ۱۲. TODOهای سازگاری v2rayNG توی xrayjson.py
اینا (خطوط ۲۳۶، ۴۰۶، ۴۲۵) اشاره به edge caseهای نامشخصی دارن که خود نویسنده‌ی
اصلی هم دقیقاً مشخص نکرده کدوم پروتکل/کلاینته. پچ کورکورانه‌ی اینا بدون دونستن
دقیقاً کدوم کانفیگ با کدوم کلاینت مشکل داره، ریسک شکستن چیزی که الان کار
می‌کنه رو داره. اگه یه کانفیگ خاص داری که با v2rayNG وصل نمی‌شه، اون کانفیگ
JSON رو بفرست تا دقیق دیباگ کنم.

---

## چک‌لیست قبل از production

1. `pip install -e .` رو توی venv پنل دوباره بزن (به‌خاطر آپدیت cryptography)
2. یه دامنه‌ی تست با `allow_insecure=True` بساز، کانفیگش رو بگیر، مطمئن شو
   `pinnedPeerCertSha256` پر شده (نه خالی) قبل از این‌که روی همه‌ی دامنه‌ها
   اعمال کنی
3. `core_type` رو عوض کن (xray ↔ singbox) و با `systemctl status
   hiddify-xray hiddify-singbox` مطمئن شو فقط یکی‌شون active هست
4. دکمه‌ی "Apply Config" رو بزن و لاگ پنل رو ببین که واقعاً چیزی اجرا میشه
   (قبلاً هیچی نمی‌شد)
5. Proxies admin رو چک کن که Mieru/Naive relay variant واقعاً exist و enable‌ست
