# ig-reels-insights

Skill para Claude Code que analiza los comentarios e insights de **tus
propios** reels de Instagram usando la Graph API oficial de Meta (tu cuenta,
tu token — sin scraping y sin ningún costo de terceros).

Devuelve cuatro cosas: temas y sentimiento, preguntas frecuentes, leads con
intención de compra, e ideas de contenido nuevo priorizadas.

## Requisitos

- Python 3 (solo librería estándar, sin `pip install`)
- Cuenta de Instagram **Business o Creator** vinculada a una Página de
  Facebook
- Un access token de la Graph API con permisos `instagram_basic`,
  `instagram_manage_comments`, `instagram_manage_insights`,
  `pages_read_engagement`

## Instalación

**Opción A — `npx skills add`** (usa [skills.sh](https://www.skills.sh/)
solo como instalador, jala el código directo de este repo, no requiere crear
cuenta en ningún lado):

```bash
npx skills add valladxres/ig-reels-insights
```

**Opción B — clonar/descargar manual:**

```bash
git clone https://github.com/valladxres/ig-reels-insights.git ~/.claude/skills/ig-reels-insights
```

(o descarga el ZIP desde GitHub y descomprímelo en `~/.claude/skills/`)

Luego, en cualquiera de las dos opciones:

```bash
cd ~/.claude/skills/ig-reels-insights
cp .env.example .env
# rellena INSTAGRAM_ACCESS_TOKEN e INSTAGRAM_BUSINESS_ACCOUNT_ID en .env

python3 scripts/ig_insights.py list --limit 10   # prueba
```

## Uso

En Claude Code: `/ig-reels-insights` y pide lo que quieras ("analiza mis
últimos 5 reels", "sácame los leads del reel X", "qué contenido debería
grabar según los comentarios").

Comandos del script, por si los quieres correr a mano:

```bash
python3 scripts/ig_insights.py list --limit 30                 # media reciente
python3 scripts/ig_insights.py comments <media_id>              # comentarios + replies
python3 scripts/ig_insights.py insights <media_id>              # reach, saves, shares...
python3 scripts/ig_insights.py bundle --recent 5 --out out/     # todo junto, a JSON
```

Flags útiles: `--throttle 1.0` (más lento, más seguro con reels de miles de
comentarios), `--retries N`, `-q`.

## Privacidad

- `.env` está en `.gitignore`; el script redacta el token de cualquier
  mensaje de error.
- Los JSON de `out/` (también en `.gitignore`) contienen usernames y
  comentarios de personas reales — no los subas a repos públicos ni los
  compartas fuera de quien los generó.

## Personalización

Los triggers/palabras-CTA son configurables con `IG_TRIGGERS` en el `.env`.
Para adaptar el análisis a tu nicho, edita las secciones 3a-3d de
[SKILL.md](SKILL.md).

## Licencia

MIT — úsala, adáptala, compártela.

---

Hecho por **Aarón** —
[Instagram](https://www.instagram.com/valladxres/) ·
[YouTube](https://youtube.com/@valladaresia) ·
[Comunidad](https://www.skool.com/idea-stack-6277/about)
