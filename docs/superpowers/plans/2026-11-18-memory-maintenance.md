# Hafıza Bakımı (memory-maintenance) Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Oturumun ilk turuna N günde bir (varsayılan 7) tek satır hafıza bakım hatırlatması enjekte etmek ve bakım prosedürünü `memory-maintenance` skill'i olarak kaydetmek.

**Architecture:** Saf stdlib'li yeni `.hermes-plugin/maintenance.py` state oku/yaz, interval hesabı ve hatırlatma satırı üretimini taşır; `__init__.py` bu modülü `_sibling` ile yükler ve mevcut `_pipeline`'ın mtime kapısının **dışında** koşan bir bakım adımıyla satırı roster'a ekler (takvim kontrolü zaman temellidir, mtime'a bağlanamaz). Skill ayrı bir `SKILL.md` olarak yazılır, `register()` ikinci skill olarak kaydeder. `config.py` değişmez: `parse_team_config` bilinmeyen anahtarları zaten geçirir, blok doğrulaması özellik mantığıdır.

**Tech Stack:** Python 3 (yalnız stdlib: json, datetime, pathlib, os, re, importlib), pytest + pytest-mock (yalnız dev), Hermes hook API (`pre_llm_call`, `register_skill`).

**Spec:** `docs/superpowers/specs/2026-11-18-memory-maintenance-design.md`

## Global Constraints

- Runtime kodu yalnız stdlib (os, re, json, pathlib, importlib) — yeni Python bağımlılığı YASAK; manifest'e hiçbir dependency eklenmez.
- Enjekte edilen toplam metin hook bütçesi (~1KB) aşılmayacak; roster'ın 1024 karakter bütçesi zaten ayrı (roster.py).
- Hook/pipeline asla raise etmez: her hata warn + atla.
- State dosyası ~/.hermes/software-team/maintenance.json; ilk çalıştırmada oluşur, var olan asla ezilmez (mevcut ensure_user_config deseni).
- team.jsonc kullanıcınındır: maintenance bloğu yoksa interval_days=7; bozuksa uyarı + 7.
- Test reçetesi: REPO=/home/yelsoft/.hermes/hermes-agent SP=$(python3 -c "import sysconfig;print(sysconfig.get_paths()['purelib'])") HERMES_AGENT_REPO=$REPO PYTHONPATH="$SP:$REPO" uv run --with pytest --with pytest-mock python -m pytest tests/ -q
- Skill kaydı: ctx.register_skill('memory-maintenance', Path(skill_md), description=...) — Path zorunlu, description frontmatter'dan okunur.

## Review Focus

1. `interval_days` = 0 / negatif / bool / string → uyarı + 7 (bozuk değer hatırlatmayı sessizce sonsuza erteleyemez). → Task 1, `test_parse_interval_rejects_invalid_values`.
2. `maintenance.json` elle düzenlenip bozulmuşsa → "hiç hatırlatılmamış" sayılır, uyarı loglanır, ilk ateşlemede yeniden yazılır; çökme yok. → Task 1, `test_read_state_corrupt_variants`.
3. `memories/` dizini yoksa veya bilinen dosyalar eksikken % hesabı: dizi yok → `; hafıza %X dolu` cümlesi tamamen atlanır; MEMORY.md yok → USER.md üzerinden hesap (bütçe haritası); bilinen dosyaların hiçbiri yok → %0; haritada olmayan `*.md` yüzdeyi bozamaz. → Task 1, `test_fill_percent_missing_dir` / `test_fill_percent_empty_dir` / `test_fill_percent_user_file_alone`.
4. Sıçrama tarihi/saat dilimi: state'teki naif tarih UTC sayılır, gelecek tarih 0 güne sıkıştırılır — tarih kayması hatırlatmayı ne sonsuza susturur ne döngüye sokar. → Task 1, `test_compute_days_since_naive_treated_as_utc` / `test_compute_days_since_future_clamps_zero`.
5. İlk çalıştırma (blok yok + maintenance.json yok): hatırlatma ilk turda "henüz bakım kaydı yok" ifadesiyle ateşlenir ve state yazılır → sonraki N gün susar. → Task 1, `test_is_due_never_reminded`; Task 2, `test_pipeline_appends_reminder_when_due`.

