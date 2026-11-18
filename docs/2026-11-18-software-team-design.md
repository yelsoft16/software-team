# software-team plugin — Design

Tarih: 2026-11-18
Sahibi: yelsoft (kullanıcı) + Hermes orkestratör (builder)
Durum: onay bekliyor

## Niyet ve neden

Hermes'te tek modelle yürüyen bir "yazılım ekibi". Kullanıcı ana modelle konuşur;
ana model orkestratördür. İstekler superpowers workflow'una girer
(brainstorm → writing-plans → subagent-driven-development → verification), alt işler
`delegate_task` ile rol bazlı model rotalarına dağıtılır ve sonuçlar orkestratörde
toplanır. Delegasyon profil bazlı DEĞİL model bazlıdır.

Neden: (a) kalite — her alt iş taze context'li, uzman prompt'lu bir subagent'ta koşar;
(b) maliyet kontrolü — ucuz işler (repo tarama, dokümantasyon) ucuz modellere, zor işler
güçlü modellere gider; (c) yönetilebilirlik — ekip tek bir JSONC dosyasından değiştirilir.

İlham: OmO (oh-my-openagent) — orkestratör + görev bazlı uzman agent'lar, her biri kendi
modelinde, paralel, bitince doğrulanan iş. Yalnızca agent YAPISI alındı; OmO'nun senpi/task
DAG motoru, memory sistemi ve skill yükleyicisi alınmadı.

## Hedefler (goals)

1. `team.jsonc` tek kaynak: agent tanımları (name, description, model, reasoning, prompt,
   enabled). Elle düzenlenebilir, yorumlu (JSONC).
2. Oturum başında (dosya mtime değişmişse) agent'lar `delegation.backends.model_map.options`
   rotalarına senkronlanır; `delegation.backend = model_map` ve
   `delegation.max_concurrent_children` de bu dosyadan yönetilir.
3. Orkestratörün ilk turuna ekip çizelgesi (rol adları + tek satırlık description'lar +
   hangi model) + ekip protokolü enjekte edilir. Subagent'lara asla enjekte edilmez.
4. Superpowers workflow motoru olarak, advanced-delegation rota motoru olarak kalır —
   ikisinin yaptığı hiçbir iş yeniden yapılmaz.

## Hedef dışı (non-goals)

- Profil bazlı delegasyon (profile_routes): yok.
- omo.jsonc'teki `teams` bloğu (ön tanımlı ekip üye listeleri): yok — orkestratör ekibi her
  görevde dinamik kurar. Gerekirse sonraki sürümde.
- Skill yükleme/yönetim mekanizması: superpowers'ın işi.
- Rota editörü TUI/slash komutları: advanced-delegation'ın işi (`hermes delegation config`,
  `/delegation`).
- Kendi delegasyon motorumuz: `delegate_task` + advanced-delegation yeterli.

## Anti-hedefler (başarısızlık kriterleri)

- Subagent'lara ekip bootstrap'ı enjekte etmek → context kirliliği. Superpowers aynı sebeple
  `platform == "subagent"` kontrolü yapıyor; biz de yapacağız.
- 8'den fazla aktif rota → seçim kalitesi düşer (kullanıcının kendi tespiti: 14 seçenek
  seçim kalitesini düşürüyor).
- team.jsonc içine sır yazmak (api_key, token): YASAK. Sadece provider/model adları;
  kimlik bilgileri Hermes'in kendi provider/auth yapısında kalır.
- Invalid agent girişi yüzünden plugin'in sessizce devre dışı kalması: kötü girişler
  uyarıyla atlanır, plugin çalışmaya devam eder (advanced-delegation'ın skip-bad-entries
  davranışıyla aynı).

## Kısıtlar (constraints)

- Rota adı charset: `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` (advanced-delegation store.py).
- Config yazımı: core'un `atomic_config_write`'u, yalnızca `delegation.*` alanlarına dokunulur,
  yorumlar korunur. Elle config.yaml'a yazılmaz.
