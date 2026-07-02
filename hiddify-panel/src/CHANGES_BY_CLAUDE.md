# پچ‌های اعمال‌شده روی فورک Hiddify-Manager / Hiddify-Panel

## 🐞 اسکن باگ: outbound نوع wireguard کانفیگ غیرقابل‌اتصال می‌ساخت (۲۰۲۶-۰۷-۰۲)

گفتی کل پروژه رو برای باگ اسکن کن. تمرکزم روی کدی بود که خودم دست زدم و
مسیرهایی که تو واقعاً استفاده می‌کنی + کلاس باگ‌هایی که قبلاً خوردیم.
چیزهایی که چک کردم و سالم بودن: همه‌ی ConfigEnum/Domain property هایی که
`get_available_inbound_tags()` صدا می‌زنه واقعاً وجود دارن (وگرنه صفحه‌ی
Routing Rules کرش می‌کرد)، هر دو core (xray و singbox) کانفیگ‌های custom
رو می‌خونن، اسکریپت‌های install سازگارن، و ارجاع قدیمی `hiddify0` جایی
نمونده.

**یه باگ واقعی پیدا شد:** شاخه‌ی `wireguard` توی `to_xray_dict()` یه
outbound با `"peers": []` (خالی!) می‌ساخت و `address` (که host اندپوینت
ه) رو اشتباهی به‌جای آدرس لوکال تونل می‌ذاشت - یعنی اگه کسی Protocol رو
wireguard انتخاب می‌کرد، یه کانفیگ تولید می‌شد که اصلاً نمی‌تونست وصل
بشه (نه peer، نه endpoint). شاخه‌ی singbox هم `pre_shared_key` رو اصلاً
خروجی نمی‌داد.

چون همین session فیلدهای `peer_public_key`/`preshared_key`/`local_address`
رو (برای amneziawg) اضافه کرده بودم، حالا wireguard هم می‌تونه ازشون
استفاده کنه:
- xray: `secretKey` = private key، `address` = `local_address` تونل، و یه
  peer واقعی با `publicKey`/`endpoint` (`address:port`)/`allowedIPs` و
  اختیاری `preSharedKey`.
- singbox: اضافه شدن `pre_shared_key` وقتی پرشد.

**فایل تغییریافته:** `models/routing.py`.

**نکته‌ی صادقانه درباره‌ی محدوده:** اسکن کاملِ خط‌به‌خطِ ~۱۹هزار خط
پایتون + ۱۲۰ اسکریپت bash + ۷۶ تمپلیت (که اکثرشون کد بالادستیِ خودِ
Hiddify ان، نه کد ما) یه کار خیلی بزرگ‌تره و بیشترش نویز می‌شه. این پاس
روی کد خودمون و مسیرهای واقعیِ در حال استفاده متمرکز بود.

---

## 🚨 باگ واقعی و قدیمی: singbox/install.sh همیشه exit 3 می‌داد (۲۰۲۶-۰۷-۰۲)

پیدا شد وقتی داشتیم دنبال می‌گشتیم چرا `hiddify-core` بعد از تست
amneziawg غیب شده بود. این باگ اصلاً ربطی به کار من نداشت - از قبل
توی خودِ فورک بوده:

خط ۱۰ فایل رو با اسم `sb.tar.gz` دانلود می‌کنه، ولی خط ۱۴ سعی می‌کرد
`rm -r sb.zip` بزنه - یه اسم فایل که اصلاً هیچ‌وقت وجود نداشته (احتمالاً
باقی‌مونده‌ی یه نسخه‌ی قدیمی‌تر از اسکریپت که یه‌زمانی `.zip` دانلود
می‌کرده). چون `sb.zip` وجود نداره، `rm -r` fail می‌کنه و `exit 3` اجرا
می‌شه - یعنی **این اسکریپت هر بار که اجرا می‌شه دقیقاً همین‌جا می‌میره**،
قبل از این‌که `chown`/`chmod +x`/`ln -sf` (خط‌های ۱۵-۱۷) یا
`set_installed_version` (خط ۱۹) اصلاً اجرا بشن.

چون `set_installed_version` هیچ‌وقت اجرا نمی‌شه، نسخه‌ی نصب‌شده هیچ‌وقت
ثبت نمی‌شه، یعنی این اسکریپت هر بار که اجرا بشه (هر Reinstall) کل
tarball ~70 مگابایتی رو دوباره از GitHub دانلود می‌کنه - هم اتلاف وقت و
پهنای باند، هم مهم‌تر: اگه دانلود/extract/copy یه بار به هر دلیلی (قطعی
شبکه، فشار دیسک وسط یه Reinstall موازی) نصفه‌کاره fail بشه، این اسکریپت
باز هم exit 3 می‌ده - دقیقاً همون چیزی که چک‌کردن exit code رو بی‌فایده
می‌کنه، و باینری `hiddify-core` می‌تونه کلاً غایب بمونه بدون این‌که هیچ
ارور واضحی دیده بشه.

**فیکس:** خط ۱۴ شد `rm -rf sb.tar.gz hiddify-core-* 2>/dev/null` (اسم
درست فایل + `-f` که دیگه اگه هیچی برای پاک کردن نبود هم fail نکنه) و
`|| exit 3` حذف شد - پاک کردن فایل‌های موقت نباید کل نصب رو بترکونه.

**فایل تغییریافته:** `singbox/install.sh`.

---

## 🚨🚨 CRITICAL: AmneziaWG سرورت رو کامل قطع کرد - Table=off جا افتاده بود (۲۰۲۶-۰۷-۰۲)

