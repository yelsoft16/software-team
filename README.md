# software-team

Hermes için 9 kişilik yazılım ekibi: tek bir `team.jsonc` dosyasından yönetilen
rol çizelgesi, rol başına model rotaları ve orkestratör protokolü. Kullanıcı
ana modelle konuşur; ana model orkestratördür — işi superpowers workflow'u
üzerinden yürütür, alt işleri `delegate_task` ile rol bazlı model rotalarına
dağıtır, sonuçları toplar ve doğrular.

Delegasyon profil bazlı değil **model bazlıdır**: her rol kendi modelinde,
kendi uzman prompt'uyla, taze context'li bir subagent olarak koşar. Ucuz işler
(keşif, araştırma) ucuz modellere, zor işler (plan, hata ayıklama) güçlü
modellere gider.

## Bağımlılıklar

- **superpowers** — workflow motoru (brainstorm → plan → uygula → doğrula). Bu
  plugin onun yaptığı hiçbir işi tekrar yapmaz, onu sürer.
- **advanced-delegation** — rota motoru. Rol rotaları onun `model_map`
  backend'ine yazılır; dağıtım da onun `delegate_task` `option` mekanizmasıyla
  yapılır.
- Hermes >= 0.22.5.

## Kurulum

```bash
hermes plugins install yelsoft16/software-team --enable
```

Kurulumdan sonra Hermes gateway'ini yeniden başlat — yeni modül yüklemede
devreye girer. `main` her zaman son stabil sürümdür.

Alternatif (elle): `git clone https://github.com/yelsoft16/software-team ~/.hermes/plugins/software-team`
ardından `hermes plugins adopt software-team` (provenance'a alır, update
takibine bağlar).

## Güncelleme

```bash
hermes plugins check-updates        # yeni commit var mı?
hermes plugins update software-team # varsa uygula
```

Güncellemeden sonra da gateway'i yeniden başlat. Sürüm çıpaları GitHub
Releases'te (`vX.Y.Z` tag'ları); git kurulumu commit bazında takip edilir.

İlk oturumda plugin şunları yapar:

1. `~/.hermes/software-team/` altına `team.jsonc` (şablondan kopya) ve
   `state.json` (rota sahipliği) oluşturur. Var olan dosyalara **asla**
   dokunmaz.
2. `team.jsonc`'teki 9 rolü `delegation.backends.model_map.options` rotalarına
   senkronlar, backend'i `model_map` yapar ve `max_parallel`'ı
   `delegation.max_concurrent_children`'a yazar. Elle eklediğin yabancı
   rotalar korunur.
3. Oturumun ilk turunda orkestratöre kompakt çizelge + protokol + bakım
   hatırlatması enjekte eder. Subagent'lara asla enjekte edilmez.

## Sorun giderme

### Kurulum: "Staged plugin files changed while preparing the update; retry."

Kurulum, klonladığı dosyaların içerik hash'ini yayına almadan hemen önce
yeniden ölçer; o arada staged klonun `.git/` içinde değişen tek bayt bile
kurulumu bu hatayla düşürür. Bilinen sebep: VS Code Remote-SSH Git
eklentisinin `~/.hermes/plugins` altında yeni beliren her `.git` dizinini
otomatik repo olarak açıp `.git/config`'e
`branch.main.vscode-merge-base` satırını yazması — yazım tam hash kontrolüyle
yayın arasına denk gelirse yarış olur. Bu yüzden bazen başarılı, bazen hatalı
biter; plugin'de/manifestte bir sorun yoktur.

- **Kalıcı çözüm:** VS Code ayarlarına `"git.autoRepositoryDetection":
  "openEditors"` ekle (ya da kurulum sırasında pencereyi kapat).
- **Geçici çözüm:** komutu tekrar çalıştır — yarış penceresi denk gelmezse
  kurulur.
- **Garantili yol (elle):**

```bash
git clone https://github.com/yelsoft16/software-team ~/.hermes/plugins/software-team
hermes plugins adopt software-team
```

### "doesn't contain plugin.yaml" uyarısı

Zararsız: manifest `.hermes-plugin/plugin.yaml` içinde olduğu için kök
kontrolü onu bulamaz; plugin düzgün kurulur ve çalışır.

## Ekip (9 rol)

| Rol | Görev | Model (varsayılan) | Reasoning |
|---|---|---|---|
| `explore` | Kod tabanını hızlı tarar: dosya, sembol, bağımlılık | gemini-3.1-flash-lite | provider varsayılanı |
| `researcher` | Dış kaynakları araştırır, kaynaklı özetler | deepseek-v4.1-flash | max |
| `consultant` | Mimari ve tasarımda ikinci görüş | cx/gpt-5.6-sol | high |
| `planner` | Uygulama planı: küçük adımlar, dosya yolları, testler | deepseek-v4-pro | max |
| `implementer` | Planı kodlar, testleriyle teslim eder | mimo-v2.6-pro | high |
| `reviewer` | Diff'i spec'e karşı denetler (kritik/önemli/minör) | glm-5.3-flash | max |
| `debugger` | Kök neden bulur: hata, kırık test, performans | deepseek-v4-pro | max |
| `writer` | Doküman, README, commit metinleri | mimo-v2.6-flash | high |
| `qa` | Gerçek senaryoları çalıştırır, artifact'lı kanıt matrisi üretir | mimo-v2.6-flash | high |

