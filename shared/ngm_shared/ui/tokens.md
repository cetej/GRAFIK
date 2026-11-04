# Sémantické UI tokeny projektů NGM

Zdroj: GRAFIK#81, vzor STAVITEL `design/tokens.json`. Aplikace definuje tyto proměnné na `:root` ve svém CSS (svými schválenými barvami a písmy) a pak načte `base.css`. Názvy jsou závazné, hodnoty ne.

| Token | K čemu |
|---|---|
| `--bg` | pozadí aplikace |
| `--surface` | panely, karty, dialog |
| `--line` | okraje a dělicí čáry |
| `--fg` | hlavní text |
| `--muted` | vedlejší text, popisky |
| `--accent` | hlavní akce (vyplněné tlačítko), odkazy |
| `--accent-soft` | podklad obrysového tlačítka pod myší a při stisku |
| `--on-accent` | text na `--accent` |
| `--focus` | rámeček fokusu z klávesnice (kontrast aspoň 3:1 proti okolí) |
| `--ok`, `--ok-soft` | hotovo: text / podklad |
| `--warn`, `--warn-soft` | varování, běží: text / podklad |
| `--bad`, `--bad-soft` | chyba, nebezpečná akce: text / podklad |
| `--font-ui` | písmo rozhraní |
| `--radius` | zaoblení ovládacích prvků |

Každá barva textu má s pozadím, na kterém stojí, kontrast aspoň 4,5:1 (`--fg`/`--bg`, `--fg`/`--surface`, `--muted`/`--surface`, `--on-accent`/`--accent`, `--ok`/`--ok-soft`, `--warn`/`--warn-soft`, `--bad`/`--bad-soft`).

## Komponenty v `base.css`

- **Tlačítko** `.ui-btn` (vedlejší, obrys), `.ui-btn.ui-primary` (hlavní, výplň akcentem), `.ui-btn.ui-danger` (nebezpečné). Vypadá jako tlačítko i v klidu, má kurzor, stav pod myší (jen na zařízení s myší), stisk a viditelný fokus. Vypnuté mění výplň, barvu písma i kurzor; proč je vypnuté, řekne text vedle.
- **Informace** `.ui-info` (panel), `.ui-tag` (štítek): bez výplně akcentem, bez rámečku tlačítka, bez kurzoru `pointer`.
- **Stav** `.ui-state` s `.ui-run`, `.ui-done`, `.ui-fail`: barevná tečka a text v barvě stavu.
- **Náhled** `.ui-thumb`: obrázek, který jde kliknutím zvětšit (kurzor lupy), zvětšení `.ui-lightbox` přes celou obrazovku.