---

### Task 1: maintenance.py — state, interval, hatırlatma satırı (TDD)

**Files:**
- Create: `.hermes-plugin/maintenance.py`
- Modify: `tests/conftest.py:27-32` — kayıt demetine `("st_maintenance", "maintenance.py")` satırı ekle
- Test: `tests/test_maintenance.py`

**Interfaces:**
- Consumes: yok (yalnız stdlib: `json`, `datetime`, `pathlib`)
- Produces: Task 2 ve 4'ün kullandığı kesin imzalar:

```python
DEFAULT_INTERVAL_DAYS = 7
_FILE_BUDGETS = {"MEMORY.md": 2200, "USER.md": 1375}  # dosya başına karakter bütçesi (% hesabının böleni)

def parse_maintenance_block(raw: object) -> tuple[int, str | None]:
    # (interval_days, warning). raw None / interval_days anahtarı yok → (7, None).
    # Bozuk: dict değil / int değil / bool / < 1 → (7, uyarı).

def read_state(state_path: Path) -> tuple[str | None, str | None]:
    # (last_reminded ISO, warning). Dosya yok → (None, None).
    # Bozuk JSON / dict değil / last_reminded yok / str değil /
    # datetime.fromisoformat ile parse edilemez → (None, uyarı).

def compute_days_since(iso: str, now: datetime) -> int:
    # Tam gün farkı, 0'a sıkıştırılmış (gelecek tarih → 0).
    # Naif tarihler UTC sayılır; iki taraf da UTC'ye normalize edilir (DST güvenli).

def is_due(last_reminded: str | None, interval_days: int, now: datetime) -> bool:
    # None → True (ilk çalıştırma hatırlatır). Yoksa gün farkı >= interval_days.

def memory_fill_percent(memories_dir: Path) -> int | None:
    # Dizi yok → None. _FILE_BUDGETS'teki her dosya için karakter/bütçe yüzdesi
    # (utf-8, errors="replace"; okuma OSError'u olan dosya atlanır); sonuç en dolu
    # dosyanın yüzdesi (min(100, round(...))). Bütçe haritasında olmayan *.md
    # yüzdeye girmez; bilinen dosyaların hiçbiri yok → 0.

def build_reminder(days: int | None, fill_percent: int | None) -> str:
    # Tek satır Türkçe hatırlatma. days None → "henüz bakım kaydı yok";
    # fill_percent None → "; MEMORY %X dolu" cümlesi atlanır.

def update_last_reminded(state_path: Path, iso: str) -> None:
    # parent.mkdir(parents=True, exist_ok=True); dosya yoksa "x" moduyla oluştur
    # (O_EXCL: yarışta var olan dosya ezilmez), FileExistsError → normal güncelleme.
    # İçerik: json.dumps({"last_reminded": iso}, indent=2) + "\n".
```

"Var olan asla ezilmez" yorumu: oluşturma yalnız `x` moduyla yapılır (ensure_user_config deseni); güncelleme yazımı plugin'in kendi yazımıdır — `read_state` asla yazmaz.

- [ ] **Step 1: Failing testleri yaz** — `tests/test_maintenance.py` (unittest.mock tercih edilir ama bu testler yalnız tmp_path kullanır) + conftest kaydı.