Rol adı = rota adı. `delegate_task`'ta görevi hangi rolle çalıştırmak
istiyorsan `option` olarak o adı seçersin; model/provider/reasoning rotada
çözülür. Rota seçilmeyen iş bilinçli olarak orkestratörde kalır (model_map
`default` rotası tanımlanmaz). Rollerin davranış sözleşmeleri (çıktı biçimi +
başarı/başarısızlık koşulları) `skills/team-protocol/references/rol-sozlesmeleri.md`'dedir.

## team.jsonc

Tek kaynak: `~/.hermes/software-team/team.jsonc` (JSONC — yorum serbest).
İlk kurulumda `templates/team.jsonc` şablonundan kopyalanır; kopya
çıktıktan sonra dosya tamamen **senindir**, plugin üzerine yazmaz. Alanlar:

| Alan | Anlam |
|---|---|
| `name` | Rol adı = rota adı (charset: `[A-Za-z0-9_.-]`) |
| `description` | Tek satır — modelin rota seçerken gördüğü sinyal |
| `model` | O rolda koşacak model |
| `provider` | Hermes config'indeki provider **adı** (endpoint/anahtar yazılmaz) |
| `base_url` | `provider` yerine özel endpoint (isteğe bağlı) |
| `reasoning` | `minimal \| low \| medium \| high \| xhigh \| max \| ultra` — alan yoksa provider varsayılanı |
| `prompt` | Role özel görev tanımı — orkestratör child'ın context'ine ekler |
| `enabled` | `false` = rota yok, çizelgede yok |

YASAK: dosyaya sır (api_key, token) yazmak. Kimlik bilgileri Hermes'in kendi
provider/auth yapısında kalır.

Dosya her oturumun ilk turunda okunur; değiştirdiysen yeni oturumda geçerli
olur. Kötü bir giriş (sözdizimi hatası, eksik alan, bilinmeyen provider)
ekibi düşürmez: o agent uyarıyla atlanır, kalanı çalışır.

## Ekip nasıl yürür

Superpowers fazları rollerle eşleşir: `brainstorming` → consultant,
`writing-plans` → planner, `subagent-driven-development` → implementer,
`requesting-code-review` → reviewer, `systematic-debugging` → debugger,
`verification-before-completion` → orkestratörün kendisi. Dağıtım kuralları,
sonuç doğrulama ve fallback kurallarının tamamı `team-protocol` skill'inde
yazar — orkestratör her oturumda onu referans alır. Her delegasyon hafıza
döngüsünden geçer (dispatch öncesi recall, rapor sözleşmesinde zorunlu
Öğrenimler bölümü, görev sonrası hindsight'a retain); ayrıntılar
`team-protocol` skill'inde.

## Hafıza bakımı

Plugin hafıza bakımını da takip eder: oturumun **ilk turunda** orkestratörün
context'ine (asla subagent'lara) tek satırlık bir hatırlatma eklenir — bakım
vakti geldiyse. Vakit, `~/.hermes/software-team/maintenance.json` dosyasındaki
son hatırlatma zamanına göre hesaplanır; aralık **7 gündür** ve `team.jsonc`'te
`maintenance.interval_days` ile değiştirilebilir. Bozuk bir değer (tamsayı
olmayan ya da 1'den küçük) uyarı verir ve aralık 7'ye döner.

Bakımı tetiklemek için **'bakım yapalım'** de; `memory-maintenance` skill'i
devreye girer: hafıza dosyalarını okur, yüksek sinyalli olguları hindsight'a
retain eder, doluluk yüksekse küçültme önerisi sunar ve bakım kaydını
günceller. Küçültmeden önce dosyalar `~/.hermes/software-team/backups/` altına
`<dosyaadı>-<YYYYmmdd-HHMMSS>.md` zaman damgalı kopyalarla yedeklenir.

**Onaysız yazım yoktur:** kullanıcı onayı olmadan hiçbir hafıza dosyası
değiştirilmez. `SOUL.md` yalnız okunur, asla düzenlenmez.

## Geliştirme

```bash
cd ~/.hermes/plugins/software-team
REPO=/home/yelsoft/.hermes/hermes-agent \
SP=$(python3 -c "import sysconfig;print(sysconfig.get_paths()['purelib'])") \
HERMES_AGENT_REPO=$REPO PYTHONPATH="$SP:$REPO" \
uv run --with pytest --with pytest-mock python -m pytest tests/ -q
```

Testler yeni Python bağımlılığı istemez; yalnızca dev ortamında pytest ve
pytest-mock kullanılır (testler `mocker` fixture'ına dayanır).