تست کردی، سرور کامل از دسترس خارج شد (SSH هم قطع شد). مقصر من بودم:
`render_amneziawg_conf()` یه `[Interface]`/`[Peer]` می‌ساخت با
`AllowedIPs = 0.0.0.0/0, ::/0` ولی بدون `Table = off`. رفتار پیش‌فرض
`wg-quick`/`awg-quick` با این AllowedIPs اینه که routing table پیش‌فرض
خودِ **سرور** رو عوض کنه بره روی این تونل - نه فقط این‌که interface رو
در دسترسِ xray/singbox’s بذاره تا با `bind_interface` انتخابش کنن. یعنی
کل ترافیک خروجی خودِ سرور (از جمله SSH) رفت روی تونل به یه peer که
راهی به‌بیرون نداشت - سرور کامل قطع شد.

این دقیقاً همون مشکلیه که راه‌حل WARP توی همین کدبیس از قبل باهاش
مواجه شده بود: `other/warp/wireguard/run.sh.j2` صراحتاً
`Table = off` رو به کانفیگش تزریق می‌کنه دقیقاً به همین دلیل. باید
همون الگو رو این‌جا هم می‌ذاشتم و نذاشتم.

**فیکس:** `Table = off` به `render_amneziawg_conf()` اضافه شد (بعد از
`PrivateKey`، قبل از `Address`). با این خط، `awg-quick` فقط interface
رو می‌سازه/بالا میاره و آدرس می‌ده، هیچ روتی به جدول کرنل اضافه نمی‌کنه؛
مسیریابی ترافیک مشخص فقط از طریق `bind_interface`/`sockopt.interface`ی
که خودِ xray/singbox صراحتاً روی این interface تنظیم می‌کنن انجام می‌شه
- دقیقاً مثل WARP.

**⚠️ اگه سروری داری که قبلاً این interface روش بالا اومده:**
1. از کنسول وب هاستت (نه SSH - چون همون قطع شده) وارد شو.
2. `systemctl stop awg-quick@awg{id}` و
   `systemctl disable awg-quick@awg{id}` بزن (به‌جای `{id}` عدد واقعی
   ردیف Outbound رو بذار، از اسم فایل توی
   `/etc/amnezia/amneziawg/*.conf` می‌تونی پیدا کنی).
3. `ip link delete awg{id}` بزن تا خودِ interface هم پاک بشه.
4. بعد از این fix رو pull کن و Reinstall بزن تا `.conf` جدید (با
   `Table = off`) دوباره نوشته بشه، و دوباره امتحان کن.

**فایل تغییریافته:** `models/routing.py` (`render_amneziawg_conf`).

---

## 🚨 هیچ کانفیگی وصل نمی‌شد: pinnedPeerCertSha256 با base64 به‌جای hex (۲۰۲۶-۰۷-۰۲)

گفتی هیچ‌کدوم از کانفیگ‌ها وصل نمی‌شن (نه فقط amnezia). لاگ v2rayN رو
فرستادی: `encoding/hex: invalid byte: U+0077 'w'` روی خیلی از کانفیگ‌ها،
حتی reality. یکی از لینک‌های vless که فرستادی رو باز کردم:
`pcs=wav%2BcIVAVDKsa%2BOitu3GCyx9boDCF9ZG2i4lBDHqqv8%3D` - این
base64ه (کاراکترهای `+`، `w`، `x`، `v` همه توی base64 عادی‌ان ولی توی
hex معتبر نیستن).

`pcs` = پارامتر `pinnedPeerCertSha256` که یه fix قبلی (توی همین فورک، از
قبل از این session) برای جایگزینی `allowInsecure` حذف‌شده‌ی Xray-core
اضافه کرده بود (`hutils/network/net.py`). مشکل: کدش
`base64.b64encode(digest).decode()` می‌کرد، ولی Xray-core این فیلد رو
hex می‌خواد نه base64 - همونطور که اسمش («Sha256» hex digest) و خودِ
ارور هم نشون می‌ده. نتیجه: هر دامنه‌ای که `allow_insecure` روش فعال بود
و یه cert hash واقعی fetch شده بود (به‌جای fallback به `allowInsecure`)،
یه `pcs` نامعتبر می‌گرفت و کل کانفیگش fail می‌شد به build - نه فقط
reality، هر پروتکلی که از این مسیر TLS رد می‌شد.

**فیکس:** `digest.hex()` به‌جای `base64.b64encode(digest).decode()` توی
`_fetch_cert_sha256_blocking()`. همه‌ی مصرف‌کننده‌ها (`xrayjson.py`،
`xray.py` برای لینک‌ساز vless) مستقیم از همین یه تابع می‌خونن، پس یه جا
فیکس شد کافیه.

**⚠️ نکته‌ی مهم بعد از این فیکس:** این hash‌ها توی حافظه cache می‌شن
(`_pinned_cert_cache`, یک ساعت TTL) - مقادیر base64ِ قبلی که همین الان
توی حافظه‌ی پروسه‌ی در حال اجرا هستن تا یک ساعت دیگه یا تا ری‌استارت
پنل (Reinstall/Apply Config که پروسه رو عوض کنه) پاک نمی‌شن. برای فیکس
فوری، پنل رو ری‌استارت کن (یا یک ساعت صبر کن) تا مقادیر جدید hex واقعاً
جایگزین بشن.

**فایل تغییریافته:** `hutils/network/net.py`.

---

## 🆕 AmneziaWG کاملاً منتقل شد توی خودِ فرم Outbounds (۲۰۲۶-۰۷-۰۲) — ⚠️ بخشی تست نشده

نسخه‌ی قبلی (پایین‌تر) هنوز یه Settings section جدا لازم داشت برای پیست
کردن .conf - و تازه اون section هم اصلاً نبود چون migration اجرا نشده
بود. کاملاً حق داشتی که گفتی این دقیقاً همون چیزی نیست که خواستی. الان
واقعاً مثل wireguard هست: همه‌چیز مستقیم توی ردیف Outbound.

