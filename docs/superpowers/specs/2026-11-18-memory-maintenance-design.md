# Hafıza Bakımı (memory-maintenance) — Kısa Tasarım

Tarih: 2026-11-18 · Durum: onaylandı (sohbet içi) · Boyut: küçük değişiklik

## Niyet

Ajanın hafıza katmanının (`~/.hermes/memories/USER.md` + `MEMORY.md`, `~/.hermes/SOUL.md`
ve hindsight) periyodik bakımı. Tetikleyici: oturum başı hatırlatma — bakım insanın
gözetiminde, insanın oturumunda koşar; insansız değişiklik yoktur.

## Hedefler

- N günde bir (varsayılan 7) ilk tura tek satır bakım hatırlatması enjekte etmek;
  satır, hafıza dosyalarının doluluk bilgisini taşır.
- Bakım prosedürünü bir skill (`memory-maintenance`) olarak paketlemek: dosyaları
  oku → hindsight'a retain → küçültme önerisi → kullanıcı onayı → uygula.
- Küçültme öncesi otomatik yedek; onaysız hiçbir hafıza yazımı yok.

## Hedef dışı (anti-goals)

- İnsansız cron koşusu (sonraki faz olabilir).
- Hindsight'ın kendi iç temizliği.
- SOUL.md düzenlenmesi (yalnız girdi).
- Makineler arası senkron.
- Başarısızlıkta ekibi düşürmek: hatırlatma üretimi asla hata fırlatmaz.

## Yaklaşımlar

1. **Oturum başı hatırlatma (SEÇİLDİ).** Plugin zaten her oturumun ilk turunda hook
   koşuyor; takvim kontrolü eklenir, hatırlatma çizelge enjeksiyonuna bir satır olarak
   katılır. Sıfır yeni altyapı, onay mekanizması doğal (iş kullanıcının oturumunda).
   Eksisi: kullanıcı o gün yazmazsa bakım bekler — aciliyeti olmadığı için kabul edildi.
2. Cron + skill şablonu — gerçek periyodik ama makine başı cron kurulumu ve insansız
   yazma riski. Sonraki faz olarak saklandı.
3. Plugin kendi zamanlayıcısı (curator tarzı arka plan görevi) — core'un auxiliary-model
   mekanizmasına bağımlı, en karmaşık. Reddedildi.

## Mekanizma

- State: `~/.hermes/software-team/maintenance.json` — `{"last_reminded": "<ISO>"}`.
  İlk kurulumda yoksa oluşturulur; yalnız plugin yazar.
- Config: `team.jsonc`'a opsiyonel `"maintenance": {"interval_days": 7}` bloğu
  (yoksa 7; bozuksa uyarı + 7). Dosya kuralı aynı: kullanıcınındır, plugin üzerine yazmaz.
- Hook pipeline'ı: roster üretildikten sonra interval geçtiyse hatırlatma satırı eklenir
  ve `last_reminded` güncellenir. Bütçe: hatırlatma satırı 1024 karakterlik roster
  bütçesinin dışında sayılır, enjekte edilen toplam metin hook bütçesini (~1KB) aşmaz.
- Hatırlatma biçimi: `🧹 Hafıza bakımı bekliyor (son bakım N gün önce; MEMORY %87 dolu) —
  'bakım yapalım' dersen memory-maintenance skill'iyle başlarım.`

## Bakım prosedürü (`skills/memory-maintenance/SKILL.md`)

1. `memories/USER.md`, `memories/MEMORY.md`, `SOUL.md` okunur; SOUL.md yalnız girdidir.
2. Yüksek sinyalli olgular `hindsight_retain` ile işlenir (yalnız ekleme — yıkıcı değil).
3. Küçültme: dosyalar `software-team/backups/` altına zaman damgalı kopyalanır; kullanıcıya
   öneri listesi sunulur (birleşecek/düşecek girişler + gerekçe); onaydan sonra `memory`
   aracıyla uygulanır. Doluluk ≥%90 ise küçültme öneride en üste alınır.
4. Biten bakımda `maintenance.json` güncellenir; hatırlatma N gün susar.

## Kullanıcı kararları

- Yaklaşım: 1 (oturum başı hatırlatma), "1 ile başlayalım gerekirse geliştiririz" (2026-11-18).

## Builder kararları (sohbette sunuldu, itiraz gelmedi)

- `interval_days` varsayılanı 7.
- SOUL.md yalnız girdi.
- Yedek yeri `~/.hermes/software-team/backups/`.
- State dosyası `maintenance.json`; hatırlatma doluluk yüzdesi taşır.

## Değişecek parçalar

- `.hermes-plugin/maintenance.py` (yeni): takvim kontrolü + state oku/yaz + hatırlatma satırı üretimi.
- `.hermes-plugin/__init__.py`: pipeline'a bakım adımı (hata durumunda warn, asla raise).
- `skills/memory-maintenance/SKILL.md` (yeni) + `register()`'da kayıt.
- `templates/team.jsonc`: `maintenance` bloğu (opsiyonel, yorumlu).
- `tests/test_maintenance.py` (yeni) + gerekirse `tests/test_hook.py` güncellemesi.
- `README.md`: özellik bölümü.
