# software-team

Hermes için 8 kişilik yazılım ekibi: tek bir `team.jsonc` dosyasından yönetilen
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
2. `team.jsonc`'teki 8 rolü `delegation.backends.model_map.options` rotalarına
   senkronlar, backend'i `model_map` yapar ve `max_parallel`'ı
   `delegation.max_concurrent_children`'a yazar. Elle eklediğin yabancı
   rotalar korunur.
3. Oturumun ilk turunda orkestratöre kompakt çizelge + protokol enjekte eder.
   Subagent'lara asla enjekte edilmez.

## Ekip (8 rol)

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

Rol adı = rota adı. `delegate_task`'ta görevi hangi rolle çalıştırmak
istiyorsan `option` olarak o adı seçersin; model/provider/reasoning rotada
çözülür. Rota seçilmeyen iş bilinçli olarak orkestratörde kalır (model_map
`default` rotası tanımlanmaz).

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
yazar — orkestratör her oturumda onu referans alır.

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