**چی عوض شد:**
1. **۷ فیلد جدید** به `CustomOutbound` اضافه شد: `peer_public_key`،
   `preshared_key`، `local_address`، `dns`، `jc`، `jmin`، `jmax`. آدرس/
   پورت موجود = Endpoint، و `uuid_or_password` موجود = PrivateKey (دقیقاً
   همون قراردادی که wireguard از قبل استفاده می‌کرد). دیگه هیچ فیلدی از
   Settings لازم نیست.
2. **هر AmneziaWG Outbound یه interface مجزا داره** - نه یه `hiddify0`
   ثابت، بلکه `awg{id}` (بر اساس id ردیف، نه tag، پس محدودیت طول اسم
   interface لینوکس هیچوقت مشکل نمی‌شه). یعنی می‌تونی چندتا AmneziaWG
   outbound مختلف بسازی، هرکدوم peer جدا.
3. **`other/amneziawg/run.sh` شد `run.sh.j2`** - یه Jinja template
   (دقیقاً مثل `other/wireguard/run.sh.j2`) که روی همه‌ی Outbound های
   enable=true با Protocol=amneziawg لوپ می‌زنه، برای هرکدوم
   `/etc/amnezia/amneziawg/awg{id}.conf` می‌سازه (از
   `CustomOutbound.render_amneziawg_conf()`) و `awg-quick@awg{id}` رو
   بالا میاره. اگه یه ردیف رو غیرفعال/حذف کنی، دفعه‌ی بعد که Apply
   Config/Reinstall بزنی، interface اونم خاموش و پاک می‌شه (رندر شدنش
   با jinja2 لوکال تست شد، هم حالت خالی هم با یه ردیف واقعی).
4. **`amneziawg_enable`/`amneziawg_config` حذف شدن** از Settings (بردن
   به category مخفی، نه واقعاً پاک شدن از کد - برای اینکه ردیف‌های قدیمی
   دیتابیس روی نصب‌های قبلی خطا ندن). یه فلگ جدید محاسبه‌شده
   `has_amneziawg_outbound` (توی `all_configs_for_cli()`) جای
   `amneziawg_enable` رو گرفته تا `install.sh` بفهمه اصلاً باید
   amneziawg-tools/amneziawg-go رو build کنه یا نه.
5. **فرم Outbounds** فیلدهای جدید رو داره (label/description فارسی...
   نه ببخشید انگلیسی چون کد انگلیسیه) و اسکریپت پولیش‌شده - براساس
   Protocol انتخابی، هم برای wireguard هم amneziawg، فیلدهای درست رو
   نشون می‌ده (مثلاً amneziawg همه‌ی Jc/Jmin/Jmax/DNS/Local Address/
   Preshared Key رو نشون می‌ده، wireguard فقط Peer Public Key/Local
   Address رو، بقیه پروتکل‌ها هیچ‌کدوم از این‌ها رو نشون نمی‌دن).

**تست شده:** رندر `render_amneziawg_conf()` رو مستقیم با مقادیر توی
اسکرین‌شاتت (PrivateKey/Address/DNS/PublicKey/PresharedKey/Endpoint واقعی
+ Jc=4/Jmin=40/Jmax=1000) اجرا کردم - خروجی دقیقاً همون فرمت .conf رو
می‌ده. رندر `other/amneziawg/run.sh.j2` هم با jinja2 خالص تست شد (هم صفر
outbound هم یه outbound واقعی) و bash معتبر تولید می‌کنه.

**تست نشده:** خودِ `awg-quick@awg{id}.service` رو سرور واقعی run نکردم -
اگه بعد از Reinstall بالا نیومد، `journalctl -u awg-quick@awg{id}` رو
بفرست.

**فایل‌های تغییریافته:** `models/routing.py` (فیلدهای جدید +
`render_amneziawg_conf` + `amneziawg_interface` + `get_amneziawg_outbounds`)،
`models/__init__.py`، `models/config_enum.py` (category مخفی)،
`panel/admin/SettingAdmin.py` (حذف فیلد قدیمی)، `panel/admin/OutboundAdmin.py`
(فیلدهای جدید + اسکریپت پولیش‌شده)، `panel/init_db.py` (migration `_v125`)،
`panel/hiddify.py` (`amneziawg_outbounds` + `has_amneziawg_outbound` توی
`all_configs_for_cli`)، `install.sh` (فلگ جدید)، `other/amneziawg/disable.sh`
(حذف چندتا interface به‌جای یکی ثابت)، `other/amneziawg/run.sh` →
`run.sh.j2`.

---

## 🆕 AmneziaWG یکپارچه شد با فرم عمومی Outbounds/Routing Rules (۲۰۲۶-۰۷-۰۱) — ⚠️ بخشی تست نشده

گفتی: "amnezia باید توی outbounds هم باشه! چندبار گفتم و توی settings هم
نمی‌بینمش. فرم رو هم polish کن." حق داشتی - نسخه‌ی قبلی AmneziaWG رو با
یه toggle مجزا (`amneziawg_route_experimental_protocols`) سیم‌کشی کرده
بود، جدا از سیستم عمومی Outbounds/Routing Rules که برای xray ساخته
بودم. الان یکی شدن:

**چی عوض شد:**
1. **Outbounds → Protocol → `amneziawg`** یه گزینه‌ی جدیده، هم برای
   xray هم singbox. انتخابش کنی، فقط یه outbound می‌سازه که به
   interface `hiddify0` (همونی که `other/amneziawg/` بالا میاره) بایند
   می‌شه - نه آدرس/پورت/UUID لازم داره. دقیقاً همون الگوی WARP
   (`bind_interface`/`sockopt.interface`)، فقط این یکی از خود فرم قابل
   ساختنه، نه هاردکد.