```python
import json
from datetime import datetime, timedelta, timezone

import st_maintenance as m

def test_parse_interval_defaults_when_block_missing():
    assert m.parse_maintenance_block(None) == (7, None)
    assert m.parse_maintenance_block({}) == (7, None)

def test_parse_interval_accepts_valid():
    assert m.parse_maintenance_block({"interval_days": 3}) == (3, None)

def test_parse_interval_rejects_invalid_values():
    for bad in (0, -1, 2.5, "7", True, [], None):
        days, warning = m.parse_maintenance_block({"interval_days": bad})
        assert days == 7 and warning and "interval_days" in warning

def test_parse_interval_rejects_non_object_block():
    days, warning = m.parse_maintenance_block([])
    assert days == 7 and warning

def test_read_state_missing_file(tmp_path):
    assert m.read_state(tmp_path / "yok.json") == (None, None)

def test_read_state_roundtrip(tmp_path):
    iso = "2026-11-11T12:00:00+00:00"
    p = tmp_path / "maintenance.json"
    p.write_text(json.dumps({"last_reminded": iso}))
    assert m.read_state(p) == (iso, None)

def test_read_state_corrupt_variants(tmp_path):
    p = tmp_path / "maintenance.json"
    for text in ("{ not json", "[]", '{"other": 1}',
                 '{"last_reminded": 5}', '{"last_reminded": "dün"}'):
        p.write_text(text)
        last, warning = m.read_state(p)
        assert last is None and warning

def test_compute_days_since_whole_days():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    assert m.compute_days_since("2026-11-11T12:00:00+00:00", now) == 7
    assert m.compute_days_since("2026-11-11T12:30:00+00:00", now) == 6  # 6 gün 23.5 saat

def test_compute_days_since_naive_treated_as_utc():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    assert m.compute_days_since("2026-11-11T12:00:00", now) == 7

def test_compute_days_since_future_clamps_zero():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    assert m.compute_days_since("2026-11-25T12:00:00+00:00", now) == 0

def test_is_due_never_reminded():
    assert m.is_due(None, 7, datetime.now(timezone.utc)) is True

def test_is_due_boundary():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    assert m.is_due("2026-11-11T12:00:00+00:00", 7, now) is True   # tam 7 gün
    assert m.is_due("2026-11-11T12:00:01+00:00", 7, now) is False  # 7 günden az

def test_fill_percent_missing_dir(tmp_path):
    assert m.memory_fill_percent(tmp_path / "yok") is None

def test_fill_percent_empty_dir(tmp_path):
    (tmp_path / "memories").mkdir()
    assert m.memory_fill_percent(tmp_path / "memories") == 0

def test_fill_percent_single_file(tmp_path):
    d = tmp_path / "memories"; d.mkdir()
    (d / "MEMORY.md").write_text("a" * 2112)  # 2112 / 2200 = %96
    assert m.memory_fill_percent(d) == 96

def test_fill_percent_user_file_alone(tmp_path):
    d = tmp_path / "memories"; d.mkdir()
    (d / "USER.md").write_text("a" * 275)     # 275 / 1375 = %20; MEMORY.md yok
    assert m.memory_fill_percent(d) == 20

def test_fill_percent_caps_at_100(tmp_path):
    d = tmp_path / "memories"; d.mkdir()
    (d / "MEMORY.md").write_text("a" * 10000)
    assert m.memory_fill_percent(d) == 100

def test_build_reminder_full():
    assert m.build_reminder(3, 87) == (
        "🧹 Hafıza bakımı bekliyor (son bakım 3 gün önce; hafıza %87 dolu) — "
        "'bakım yapalım' dersen memory-maintenance skill'iyle başlarım."
    )

def test_build_reminder_without_fill():
    assert m.build_reminder(3, None) == (
        "🧹 Hafıza bakımı bekliyor (son bakım 3 gün önce) — "
        "'bakım yapalım' dersen memory-maintenance skill'iyle başlarım."
    )

def test_build_reminder_first_run():
    text = m.build_reminder(None, 87)
    assert "henüz bakım kaydı yok" in text and "son bakım" not in text

def test_reminder_line_fits_budget():
    text = m.build_reminder(99999, 100)
    assert len(text) <= 200 and "\n" not in text

def test_update_last_reminded_creates_and_updates(tmp_path):
    p = tmp_path / "nested" / "maintenance.json"
    m.update_last_reminded(p, "2026-11-18T00:00:00+00:00")
    assert json.loads(p.read_text()) == {"last_reminded": "2026-11-18T00:00:00+00:00"}
    m.update_last_reminded(p, "2026-11-19T00:00:00+00:00")
    assert json.loads(p.read_text()) == {"last_reminded": "2026-11-19T00:00:00+00:00"}
```