- Model, rota seçimi yaparken yalnızca rota ADI + tek satır description görür (provider/model
  endpoint'i modelden saklı — advanced-delegation'ın kasıtlı dar prompt-injection yüzeyi).
- Hermes >= 0.22.5 (advanced-delegation ile aynı taban). Plugin bağımlılıkları: superpowers,
  advanced-delegation (ikisi de kurulu).
- reasoning seviyeleri: `minimal | low | medium | high | xhigh | max | ultra` — core 0.23.2
  `hermes_constants.VALID_REASONING_EFFORTS` ile birebir (2026-11-18 doğrulandı). "off" diye
  bir seviye YOK; reasoning alanını tamamen atlamak = provider varsayılanı (builder çağrısı:
  team.jsonc core'un kelime dağarcığını aynen kullanır, çeviri katmanı yok).
- Provider referansı: team.jsonc'de Hermes config'indeki provider ADI kullanılır. Bu
  profile'da OmniRoute endpoint'i `api-yelsoft-online` adıyla tanımlı (base
  https://api.yelsoft.online/v1, key_env HERMES_CUSTOM_API_YELSOFT_ONLINE_API_KEY) — omo'daki
  `omniroute` adının Hermes karşılığı budur (2026-11-18 doğrulandı). Endpoint/anahtar
  team.jsonc'e ASLA yazılmaz.

## Yaklaşımlar (approaches)

A. **Skill-only** (plugin yok, sadece bir SKILL.md ekip talimatı): en basit ama config dosyası
   okunmaz, rota senkronu yok, model eşlemesi elle config.yaml'da tutulur. Elendi: config
   sayfası gereksinimini karşılamıyor.

B. **Hook + config + sync plugin** (SEÇİLEN): `.hermes-plugin/plugin.yaml` + `__init__.py`
   (pre_llm_call hook + rota senkronu) + `skills/team-protocol/SKILL.md` + şablon
   `team.jsonc`. Superpowers'ın kanıtlanmış enjeksiyon pattern'i, advanced-delegation'ın
   kanıtlanmış rota yazımı. Ticaret: az miktarda Python bakımı.

C. **Kendi rota motorumuzu yazmak**: advanced-delegation'ın yaptığını yeniden yapmak —
   tekerlek, reddedildi (kullanıcı kararı: "onları yaptığı işi tekrar yapmayalım").

## Kullanıcının verdiği kararlar

- Plugin adı: `software-team`.
- Ekip: 8 agent — `explore`, `researcher`, `consultant`, `planner`, `implementer`,
  `reviewer`, `debugger`, `writer` (`quick` rolü implementer'a birleşti).
- Config dosyası: `team.jsonc`, omo.jsonc'ten esinlenen şekil (agent başına description +
  model + reasoning + prompt).
- Varsayılan model eşlemesi (kullanıcının kendi omo.jsonc'undan; provider = `api-yelsoft-online`,
  Hermes config'inde doğrulanmış model adları — builder check'in tespitiyle düzeltildi):

  | agent | model | reasoning |
  |---|---|---|
  | explore | gemini-3.1-flash-lite | (alan yok) |
  | researcher | deepseek-v4.1-flash | max |
  | consultant | cx/gpt-5.6-sol | high |
  | planner | deepseek-v4-pro | max |
  | implementer | mimo-v2.6-pro | high |
  | reviewer | glm-5.3-flash | max |
  | debugger | deepseek-v4-pro | max |
  | writer | mimo-v2.6-flash | high |

## Builder'a kalanlar (builder'ın kararları)

(Opus review 2026-11-18 bulguları işlendi: 3 high + 4 medium + 3 low; blocker yok.)

- Plugin düzeni: `.hermes-plugin/plugin.yaml` + `__init__.py`, `skills/team-protocol/SKILL.md`,
  şablon `team.jsonc`. plugin.yaml'da `provides_hooks: [pre_llm_call]` KESİN beyan edilir —
  core declared vs actual hook karşılaştırması yapıyor, beyansız hook ileride strict
  validation'da plugin'i kırar. Superpowers'ın register pattern'i (`ctx.register_skill` +
  Path) baz alınır.
- Config konumu ve yaşam döngüsü: `~/.hermes/software-team/team.jsonc`. İlk kurulumda şablon
  kopyalanır; dosya yoksa plugin pasif değil, uyarı verir (sessiz ölüm yasak).
- JSONC parse: yeni bağımlılık YOK — regex ile yorum temizleme + `json.loads` (stdlib).
- Doğrulama (plugin ön-doğrulaması, store'un listesiyle birebir): zorunlu alanlar
  `name, description, model, provider|base_url` (advanced-delegation `_entry_problem` /
  `validate_route` description ve provider'ı da zorunlu tutuyor — doc'un eski listesi
  eksikti); reasoning legal seviye kontrolü (core kelime dağarcığı); rota adı charset
  kontrolü. Rota adı = agent'ın ROL adıdır, model adı DEĞİL (model adları '/' içerir,
  charset'e uymaz).
- Senkron semantiği: her oturumun İLK pre_llm_call çağrısında koşar (her turda değil);
  team.jsonc mtime değiştiyse yeniden okur. Sıralama kritik: önce `save_routes()`, SONRA
  `set_mode('model_map')` — save_routes backend'i DEĞİŞTİRMEZ; backend default kalırsa hiçbir
  rota kullanılmaz (store.py doğrulandı). `enabled: false` → rota yok, çizelgede yok. Kötü
  giriş: uyarı + atla. Rota yazımı advanced-delegation store'undan gider (atomic, yorum
  koruyan) — elle yazılmaz.
- Rota sahipliği: plugin YALNIZCA kendi yazdığı rotaları mutate eder. Senkronlanan rota
  adları `~/.hermes/software-team/state.json`'da tutulur; sync'te mevcut options listesi
  okunur, yalnızca state'teki adlar çıkarılıp güncel set yazılır — `hermes delegation
  config` ile elle eklenmiş yabancı rotalar KORUNUR (save_routes tüm listeyi komple yazar,
  append etmez).
- `max_parallel` → `delegation.max_concurrent_children`: core'un atomic_config_write'uyla,
  YALNIZCA bu anahtar yazılır; delegation.model/provider/reasoning_effort'a asla dokunulmaz.
- Race koruması: iki oturum aynı anda sync yaparsa diye in-process lock + son yazılan
  options hash karşılaştırması.
- Provider varlık kontrolü: agent'ın provider'ı Hermes config'indeki `providers` listesinde
  YOKSA uyarı + atla (config-seviyesi kontrol; runtime erişilebilirlik core'un
  retry/fallback'ine bırakılır).
- Rotasız görev politikası: model_map'in `default` rotası AYARLANMAZ — rotasız işi
  orkestratör kendi modelinde yapar (aksi halde her küçük delegate pahalı rotaya gidebilir).
- Enjeksiyon formatı: ilk turda (is_first_turn && platform != "subagent") kompakt çizelge:
  rol adı + description + model/reasoning + varsa prompt özeti, ardından protokol kuralları.
  Boyut bütçesi: ≤ ~1KB (superpowers bootstrap'ı zaten ~3-4KB enjekte ediyor; core hook
  context'lerini '\n\n' ile birleştiriyor — turn_context.py doğrulandı; spill eşiğine karşı
  test yazılır). Enjeksiyon kapsamı TÜM non-subagent yüzeylerdir (owner gating YOK —
  kullanıcı kararı 2026-11-18: yapı herkese açık olsun, daha güçlü bir ekip yapısı sunar).
- `team-protocol` skill içeriği: rol→iş eşleme tablosu, her rolün prompt'u child context'ine
  nasıl aktarılır, verification-before-completion ile sonuç doğrulama.