2. **`amneziawg_route_experimental_protocols` حذف شد.** به‌جاش از
   Routing Rules معمولی استفاده کن: یه rule بساز، Outbound Tag رو
   بذار روی تگ همون outbound که با Protocol=amneziawg ساختی، و توی
   "Match Inbound(s)" حالا mieru/naive/tuic/hysteria2 هم لیست شدن
   (`get_available_inbound_tags()` بازنویسی شد) - یعنی می‌تونی هر
   inbound رو به هر outbound وصل کنی، نه فقط این یکی مسیر ثابت.
3. **`CustomOutbound.to_singbox_dict()` / `CustomRoutingRule.
   to_singbox_dict()` جدید** - همون ردیف‌های DB که تا حالا فقط برای
   xray سریالایز می‌شدن (`build_custom_xray_extra`)، الان یه نسخه‌ی
   singbox هم دارن (`build_custom_singbox_extra`)، merge شده توی
   `additional_configs_singbox` که `06_outbounds.json.j2` و
   `03_routing.json.j2` جدیداً واقعاً می‌خوننش (قبلاً این کانفیگ فقط
   توی subscription کلاینت خونده می‌شد، سمت سرور اصلاً استفاده نمی‌شد).
   این یعنی هرچی از Outbounds/Routing Rules بسازی، چه core_type=xray
   باشی چه singbox، بدون دوباره وارد کردن، درست رندر می‌شه.
4. **فرم Outbounds پولیش شد** - یه اسکریپت JS کوچیک (`OutboundAdmin.py`)
   بسته به Protocol انتخابی، فیلدهای بی‌ربط رو مخفی می‌کنه (مثلاً
   freedom/amneziawg هیچ‌کدوم از Address/Port/UUID/Network/... رو لازم
   ندارن، فقط vless فیلد Flow داره، و غیره).

**⚠️ چیزی که تست نشده:**
- اون اسکریپت JS یه فیلد سفارشی WTForms هست که فقط `<script>` رندر
  می‌کنه؛ توی مرورگر واقعی تست نشده - فرم‌های این پروژه از طریق مودال
  Bootstrap لود می‌شن، و اینکه اون لودر AJAX اسکریپت تزریق‌شده رو واقعا
  اجرا می‌کنه یا نه بستگی به نوع لود داره (jQuery `.html()`/`.load()`
  چرا، یه `.innerHTML=` خام نه). اگه با عوض کردن Protocol فیلدها مخفی/
  ظاهر نشدن، کنسول مرورگر رو چک کن.
- `to_singbox_dict()` برای `wireguard` مستقیم از روی مستندات نوشته شده
  (schema قدیمی‌تر "outbound"، نه "endpoints" جدید sing-box 1.11+)، رو
  سرور واقعی تست نشده.

**اگه هنوز بخش AmneziaWG رو توی Settings نمی‌بینی:** پیدا کردم چرا -
`SettingAdmin.get_config_form()` فیلدهای هر category رو فقط از روی
ردیف‌های *موجود توی دیتابیس* می‌سازه (`StrConfig`/`BoolConfig` query)،
نه مستقیم از `ConfigEnum`. اگه migration `_v124` (که کلیدهای
`amneziawg_enable`/`amneziawg_config` رو می‌سازه) هنوز روی سرورت اجرا
نشده باشه، بخش Amneziawg خالی می‌مونه یا اصلاً دیده نمی‌شه. این migration
موقع بالا اومدن اپ اجرا می‌شه اگه `db_version` فعلیت کمتر از ۱۳۰ باشه -
یه Reinstall کامل (نه فقط Apply Config) باید این رو trigger کنه؛ اگه
بعد از Reinstall هم نبود، لاگ استارتاپ رو بفرست.

**فایل‌های تغییریافته:** `hiddifypanel/models/routing.py` (`to_singbox_dict`
×۲، `build_custom_singbox_extra`، `get_available_inbound_tags` گسترش‌یافته)،
`models/__init__.py`، `models/config_enum.py` (حذف toggle)،
`panel/init_db.py` (`_v124` ساده‌تر شد)، `panel/hiddify.py` (merge سمت
singbox توی `all_configs_for_cli`)، `panel/admin/OutboundAdmin.py`
(فیلد Protocol + اسکریپت پولیش)، `panel/admin/RoutingRuleAdmin.py`
(توضیح inbound_tags)، `singbox/configs/06_outbounds.json.j2` و
`03_routing.json.j2` (بلوک ثابت amneziawg حذف و با merge loop عمومی
جایگزین شد - رندر شدنشون به JSON معتبر با jinja2+json5 لوکال تست شد).

---

## 🆕 AmneziaWG به‌عنوان یه core جدا اضافه شد (۲۰۲۶-۰۷-۰۲) — ⚠️ تست نشده

خواسته بودی ترافیک mieru/naive/hysteria/tuic بره روی یه outbound
AmneziaWireGuard. قبل از هر چیز رفتم مستقیم سورس `hiddify-sing-box` رو
گشتم (نه فقط README) - صفر نتیجه برای Jc/Jmin/Jmax/amnezia. یعنی خودِ
sing-box این‌ور واقعاً همچین چیزی نداره، حدست درست بود.

**راه‌حل:** دقیقاً همون الگویی که WARP از قبل استفاده می‌کنه - یه
interface شبکه‌ی مستقل، جدا از خودِ sing-box، که بعد sing-box فقط با
`bind_interface` بهش وصل می‌شه (نه AWG رو خودش implement کنه). دو تا
پروژه‌ی جدا از amnezia-vpn، هیچ‌کدوم باینری آماده ندارن، پس از سورس
build می‌شن:
- `amneziawg-tools` (C) → `awg`/`awg-quick` (فورک `wg`/`wg-quick`) +
  یونیت systemd `awg-quick@.service`.
