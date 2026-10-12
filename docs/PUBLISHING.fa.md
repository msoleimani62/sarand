# انتشار در PyPI

sarand در PyPI با نام **`sarand-cli`** منتشر می‌شود (نام `sarand` مال یک پروژه‌ی
بی‌ربط است). دستور همان `sarand` و بسته‌ی import همان `sarand` می‌ماند. انتشار با
*trusted publishing* انجام می‌شود: GitHub هویت خودش را به PyPI ثابت می‌کند و
**هیچ رمز یا توکنی در هیچ جا ذخیره نمی‌شود**.

workflow در `.github/workflows/release.yml` است. برای هر پلتفرم یک wheel می‌سازد
(Linux با x86_64 و aarch64، macOS با arm64 و x86_64، Windows با x64؛ هر کدام برای
همه‌ی نسخه‌های پایتون از ۳.۱۰ به بالا کار می‌کند) و یک sdist، wheelها را روی سه
سیستم برای آزمون دود نصب می‌کند و بعد منتشر می‌کند.

## راه‌اندازی یک‌باره (حدود ۲۰ دقیقه، همه از مرورگر)

**۱. دو حساب.** یکی در <https://pypi.org/account/register/> و یکی در
<https://test.pypi.org/account/register/> بسازید (دو سایت جدا با حساب‌های جدا).
ایمیل را در هر دو تأیید کنید و وقتی خواسته شد احراز هویت دومرحله‌ای را روشن کنید
(برنامه‌ی authenticator)؛ PyPI برای انتشار آن را لازم دارد.

**۲. ثبت پروژه در TestPyPI.** صفحه‌ی
<https://test.pypi.org/manage/account/publishing/> را باز کنید، بخش *Add a new
pending publisher*، تب *GitHub*، و دقیقاً این‌ها را پر کنید:

| فیلد | مقدار |
|---|---|
| PyPI Project Name | `sarand-cli` |
| Owner | `msoleimani62` |
| Repository name | `sarand` |
| Workflow name | `release.yml` |
| Environment name | `testpypi` |

*Add* را بزنید. pending publisher اسم را **رزرو نمی‌کند**؛ اسم با اولین آپلود موفق
مال شما می‌شود.

**۳. همین در PyPI.** صفحه‌ی <https://pypi.org/manage/account/publishing/> را باز کنید
و همان فیلدها را پر کنید، ولی *Environment name* = `pypi`.

**۴. دو environment در GitHub.** در مخزن: *Settings ← Environments ← New environment*.
`testpypi` را بسازید (چیز دیگری لازم نیست) و `pypi` را. روی `pypi` گزینه‌ی
*Required reviewers* را بزنید و خودتان را اضافه کنید: هر انتشار واقعی قبل از
آپلود منتظر تأیید شما می‌ماند.

## تمرین روی TestPyPI

۱. مخزن ← *Actions* ← *Release* ← *Run workflow* (شاخه‌ی `main`)، گزینه‌ی
*Also upload to TestPyPI* را تیک بزنید و اجرا کنید.
۲. صبر کنید: پنج build، sdist و آزمون‌های دود. بعد *Publish to TestPyPI* شروع می‌شود
(برای `testpypi` تأیید لازم نیست).
۳. <https://test.pypi.org/project/sarand-cli/> را باز کنید: صفحه، README و فایل‌ها
باید باشند.
۴. در یک محیط موقت نصب کنید:

   ```bash
   python3 -m venv /tmp/try && /tmp/try/bin/pip install \
     -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple \
     sarand-cli && /tmp/try/bin/sarand --version
   ```

   (`--extra-index-url` اجازه می‌دهد وابستگی‌ها از PyPI واقعی بیایند.)

یک نسخه فقط یک‌بار روی یک index آپلود می‌شود؛ تمرین از `skip-existing` استفاده
می‌کند، پس اجرای دوباره‌اش شکست نمی‌خورد.

## انتشار واقعی

۱. commit ریلیز (ورودی CHANGELOG و افزایش نسخه) را مثل هر ریلیز بسازید و منتظر CI
سبز بمانید.
۲. `python3 scripts/release.py tag && git push origin vX.Y.Z` تگ را می‌سازد و
push می‌کند. اسم تگ باید برابر نسخه‌ی `pyproject.toml` باشد؛ workflow تگ ناهمخوان
را رد می‌کند.
۳. *Actions ← Release*: وقتی buildها سبز شدند، *Publish to PyPI* منتظر تأیید شما
می‌ماند (*Review deployments ← pypi ← Approve*).
۴. <https://pypi.org/project/sarand-cli/> را باز کنید و بررسی کنید:

   ```bash
   pipx install sarand-cli && sarand --version
   ```

فایل آپلودشده را می‌شود *yank* کرد (از نصب‌کننده‌ها پنهان می‌شود) ولی هرگز
جایگزین یا برای استفاده‌ی دوباره پاک نمی‌شود: اشتباه را نسخه‌ی بعدی درست می‌کند.

## اگر چیزی شکست خورد

| نشانه | علت معمول |
|---|---|
| `invalid-publisher` یا «no matching publisher» | یکی از فیلدهای فرم PyPI با این مخزن نمی‌خواند: owner، repository، اسم فایل `release.yml` یا اسم environment (`pypi` / `testpypi`). حساس به بزرگی و کوچکی حروف‌اند. |
| اسم «گرفته‌شده» رد می‌شود | کسی قبل از اولین آپلود `sarand-cli` را ثبت کرده؛ اسم دیگری انتخاب کنید و `name` در `pyproject.toml` و دو فرم را عوض کنید. |
| `Publish` رد می‌شود (skipped) | انتشار با تگ نیاز به تگ `v*` دارد؛ job مربوط به TestPyPI به تیک *Also upload to TestPyPI* نیاز دارد. |
| job ی `check` روی تگ شکست می‌خورد | تگ برابر `v` + نسخه‌ی `pyproject.toml` نیست. تگ را پاک کنید و بعد از اصلاح نسخه دوباره تگ بزنید. |
| build یک wheel شکست می‌خورد | همان job ی ماتریس را بخوانید؛ بقیه‌ی پلتفرم‌ها تمام می‌شوند (`fail-fast` خاموش است) ولی تا همه‌ی buildها و آزمون‌های دود سبز نشوند چیزی منتشر نمی‌شود. |
| `File already exists` | آن نسخه از قبل روی index هست؛ نسخه را بالا ببرید. |

فرم trusted publisher نمی‌تواند workflow ی *reusable* را نام ببرد: jobهای انتشار
باید در خود `release.yml` بمانند.