Not: `test_read_state_missing_file`'da dosya adı `yok.json` bilerek sabittir (var olmayan yol).

- [ ] **Step 2: Testi koştur, FAIL bekle**

Run (repo kökünde):
```bash
REPO=/home/yelsoft/.hermes/hermes-agent SP=$(python3 -c "import sysconfig;print(sysconfig.get_paths()['purelib'])") HERMES_AGENT_REPO=$REPO PYTHONPATH="$SP:$REPO" uv run --with pytest --with pytest-mock python -m pytest tests/test_maintenance.py -q
```
Expected: collection hatası `ImportError: cannot load .../.hermes-plugin/maintenance.py` (conftest kaydı dosyayı bulamaz).

- [ ] **Step 3: `maintenance.py`'yi uygula** — Interfaces'teki imzalar ve değerlerle (tek seçim paylaşılmayan: `read_state` içinde ISO parse denemesi `datetime.fromisoformat`, naif → `tzinfo=timezone.utc` ile UTC say; `compute_days_since` `(now - parsed).days` tamsayı farkını kullanır). Modül docstring İngilizce, hatırlatma metni Türkçe (config.py/roster.py deseni).

- [ ] **Step 4: Testi koştur, PASS bekle**

Run: Step 2'deki komutun aynısı.
Expected: `22 passed` (yukarıdaki test listesiyle birebir: 4 parse + 3 read_state + 3 compute_days_since + 2 is_due + 5 fill + 4 build_reminder + 1 update).

- [ ] **Step 5: Commit**

```bash
git add .hermes-plugin/maintenance.py tests/test_maintenance.py tests/conftest.py
git commit -m "feat: memory-maintenance core (state, interval, reminder line)"
```

---

### Task 2: Hook entegrasyonu — pipeline bakım adımı (TDD)

**Files:**
- Modify: `.hermes-plugin/__init__.py` (imports, `_PIPELINE_CACHE`, `_pipeline`, iki yeni fonksiyon)
- Modify: `tests/test_hook.py` (`_pipeline_mod` yardımcısı + yeni testler; mevcut test gövdeleri değişmez)

**Interfaces:**
- Consumes: Task 1 imzaları (`_sibling("maintenance")` ile; `parse_team_config` gibi modül düzeyi alias):
  `parse_maintenance_block`, `read_state`, `is_due`, `compute_days_since`, `memory_fill_percent`, `build_reminder`, `update_last_reminded`
- Produces:

```python
# .hermes-plugin/__init__.py — modül düzeyi aliaslar + yeni fonksiyonlar:
maintenance = _sibling("maintenance")
parse_maintenance_block = maintenance.parse_maintenance_block
read_state = maintenance.read_state
is_due = maintenance.is_due
compute_days_since = maintenance.compute_days_since
memory_fill_percent = maintenance.memory_fill_percent
build_reminder = maintenance.build_reminder
update_last_reminded = maintenance.update_last_reminded

def _maintenance_paths() -> tuple[Path, Path]:
    # (state_path, memories_dir). Çağrı anında LIVE_DIR'ı okur (testler patch edebilir):
    # (LIVE_DIR / "maintenance.json", Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "memories")

def _maintenance_reminder(data: dict | None) -> str:
    # Hatırlatma satırı; due değilse "". Asla raise etmez. Sıra: interval parse
    # (blok uyarısı _log.warning), read_state (state uyarısı _log.warning),
    # is_due değilse "" dön; days/fill HESAPLA (state güncellenmeden önce),
    # sonra update_last_reminded(state, now_iso) ve build_reminder(days, fill).
    # now = datetime.now(timezone.utc); iso = now.isoformat() (+00:00 soneki).
```