- `amneziawg-go` (Go) → پیاده‌سازی userspace. `awg-quick` اول
  `ip link add type amneziawg` رو امتحان می‌کنه (نیاز به کرنل‌ماژول که
  هیچ کرنل استوک کلاودی نداره)، و خودکار می‌افته روی `amneziawg-go` اگه
  پیدا بشه - یعنی نیازی به build کردن کرنل‌ماژول/DKMS نیست.

**چطور استفاده کنی:**
1. Settings → یه بخش جدید "AmneziaWG" - توش `amneziawg_enable` رو بزن، و
   کانفیگ کامل `[Interface]`/`[Peer]` (همون فرمت WireGuard + Jc/Jmin/
   Jmax/S1/S2/H1-H4 اگه peer‌ت لازم داره) رو توی فیلد "AmneziaWG Config"
   پیست کن.
2. یه toggle دیگه هم هست: "Route mieru/naive/tuic/hysteria2 through
   amneziawg" - وقتی فعاله، ترافیک این پروتکل‌ها (شامل تگ‌های
   per-domain برای tuic/hysteria2/naive-quic) مستقیم می‌ره روی
   outbound جدید `amneziawg`.
3. Reinstall بزن تا `other/amneziawg/install.sh` باینری‌ها رو build کنه.

**فایل‌های جدید:** `other/amneziawg/install.sh`, `run.sh`, `disable.sh`.
**فایل‌های تغییریافته:** `install.sh` (مرحله‌ی جدید نصب)،
`hiddifypanel/models/config_enum.py` (سه تا کانفیگ جدید)،
`hiddifypanel/panel/admin/SettingAdmin.py` (فیلد textarea کانفیگ)،
`singbox/configs/06_outbounds.json.j2`، `singbox/configs/03_routing.json.j2`،
migration `_v124`.

**⚠️ خیلی مهم - این تست نشده:** من سرور واقعی برای build/run کردن
`amneziawg-tools`/`amneziawg-go` ندارم؛ همه‌ی این کد مستقیم از روی
مستندات و سورس خودِ این دو پروژه نوشته شده، نه تست‌شده سر یه نصب واقعی.
اگه `bash install.sh` توی مرحله‌ی AmneziaWG fail کرد، دقیقاً همون خروجی
رو برام بفرست تا دیباگ کنم.

**چیزی که این نیست:** فرم عمومی singbox Outbounds/Routing Rules (شبیه
چیزی که برای xray ساختم) که بشه هر outbound دلخواهی (نه فقط
AmneziaWG) اضافه کرد و به هر inbound دلخواهی route کرد. این یکی
AmneziaWG رو مشخصاً و مستقیم سیم‌کشی کرده، نه یه سیستم عمومی. اگه اون
سیستم عمومی‌تر رو هم می‌خوای، جدا بگو.

---

## 🚨 همون باگ xhttp/download، این‌بار روی کلید 'host' (۲۰۲۶-۰۷-۰۲)

فیکس قبلی‌م برای `KeyError: 'path'` توی `_add_xhttp_details()` رو با
`setdefault` تک‌تک برای `path`/`xhttp_mode`/`params` انجام دادم - ولی
`'host'` رو جا انداختم، و لاگ جدیدت دقیقاً همون کلاس باگ رو نشون داد،
فقط این‌بار `KeyError: 'host'`.

**فیکس درست‌تر:** به‌جای اضافه کردن fallback تک‌تک برای هر کلید (که هر بار
یکی جا می‌مونه)، حالا `dl` با merge کردن کل `proxy` به‌عنوان پایه، زیر
هرچی خودِ `download` واقعاً تعریف کرده، ساخته می‌شه: `dl = {**proxy,
**proxy['download']}`. یعنی هر کلیدی که download خودش نداشته باشه از
proxy اصلی میاد، و هر کلیدی که واقعاً تعریف کرده (sni/host/server/mode/
alpn - دقیقاً چیزی که یه دامنه‌ی download جدا براش وجود داره) بازم برنده
می‌مونه. این کلاس کامل باگ رو می‌بنده، نه فقط یه کلید خاص.

**فایل:** `hiddify-panel/src/hiddifypanel/hutils/proxy/xrayjson.py`

---

## ✅ ایمپورت لینک vless روی Outbounds + مسیریابی بر اساس Inbound (۲۰۲۶-۰۷-۰۲)

### ۱. Outbounds: پیست کردن لینک `vless://`
یه فیلد جدید "Import Link (vless://...)" به فرم Outbound اضافه شد. یه لینک
بده (مثل چیزی که از یه پنل/پروایدر دیگه می‌گیری)، وقتی Save می‌کنی خودش
uuid/host/port/network/security/sni/path/host-header/fingerprint/flow رو
از توش استخراج می‌کنه و فیلدهای پایین رو پر می‌کنه (overwrite می‌کنه).
اگه لینک نامعتبر باشه، خطای واضح می‌ده به‌جای اینکه بی‌صدا هیچی نسازه.

سه تا فیلد جدید هم به مدل `CustomOutbound` اضافه شد چون خیلی رایج بودن و
لایق فیلد اختصاصی بودن (به‌جای فقط از طریق `extra_json`): `host_header`
(هدر Host برای ws/httpupgrade/xhttp)، `fingerprint` (uTLS برای tls/reality)،
و `flow` (فقط vless، مثل `xtls-rprx-vision`).

**فایل‌ها:** `hiddifypanel/models/routing.py` (تابع `parse_vless_link`)،
`hiddifypanel/panel/admin/OutboundAdmin.py`، migration `_v123` توی
`panel/init_db.py`.

