---
name: memory-maintenance
description: Hafıza bakımı: oku, hindsight'a retain, küçült, yedekle.
---

# Hafıza Bakımı

Kullanıcı **'bakım yapalım'** dediğinde (ya da hatırlatma satırı geldiğinde)
aşağıdaki bakım prosedürünü sırasıyla uygula. Dört adımdır; hiçbir adımda
kullanıcı onayı olmadan hafıza yazımı yapılmaz.

## Dosyaları oku

`~/.hermes/memories/USER.md`, `~/.hermes/memories/MEMORY.md` ve
`~/.hermes/SOUL.md` dosyalarını oku. `SOUL.md` yalnız girdidir, asla düzenlenmez.

## Yüksek sinyalleri hindsight'a retain et

Okuduğun dosyalardaki yüksek sinyalli olguları `hindsight_retain` ile retain et.
Bu adım yalnız eklemedir — yıkıcı işlem yoktur.

## Küçültme (onaylı)

Doluluk ≥ %90 ise küçültme önerisi listenin en üstüne alınır. Önce yedekle:
`~/.hermes/software-team/backups/<dosyaadı>-<YYYYmmdd-HHMMSS>.md` zaman damgalı
kopya. Sonra kullanıcıya öneri listesi sun (birleşecek/düşecek girişler + gerekçe);
kullanıcı onayı olmadan hiçbir yazım yapılmaz. Uygulama `memory aracı`yla yapılır.

## Bitirme: state güncelle

`~/.hermes/software-team/maintenance.json` dosyasına
`{"last_reminded": "<şimdiki ISO>"}` yaz (yoksa oluştur) → hatırlatma N gün susar.