`_pipeline` yeniden yapısı (cache'in `data` anahtarı kazanması kararın özü; uygulayıcı bu şekli aynen kullanır):

```python
    cache = _PIPELINE_CACHE                     # {"mtime": None, "roster": None, "data": None}
    if cache["roster"] is not None and cache["mtime"] == mtime:
        roster = cache["roster"]
    else:
        # ... mevcut parse/sync/roster akışı değişmez; sonda:
        cache["mtime"], cache["roster"], cache["data"] = mtime, roster, data
    # Bakım zaman temellidir: mtime kapısının DIŞINDA, her çağrıda koşar.
    try:
        reminder = _maintenance_reminder(cache["data"])
    except Exception as exc:                     # asla raise: warn + atla
        _log.warning("software-team: maintenance check failed: %s", exc)
        reminder = ""
    return roster + ("\n" + reminder if reminder else "")
```

Ayrıca: modül docstring'i ve `_pipeline` docstring'i hatırlatma adımından söz edecek; `pre_llm_call` değişmez (subagent/ikinci tur filtresi zaten orada).

- [ ] **Step 1: Failing testleri yaz** — `tests/test_hook.py`:

Önce `_pipeline_mod`'a `maint: bool = False` parametresi ekle: `maint=False` ise `mocker.patch.object(mod, "_maintenance_reminder", return_value="")` (mevcut testlerin tümü bakımsız koşar, tek satırlık değişiklik — gövdeleri değişmez); `maint=True` ise bu patch yerine `maint_state = tmp_path / "maintenance.json"`, `memories = tmp_path / "memories"` tanımla, `mocker.patch.object(mod, "_maintenance_paths", return_value=(maint_state, memories))` ve **6'lı demet** `(mod, team, state, sync_routes, sync_concurrency, maint_state)` döndür (maint=False'da mevcut 5'li demet aynen kalır). Ardından yeni testler:

```python
import json
from datetime import datetime, timezone

def test_pipeline_appends_reminder_when_due(mocker, tmp_path):
    mod, _, _, _, _, maint_state = _pipeline_mod(mocker, tmp_path, team_text=VALID_TEAM, maint=True)
    roster = mod._pipeline()
    assert "🧹 Hafıza bakımı bekliyor" in roster
    assert "henüz bakım kaydı yok" in roster              # ilk çalıştırma: state yok
    assert "last_reminded" in json.loads(maint_state.read_text())  # ateşleme state'i yazdı

def test_pipeline_skips_reminder_when_not_due(mocker, tmp_path):
    mod, _, _, _, _, _ = _pipeline_mod(mocker, tmp_path, team_text=VALID_TEAM, maint=True)
    mocker.patch.object(mod, "read_state",
                        return_value=(datetime.now(timezone.utc).isoformat(), None))
    roster = mod._pipeline()
    assert "🧹" not in roster

def test_pipeline_reminder_failure_degrades_to_log_only(mocker, tmp_path, caplog):
    mod, _, _, _, _, _ = _pipeline_mod(mocker, tmp_path, team_text=VALID_TEAM, maint=True)
    mocker.patch.object(mod, "_maintenance_reminder", side_effect=RuntimeError("maint boom"))
    roster = mod._pipeline()                              # asla raise etmez
    assert "explore" in roster and "🧹" not in roster
    assert any("maintenance" in r.message and r.levelno == logging.WARNING for r in caplog.records)

def test_cached_pipeline_reevaluates_maintenance(mocker, tmp_path):
    mod, _, _, _, _, maint_state = _pipeline_mod(mocker, tmp_path, team_text=VALID_TEAM, maint=True)
    first = mod._pipeline()
    assert "🧹" in first                                   # ateşlendi → state yazıldı
    second = mod._pipeline()                               # aynı mtime: roster önbellekten
    assert "🧹" not in second                              # bakım yeniden değerlendirildi → sessiz

def test_reminder_line_fits_hook_budget(mocker, tmp_path):
    mod, _, _, _, _, _ = _pipeline_mod(mocker, tmp_path, team_text=VALID_TEAM, maint=True)
    reminder = next(l for l in mod._pipeline().splitlines() if "🧹" in l)
    assert len(reminder) <= 200                            # bütçe: ~1KB içinde tek satır
```

Not: `unittest.mock` importuna gerek yok — bu dosya zaten `mocker` fixture'ını kullanıyor (yukarıdaki patch'ler de `mocker.patch.object`).