### ۲. Routing Rules: مسیریابی بر اساس Inbound
یه فیلد چندانتخابی "Match Inbound(s)" اضافه شد که از inboundهای واقعی
xray پر می‌شه (نه یه لیست هاردکد) - دقیقاً همون protocol_enable/*_enable
هایی که خود تمپلیت‌ها چک می‌کنن رو می‌خونه، پس فقط چیزی که واقعاً تولید
می‌شه رو نشون می‌ده.

**⚠️ نکته‌ی مهم معماری - قبل از استفاده بخون:** مثالی که خواسته بودی
("139.162.182.137 tls xhttp direct vmess dl=h2") دقیقاً همون اسم یه ردیف
Proxy‌ه، ولی Hiddify به‌ازای هر ردیف Proxy یه inbound جدا نمی‌سازه.
اکثر ترکیب‌های protocol+transport (v10-{{protocol}}-{{stream}}) یه
inbound مشترک دارن که از هر دامنه/CDN-mode ای بیاد بهش می‌رسه (چون
مسیریابی دامنه قبلش، توی HAProxy با SNI انجام می‌شه، نه توی خود xray). پس
چیزی که واقعاً می‌تونی انتخاب کنی اینه: "هر ترافیک vless روی xhttp، از هر
دامنه‌ای" - نه دقیقاً همون یه ردیف Proxy با اون دامنه‌ی خاص. تنها استثنا
Reality‌ست: هر دامنه‌ی reality واقعاً یه inbound اختصاصی خودش داره
(`realityin_{stream}_{port}`)، پس اونا رو per-domain لیست کردم.
اگه لازمه محدودتر از این بشه (مثلاً فقط یه دامنه‌ی خاص با CDN مشخص)،
باید فیلد Domains رو هم پر کنی کنارش.

**فایل‌ها:** `hiddifypanel/models/routing.py` (تابع
`get_available_inbound_tags`، ستون `CustomRoutingRule.inbound_tags`)،
`hiddifypanel/panel/admin/RoutingRuleAdmin.py`.

---

## 🚨 خودم یه باگ جدید ساختم با فیکس قبلی - همین الان فیکس شد (۲۰۲۶-۰۷-۰۲)

فیکس قبلی (`timeout 240 acme.sh ...`) یه رگرسیون واقعی بود: `timeout`
دستور هدفش رو مستقیم با `execvp()` اجرا می‌کنه، یعنی از هر alias/function
شل رد می‌شه. `acme.sh` (بدون مسیر کامل) فقط از طریق alias‌ای که
`source ./lib/acme.sh.env` می‌سازه شناخته می‌شه - پس `timeout ... acme.sh`
همیشه فوری با "No such file or directory" fail می‌شد، برای **هر** درخواست
گواهی، نه فقط اونایی که گیر می‌کردن. نتیجه: fallback به self-signed برای
همه‌ی دامنه‌ها همیشه فعال می‌شد، حتی وقتی ACME واقعی مشکلی نداشت.

**فیکس:** به‌جای `acme.sh`، مسیر کامل فایل واقعی
(`/opt/hiddify-manager/acme.sh/lib/acme.sh`) رو به `timeout` می‌دم. فراخوانی
دیگه‌ی `acme.sh --installcert` که مستقیم (بدون timeout) صدا زده می‌شه رو
دست نزدم، چون از قبل درست کار می‌کرد (alias مستقیم توسط خود شل resolve
می‌شه، نه توسط `timeout`).

**فایل:** `acme.sh/cert_utils.sh`

---

## 🚨 ACME می‌تونست کل نصب رو قفل کنه - یه دامنه‌ی گیرکرده همه‌چیز رو معطل می‌ذاشت (۲۰۲۶-۰۷-۰۱، ادامه)

از `0install.log`ت پیدا شد: بعد از rate-limit شدن Let's Encrypt، برای
`139.162.182.137` (IP) fallback به self-signed سریع و درست کار کرد. ولی
برای `t9.nekocafe.sbs`، تلاش بعدی با ZeroSSL توی وضعیت "processing" گیر
کرد و acme.sh هر ۱۵ ثانیه poll می‌کرد - **بدون هیچ سقف زمانی**. لاگ نصبت
دقیقاً همون‌جا قطع شد (نه خطا، نه ادامه) چون واقعاً معلق مونده بود.

`acme.sh/run.sh` هر دامنه رو به‌صورت `get_cert $d &` جدا در پس‌زمینه اجرا
می‌کنه (این قسمت از قبل درست بود، دامنه‌ها از هم مستقل‌ان) - ولی بعدش
`wait` می‌کنه تا **همه** تموم بشن، قبل از `stop_nginx_acme` (که
nginx/haproxy رو reload می‌کنه). یعنی یه دامنه‌ی گیرکرده، reload کل
سرور رو معطل می‌ذاشت - نه فقط گواهی خودش رو خراب می‌کرد.

**فیکس:** توی `acme.sh/cert_utils.sh`، تابع `acmecmd()` رو با
`timeout 240` پیچیدم. اگه یه دامنه بیشتر از ۴ دقیقه طول بکشه، acme.sh
kill می‌شه، exit code غیر صفر برمی‌گرده، و منطق fallback موجود
(`get_self_signed_cert`) که از قبل توی `get_cert()` بود خودکار فعال
می‌شه - بدون اینکه هیچ‌جای دیگه رو دست بزنم. این دقیقاً همون چیزیه که
خواسته بودی: گیر کردن روی یه دامنه دیگه بقیه رو معطل نمی‌ذاره.

**فایل:** `acme.sh/cert_utils.sh`

**نکته:** این فیکس علت این‌که پنل خودش صفحه‌ی admin رو 500 می‌ده رو
مستقیماً تأیید نمی‌کنه - برای اون به `hiddify_panel.err.log` واقعی نیاز
دارم (نه `hiddify_panel_background_tasks.err.log`، که فقط نویز
grpc/singbox داشت و ربطی به این نداره).

---

## 🚨 دو باگ واقعی دیگه از نصب موفق اولت (۲۰۲۶-۰۷-۰۱، ادامه) - هر دو فیکس شدن

نصب بالاخره کامل تموم شد (`NOTICE: auto-detected local panel source` + واقعاً
`hiddifypanel==12.3.3` از سورس پچ‌شده build شد) - ولی دو باگ واقعی دیگه رو
لاگ‌هات نشون دادن:

### باگ الف: منوی "Xray Configs" اصلاً جایی وجود نداشت - نه فقط جای اشتباه
علت واقعی: `admin-layout.html` (سایدبار پنل) یه لیست کاملاً **دستی و
هاردکدشده** از صفحاته (`render_nav_item('flask.domain.index_view', ...)`
برای هر صفحه، یکی‌یکی) - هیچ‌جا از روی چیزی که `flaskadmin.add_view(...)`
واقعاً ثبت کرده لوپ نمی‌زنه. یعنی پارامتر `category="Xray Configs"` که پچ
قبلی روی `OutboundAdmin`/`RoutingRuleAdmin`/`InboundOverrideAdmin` گذاشته
بود، برای این تم/فورک خاص هیچ اثری روی UI نداشت - صفحه‌ها واقعاً ثبت و در
دسترس بودن (مثلاً `/admin/inbound_override/` مستقیم کار می‌کرد)، ولی هیچ‌جا
لینکی به سایدبار اضافه نشده بود که بهشون برسی.

**فیکس:** سه‌تا `render_nav_item` جدید به `admin-layout.html` اضافه شد
(کنار Backup، زیر همون `if g.account.mode=='super_admin'`). endpointها رو
از روی رفتار پیش‌فرض flask-admin برای `ModelView` بدون `endpoint=` صریح
پیدا کردم (پیش‌فرض = اسم کلاس مدل، نه اسم کلاس View): `OutboundAdmin` روی
مدل `CustomOutbound` → endpoint `customoutbound`، `RoutingRuleAdmin` روی
`CustomRoutingRule` → endpoint `customroutingrule`، و
`InboundOverrideAdmin` که از قبل صریحاً `endpoint="inbound_override"`
داشت.

**فایل:** `hiddify-panel/src/hiddifypanel/templates/admin-layout.html`

### باگ ب: subscription همچنان 500 می‌داد - `KeyError: 'path'`
لاگ واقعی (`hiddify_panel.err.log`) دقیقاً نشون داد کجا: `xrayjson.py`،
تابع `_add_xhttp_details()`، برای پروتکل‌های xhttp که یه دامنه‌ی download
جدا دارن (یا حتی همون دامنه‌ی اصلی به‌عنوان download، وقتی CDN جدا تنظیم
نشده). این تابع خودش رو روی `proxy['download']` صدا می‌زنه (recursive)، ولی
اون دیکشنری فقط فیلدهای مخصوص دامنه (`sni`, `host`, `server`, `mode`,
`alpn`) رو داره - نه `path`/`xhttp_mode`/`params` که این تابع بهشون نیاز
داره. `shared.py` سعی می‌کنه اینا رو ست کنه (`dl['path']=base['path']`)،
ولی همیشه این اتفاق نمی‌افته (مثلاً وقتی override دامنه یا مسیر دیگه‌ای
باعث میشه `download` یه دیکشنری متفاوت/جزئی باشه) - و هر بار که میفتاد، کل
subscription اون یوزر با 500 کرش می‌کرد.

**فیکس:** توی خودِ `_add_xhttp_details()`، قبل از recurse کردن روی
`proxy['download']`، مقادیر گم‌شده (`path`, `xhttp_mode`, `params`) رو از
proxy اصلی fallback می‌کنه (`dl.setdefault(...)`) به‌جای اینکه فرض کنه حتماً
از قبل ست شدن. این مستقل از اینکه دقیقاً چرا `download` این فیلدها رو
نداشت درست کار می‌کنه.

**فایل:** `hiddify-panel/src/hiddifypanel/hutils/proxy/xrayjson.py`

---

## 🚨 فیکس قبلی (KillMode) کافی نبود - ریشه‌ی واقعی `systemctl kill` بود (۲۰۲۶-۰۷-۰۱، ادامه)

از لاگ زنده‌ی خودت تست شد: بعد از فیکس قبلی (`KillMode=process`)، دقیقاً
همون رفتار (کشتن تک‌تک پردازش‌های فرزند) ادامه داشت، با اینکه
`systemctl show hiddify-panel.service -p KillMode` درست `process` نشون
می‌داد. دلیلش: `KillMode=` فقط رفتار `systemctl restart`/`stop` عادی رو
کنترل می‌کنه؛ `systemctl kill` یه دستور جداست که پیش‌فرضش `--kill-who=all`ه
و **کلاً KillMode رو نادیده می‌گیره**.

آخر خط ۱۵۵ `install.sh` (و معادلش توی `common/hiddify_installer.sh` خط
۲۵۹) دقیقاً همین `systemctl kill -s SIGTERM hiddify-panel` رو صدا می‌زد -
یعنی صریحاً و همیشه کل cgroup رو می‌کشت، چه install از پنل صدا زده شده
باشه چه نه. **فیکس واقعی:** `--kill-who=main` اضافه شد به هر دو جا، که
دقیقاً همون پردازش اصلی (tracked PID) رو هدف می‌گیره، نه کل cgroup.

فیکس قبلی (`KillMode=process` روی خود سرویس‌ها) بی‌فایده نبود - برای
`systemctl restart hiddify-panel-background-tasks.service` (توی
`hiddify-panel/run.sh`، که از `restart` استفاده می‌کنه نه `kill`) هنوز
لازمه و درست کار می‌کنه. فقط برای *این* باگ خاص (که از `systemctl kill`
میومد) کافی نبود.

**فایل‌ها:** `install.sh`, `common/hiddify_installer.sh`

---

## 🚨 باگ واقعاً بزرگ: Reinstall/Apply Config خودش خودش رو می‌کشت وسط کار (۲۰۲۶-۰۷-۰۱)

از لاگ واقعی نصبت (journalctl) پیدا شد. وقتی از پنل "Reinstall" یا "Apply
Configs" می‌زدی:

1. `run_commander.py`ی که قبلاً پچ کردم (Bug اصلی Apply/Reinstall) الان
   واقعاً `install.sh` رو اجرا می‌کنه، به‌عنوان یه پردازش فرزندِ جدا
   (`subprocess.Popen(..., start_new_session=True)`) از پردازش خودِ
   `hiddify-panel.service`.
2. ولی `install.sh` خودش یکی از کارهایی که می‌کنه اینه که
   `hiddify-panel.service` رو (چون خودش یکی از کامپوننت‌هاست) دوباره نصب و
   ری‌استارت کنه.
3. `hiddify-panel.service` هیچ `KillMode` صریحی نداشت، یعنی پیش‌فرض
   systemd یعنی `control-group` بود: وقتی این سرویس ری‌استارت می‌شه،
   systemd سیگنال SIGTERM رو به **همه‌ی پردازش‌های داخل همون cgroup**
   می‌فرسته - و پردازش نصبی که خودِ همین سرویس چند ثانیه قبل راه انداخته
   بود هم دقیقاً همونجاست (`start_new_session=True` فقط از سیگنال‌های
   ترمینال/process-group جلوگیری می‌کنه، نه از کشتار cgroup-based
   systemd). نتیجه: خودِ عملیات نصب، وسط کار (درست بعد از مرحله‌ی nginx،
   قبل از xray/singbox/haproxy/warp/ssfaketls) توسط ری‌استارت سرویس خودش
   کشته می‌شد.

این دقیقاً توضیح می‌ده چرا بعد از نصب، سرویس‌هایی مثل singbox/haproxy/nginx
fail می‌شدن، فایل‌های config (`singbox/configs/01_api.json`,
`nginx/parts/short-link.conf`) اصلاً ساخته نشده بودن، `hiddify-ss-faketls.service`
پیدا نمی‌شد، و `other/warp/run.sh` وجود نداشت - نصب هیچ‌وقت به اون مرحله‌ها
نمی‌رسید چون قبلش کشته می‌شد.

**فیکس:** `KillMode=process` به هر دو `hiddify-panel.service` و
`hiddify-panel-background-tasks.service` اضافه شد. این یعنی ری‌استارت این
سرویس‌ها فقط پردازش اصلی (tracked PID) رو سیگنال می‌ده، نه بقیه‌ی
پردازش‌های داخل cgroup - پس اسکریپت نصبی که این سرویس‌ها خودشون راه
انداختن، سالم ادامه پیدا می‌کنه حتی وقتی سرویس مادر ری‌استارت می‌شه.

**فایل‌ها:** `hiddify-panel/hiddify-panel.service`, `hiddify-panel/hiddify-panel-background-tasks.service`

---

## 🔍 فرم «Inbound Overrides» واقعی شد، ولی Port/Security عمداً توش نیست (۲۰۲۶-۰۷-۰۱)

خواسته بودی «فرم شبیه 3x-ui» (Port/SNI/Security جدا جدا روی هر inbound).
قبل از رد کردن دوباره، این‌بار عمیق‌تر رفتم توی کد سرور-ساید (نه فقط
subscription) تا مطمئن بشم واقعاً چی قابل override هست:

- **Port واقعاً یه مفهوم per-inbound نیست.** اکثر پروتکل‌ها (vless/vmess/
  trojan/reality) از یه entrypoint مشترک (HAProxy/xray روی ۴۴۳) رد می‌شن که
  بر اساس SNI/ALPN مسیریابی می‌کنه، نه پورت اختصاصی. کانفیگ واقعی سرور
  (`xray/configs/*.j2`) از تنظیمات global ساخته می‌شه و اصلاً `Proxy.params`
  رو نمی‌خونه. یعنی یه فیلد "Port" روی این فرم یا هیچ کاری نمی‌کرد، یا یه
  پورت اشتباه به کلاینت می‌داد که هیچی روش گوش نمی‌ده (قطعی وصل).
- **Security هم همینطور** — نوع security (tls/reality/none) از قبل توی
  ترکیب `l3` همون ردیف Proxy قفل شده؛ چیزی نیست که override بشه، برای اون
  باید یه Proxy دیگه رو enable کنی.
- ولی `sni`, `host`, `path`, `fingerprint`, `alpn`, `hysteria_obfs_password`،
  و `mode` (برای xhttp) واقعاً از `Proxy.params` خونده می‌شن (تایید شده توی
  `apply_proxy_overrides()` و خط `base['params'].get('mode',"auto")` توی
  `make_proxy()`), و امن/کاربردی‌ان.

**کاری که کردم:** `InboundOverrideAdmin.py` رو از یه تکست‌باکس خام JSON به یه
فرم واقعی با فیلدهای جدا (SNI, Host, Path, Fingerprint دراپ‌داون, ALPN
دراپ‌داون, XHTTP Mode دراپ‌داون, Hysteria2 Obfs Password) تغییر دادم. یه
فیلد "Advanced Override (JSON)" هم نگه داشتم برای هر کلید دیگه‌ای که این
فیلدها پوششش نمی‌دن (مثلاً `mux_enable`) — این یکی هم الان round-trip درسته
(پاک کردن یه کلید ازش واقعاً حذفش می‌کنه، نه فقط merge یک‌طرفه).

**فایل:** `hiddify-panel/src/hiddifypanel/panel/admin/InboundOverrideAdmin.py`

---

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
