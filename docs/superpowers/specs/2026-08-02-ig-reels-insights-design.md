# ig-reels-insights — Diseño

Fecha: 2026-08-02
Autor: Aarón (valladxres)

## Objetivo

Skill de Claude Code, propia y original de Aarón, para analizar a fondo los
comentarios e insights de los reels de Instagram del usuario que la corre, vía
la Graph API oficial de Meta (no scraping, sin costo de terceros). Se publica
como recurso gratuito en el GitHub de Aarón para que su audiencia la instale
sin necesidad de registrarse en ninguna plataforma.

No es una copia de la skill `instagram-reels-analysis` ya instalada en esta
máquina (de otro creador) — comparte el concepto general (Graph API +
análisis por Claude), pero se implementa desde cero, con su propio nombre,
estructura de código y documentación.

## Alcance funcional

Los mismos cuatro pilares de análisis que el recurso que la inspiró:

1. **Temas y sentimiento** — agrupa comentarios reales por tema, sentimiento
   (positivo/neutral/negativo), excluyendo respuestas del dueño y triggers de
   automatización.
2. **FAQs / dudas repetidas** — extrae preguntas, agrupa por similitud
   semántica, ordena por frecuencia.
3. **Leads / intención de compra** — detecta comentarios-trigger (palabras
   CTA configurables) + intención de compra no listada explícitamente;
   detecta primero el trigger propio de cada reel a partir del caption y las
   respuestas del dueño. Entrega lista de usuarios interesados, deduplicada.
4. **Ideas de contenido nuevo** — sintetiza de lo anterior qué grabar después:
   gancho + formato + justificación, priorizado por impacto estimado.

El script hace solo la parte mecánica (bajar y tagear datos); el análisis lo
hace Claude leyendo los JSON, nunca hardcodeado en el script.

## Estructura del repo

```
ig-reels-insights/
├── SKILL.md              # definición de la skill (frontmatter + instrucciones)
├── README.md             # instalación, uso, firma de Aarón
├── LICENSE               # MIT
├── .env.example
├── .gitignore             # excluye .env y out/
└── scripts/
    └── ig_insights.py    # script único, Python 3 stdlib puro (urllib)
```

Nombre de la skill: `ig-reels-insights`, invocable como `/ig-reels-insights`.

## El script (`ig_insights.py`)

Python 3, solo librería estándar (sin `pip install`, sin `requests`).
Subcomandos vía `argparse`:

- `list` — últimos media (reels): id, tipo, likes, comentarios, fecha, caption
- `comments <media_id>` — comentarios + replies, paginación completa
- `insights <media_id>` — reach/saves/shares/etc., autodetectando qué
  métricas acepta la versión vigente de la Graph API
- `bundle <ids...> | --recent N [--out out/]` — media + insights +
  comentarios tagueados, un JSON por reel

Cada comentario tagueado con:
- `is_from_owner` — respuesta del dueño de la cuenta
- `is_trigger` + `matched_trigger` — coincide con la lista de triggers
  (`IG_TRIGGERS` en `.env`, configurable)

Comportamiento:
- Throttling configurable (`--throttle`, default razonable) + backoff
  exponencial ante rate limits (códigos 4/17/32/613/80004/429)
- Fail-fast ante errores duros (token vencido, media inaccesible)
- El token nunca aparece en mensajes de error ni logs

## Configuración

`.env` (con `.env.example` de plantilla, en `.gitignore`):

- `INSTAGRAM_ACCESS_TOKEN` — token long-lived / system user con permisos
  `instagram_basic`, `instagram_manage_comments`, `instagram_manage_insights`,
  `pages_read_engagement`
- `INSTAGRAM_BUSINESS_ACCOUNT_ID` — ID numérico de la cuenta Business/Creator
- `IG_TRIGGERS` — lista opcional de palabras-CTA propias, separadas por coma

Si el `.env` no existe, el flujo de la skill le pide el token y el account ID
al usuario y lo crea con la herramienta de escritura de archivos (nunca por
shell, para no dejar el token en el historial).

## Entregable en chat

1. Resumen global: nº de reels, comentarios totales, % sentimiento agregado,
   top 3 dudas, nº de leads, 5-8 ideas de contenido priorizadas
2. Por reel: mini-ficha con insights clave, sentimiento, dudas, leads
3. Tabla de leads (usuario, comentario, reel, trigger)

Para volumen alto, ofrece exportar a Markdown (`reporte-YYYY-MM-DD.md`) y/o
CSV (`leads.csv`, `comentarios.csv`).

## Seguridad y privacidad

- `.env` en `.gitignore` desde el primer commit, nunca se sube
- Token redactado de cualquier error antes de mostrarse
- `out/` en `.gitignore` — contiene usernames y comentarios de personas
  reales, README advierte no subir a repos públicos ni compartir fuera de
  quien lo corre

## Distribución

- Repo público en GitHub bajo `valladxres`, licencia MIT
- Instalación documentada en dos vías:
  - `npx skills add valladxres/ig-reels-insights` (usa el registro skills.sh
    solo como instalador — no requiere crear cuenta en ninguna plataforma)
  - Clonado/descarga manual: copiar la carpeta a `~/.claude/skills/`
- README con sección de crédito al final: enlaces a Instagram
  (https://www.instagram.com/valladxres/), comunidad en Skool
  (https://www.skool.com/idea-stack-6277/about) y YouTube
  (https://youtube.com/@valladaresia)

## Fuera de alcance

- No incluye UI ni dashboard — todo el análisis se entrega en el chat de
  Claude Code (+ exports opcionales a archivo)
- No gestiona la obtención del token de Meta (permisos, App Review) — el
  README explica los requisitos pero no automatiza ese proceso
- No soporta otras redes (TikTok, YouTube) — solo Instagram Graph API