- [ ] **Step 2: Testi koştur, FAIL bekle**

Run (repo kökünde):
```bash
REPO=/home/yelsoft/.hermes/hermes-agent SP=$(python3 -c "import sysconfig;print(sysconfig.get_paths()['purelib'])") HERMES_AGENT_REPO=$REPO PYTHONPATH="$SP:$REPO" uv run --with pytest --with pytest-mock python -m pytest tests/test_hook.py -q
```
Expected: FAIL — `AttributeError: module ... has no attribute '_maintenance_reminder'` (`maint=False` patch'i ve yeni testler birlikte düşer).

- [ ] **Step 3: `__init__.py`'yi uygula** — Interfaces'teki aliasları, `_maintenance_paths`, `_maintenance_reminder` (sıra yorumda sabit) ve `_pipeline` yeniden yapısını ekle; `_PIPELINE_CACHE` başlangıç değerine `"data": None`; imports'a `from datetime import datetime, timezone`. Başka hiçbir fonksiyona dokunma.

- [ ] **Step 4: Testi koştur, PASS bekle**

Run: Step 2'deki komutun aynısı.
Expected: PASS — test_hook.py'deki tüm testler (eski + yeni) yeşil.

- [ ] **Step 5: Commit**

```bash
git add .hermes-plugin/__init__.py tests/test_hook.py
git commit -m "feat: inject memory-maintenance reminder in first-turn pipeline"
```

---

### Task 3: memory-maintenance skill + register (TDD)

**Files:**
- Create: `skills/memory-maintenance/SKILL.md`
- Modify: `.hermes-plugin/__init__.py:268-275` — `register()` ikinci skill'i ekler
- Test: `tests/test_maintenance_skill.py`

**Interfaces:**
- Consumes: mevcut `_skills_dir() -> str`, `_frontmatter_value(content: str, key: str) -> str`; `ctx.register_skill(name, Path, description=...)`
- Produces: `register()` artık sırayla `team-protocol` ve `memory-maintenance` kaydeder; SKILL.md içeriği aşağıda sabittir.

- [ ] **Step 1: Failing testleri yaz** — `tests/test_maintenance_skill.py`:

```python
import importlib.util
import pathlib
import unittest.mock

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]
SKILL = PLUGIN_DIR / "skills" / "memory-maintenance" / "SKILL.md"

def test_skill_frontmatter_and_sections():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\nname: memory-maintenance\n")
    assert "description:" in text[:200]
    for needle in ["hindsight_retain", "backups", "onay", "maintenance.json",
                   "%90", "SOUL.md", "memory aracı", "bakım yapalım"]:
        assert needle in text

def test_skill_description_fits_catalogue_limit():
    frontmatter = SKILL.read_text(encoding="utf-8").split("---", 2)[1]
    description = next(l.split(":", 1)[1].strip().strip("\"'")
                       for l in frontmatter.splitlines()
                       if l.strip().startswith("description:"))
    assert 0 < len(description) <= 60

def test_register_memory_maintenance_skill(mocker):
    spec = importlib.util.spec_from_file_location(
        "st_init", PLUGIN_DIR / ".hermes-plugin" / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ctx = mocker.Mock()
    mod.register(ctx)
    names = [c.args[0] for c in ctx.register_skill.call_args_list]
    assert names == ["team-protocol", "memory-maintenance"]
    path_arg = ctx.register_skill.call_args_list[1].args[1]
    assert isinstance(path_arg, pathlib.Path)   # Path zorunlu — str AttributeError üretir
    assert ctx.register_skill.call_args_list[1].kwargs["description"].strip()
```

- [ ] **Step 2: Testi koştur, FAIL bekle**

Run (repo kökünde):
```bash
REPO=/home/yelsoft/.hermes/hermes-agent SP=$(python3 -c "import sysconfig;print(sysconfig.get_paths()['purelib'])") HERMES_AGENT_REPO=$REPO PYTHONPATH="$SP:$REPO" uv run --with pytest --with pytest-mock python -m pytest tests/test_maintenance_skill.py -q
```
Expected: FAIL — `FileNotFoundError` (SKILL.md yok) + register testi ikinci skill çağrısını bulamaz.

- [ ] **Step 3: SKILL.md + register uygula.** Frontmatter birebir:

```markdown
---
name: memory-maintenance
description: Hafıza bakımı: oku, hindsight'a retain, küçült, yedekle.
---
```

Gövde Türkçe, dört başlık ve sabit içerik (spec'in "Bakım prosedürü" bölümü):
- **## Dosyaları oku** — `~/.hermes/memories/USER.md`, `~/.hermes/memories/MEMORY.md`, `~/.hermes/SOUL.md`; SOUL.md yalnız girdidir, asla düzenlenmez.
- **## Yüksek sinyalleri hindsight'a retain et** — `hindsight_retain` ile yalnız ekleme (yıkıcı işlem yok).
- **## Küçültme (onaylı)** — doluluk ≥ %90 ise küçültme önerisi listenin en üstüne. Önce yedek: `~/.hermes/software-team/backups/<dosyaadı>-<YYYYmmdd-HHMMSS>.md` zaman damgalı kopya. Sonra kullanıcıya öneri listesi (birleşecek/düşecek girişler + gerekçe); kullanıcı onayı olmadan hiçbir yazım yapılmaz; uygulama `memory` aracıyla.
- **## Bitirme: state güncelle** — `~/.hermes/software-team/maintenance.json` dosyasına `{"last_reminded": "<şimdiki ISO>"}` yaz (yoksa oluştur) → hatırlatma N gün susar.

`register()` içine, mevcut satırlardan sonra:

```python
    skill_md = Path(skills_dir) / "memory-maintenance" / "SKILL.md"
    description = _frontmatter_value(skill_md.read_text(encoding="utf-8"), "description")
    ctx.register_skill("memory-maintenance", skill_md, description=description)
```

- [ ] **Step 4: Testi koştur, PASS bekle**

Run: Step 2'deki komutun aynısı.
Expected: PASS (3 test).

- [ ] **Step 5: Commit**

```bash
git add skills/memory-maintenance/SKILL.md .hermes-plugin/__init__.py tests/test_maintenance_skill.py
git commit -m "feat: memory-maintenance skill + registration"
```

---

### Task 4: team.jsonc şablonuna maintenance bloğu (TDD)

**Files:**
- Modify: `templates/team.jsonc` (başlık yorumu + blok)
- Test: `tests/test_ensure.py` (yeni testler)

**Interfaces:**
- Consumes: `st_config.parse_team_config(path) -> dict` (bilinmeyen anahtarları geçirir), `st_maintenance.parse_maintenance_block`
- Produces: şablonda `"maintenance": {"interval_days": 7}` bloğu.

Not (tahmin düzeltmesi): blok parse'ı `config.py`'ye girmez — Task 1'de `maintenance.py`'ye kondu. `config.py`'nin JSONC→dict ve agent doğrulama sorumluluğu değişmiyor; daha küçük diff.

- [ ] **Step 1: Failing testleri yaz** — `tests/test_ensure.py` sonuna:

```python
def test_template_maintenance_block_parses():
    import st_config
    import st_maintenance
    cfg = st_config.parse_team_config(TEMPLATE)
    assert cfg["maintenance"] == {"interval_days": 7}
    assert st_maintenance.parse_maintenance_block(cfg["maintenance"]) == (7, None)

def test_template_maintenance_comment_documents_default():
    text = TEMPLATE.read_text(encoding="utf-8")
    head = text.split("\n{", 1)[0]
    assert "maintenance" in head.lower() and "7" in head  # varsayılanı belgeler
```

- [ ] **Step 2: Testi koştur, FAIL bekle**

Run (repo kökünde):
```bash
REPO=/home/yelsoft/.hermes/hermes-agent SP=$(python3 -c "import sysconfig;print(sysconfig.get_paths()['purelib'])") HERMES_AGENT_REPO=$REPO PYTHONPATH="$SP:$REPO" uv run --with pytest --with pytest-mock python -m pytest tests/test_ensure.py -q
```
Expected: FAIL — `KeyError: 'maintenance'` (ilk test), ikinci test başlık yorumunu bulamaz.

- [ ] **Step 3: Şablonu düzenle** — `templates/team.jsonc`:
  - Başlık yorum bloğunun sonuna (satır 8'deki `enabled` satırından sonra): `// maintenance.interval_days: hafıza bakımı hatırlatma aralığı (gün; yoksa varsayılan 7).`
  - `"max_parallel": 4,` satırından hemen sonra:

```jsonc
  // Opsiyonel: N günde bir hafıza bakımı hatırlatması. Blok yoksa 7 kullanılır;
  // 1'den küçük veya tamsayı olmayan değer uyarı verir, 7 kullanılır.
  "maintenance": {
    "interval_days": 7
  },
```

- [ ] **Step 4: Testi koştur, PASS bekle**

Run: Step 2'deki komutun aynısı.
Expected: PASS — test_ensure.py'deki tüm testler (eski + yeni) yeşil.

- [ ] **Step 5: Commit**

```bash
git add templates/team.jsonc tests/test_ensure.py
git commit -m "feat: maintenance block in team.jsonc template"
```

---

### Task 5: README + tam suite + commit

**Files:**
- Modify: `README.md` ("İlk oturumda plugin şunları yapar" 3. maddesi + yeni bölüm)

**Interfaces:**
- Consumes: yok (dokümantasyon).
- Produces: README'de `## Hafıza bakımı` bölümü.

- [ ] **Step 1: README'yi düzenle** — `## Ekip nasıl yürür` ile `## Geliştirme` arasına `## Hafıza bakımı` bölümü; içinde şunlar mutlaka yer alacak: hatırlatmanın oturumun ilk turunda geldiği, varsayılan interval 7 gün ve `team.jsonc` `maintenance.interval_days` ile değiştiği (bozuk değer → uyarı + 7), state dosyası `~/.hermes/software-team/maintenance.json`, yedeklerin `~/.hermes/software-team/backups/` altına zaman damgalı yazıldığı, tetik cümlesi ('bakım yapalım') ve skill adı, onaysız yazım olmadığı. Ayrıca "İlk oturumda plugin şunları yapar" 3. maddesine "+ bakım hatırlatması" ekle.

- [ ] **Step 2: Tam suite'i koştur, PASS bekle**

Run (repo kökünde):
```bash
REPO=/home/yelsoft/.hermes/hermes-agent SP=$(python3 -c "import sysconfig;print(sysconfig.get_paths()['purelib'])") HERMES_AGENT_REPO=$REPO PYTHONPATH="$SP:$REPO" uv run --with pytest --with pytest-mock python -m pytest tests/ -q
```
Expected: PASS — tüm test dosyaları yeşil, 0 failed (mevcut 4 dosya + test_maintenance.py + test_maintenance_skill.py).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: memory-maintenance feature section in README"
```

---

## Kapsam dışı (anti-goals — planın hiçbir görevi bunları yapmaz)

- İnsansız cron koşusu; plugin kendi zamanlayıcısı; hindsight iç temizliği; SOUL.md düzenlemesi; makineler arası senkron.
- `.hermes-plugin/plugin.yaml` / manifest'e hiçbir değişiklik; yeni Python bağımlılığı yok.
- `ensure_user_config` imzası ve davranışı değişmez (maintenance.json ilk kurulumda DEĞİL, ilk hatırlatmada oluşur — Review Focus 5).
