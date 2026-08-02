---
name: ig-reels-insights
description: Analiza los comentarios e insights de TUS propios reels de Instagram vía la Graph API oficial de Meta (tu cuenta, tu token, sin scraping ni costo de terceros). Agrupa temas y sentimiento, extrae FAQs repetidas, detecta leads con intención de compra, y propone ideas de contenido nuevo. Úsala cuando el usuario pida "analiza mis reels", "qué comenta la gente en mi Instagram", "sácame los leads de este reel" o "qué contenido debería grabar según los comentarios".
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Bash
---

# /ig-reels-insights — Insights de tus reels de Instagram

Baja comentarios e insights de **tus** reels con **tu** token (Instagram Graph
API, no scraping) y saca: de qué habla la gente, qué preguntan, quién quiere
comprar y **qué contenido nuevo grabar**.

El **script** (`scripts/ig_insights.py`) hace el trabajo pesado: paginación
completa con replies, throttling y backoff ante rate limits, y tagueo de cada
comentario. El **análisis** lo haces tú (Claude) leyendo el JSON que produce.
No hardcodees el análisis en el script.

---

## 0 · Setup (una vez)

Credenciales en `.env` (junto a este archivo, copia de `.env.example`):

- `INSTAGRAM_ACCESS_TOKEN` — token long-lived o de system user, con permisos
  `instagram_basic`, `instagram_manage_comments`, `instagram_manage_insights`,
  `pages_read_engagement`.
- `INSTAGRAM_BUSINESS_ACCOUNT_ID` — ID numérico de la cuenta Business/Creator.
- `IG_TRIGGERS` (opcional) — palabras-CTA propias, separadas por coma, además
  de las por defecto (info, precio, quiero, guía, curso...).

El `.env` está en `.gitignore`. **Nunca** ecoes el token ni lo dejes en un
comando/output — el script ya lo redacta de sus errores.

Si el `.env` no existe todavía, pídele al usuario el token y el account ID y
créalo tú con la herramienta de escritura de archivos (no por Bash, para no
dejar el token en el historial de shell).

---

## 1 · Elegir qué reels analizar

Tres modos:

- **IDs directos** — si el usuario da media IDs, úsalos.
- **Links** — un permalink (`instagram.com/reel/ABC123/`) no resuelve directo
  al media ID. Corre `list` y cruza el campo `permalink` para encontrar el ID.
  Si el reel es viejo y no aparece entre los recientes, pide el media ID
  directo.
- **Recientes** — "los últimos N reels": usa `--recent N`.

```bash
cd <carpeta-de-esta-skill>
python3 scripts/ig_insights.py list --limit 30
```

---

## 2 · Bajar los datos

El comando `bundle` escribe, por cada reel, un JSON con `media` + `insights`
+ comentarios (planos, con replies incluidos) a una carpeta.

```bash
# por IDs concretos:
python3 scripts/ig_insights.py bundle 17841... 17899... --out out/

# o los N más recientes:
python3 scripts/ig_insights.py bundle --recent 5 --out out/
```

Escribe siempre a `out/` (está en `.gitignore`). Luego **lee** los `out/*.json`
para analizar. Comandos sueltos si hacen falta: `comments <media_id>` e
`insights <media_id>`.

Cada comentario viene tagueado:
- `is_from_owner` — lo escribió el dueño de la cuenta. **Fuera** del análisis
  de sentimiento.
- `is_trigger` + `matched_trigger` — coincide con la lista de triggers.
- El bloque `counts` trae `total_comments`, `real_comments` (sin dueño),
  `lead_candidates` (triggers).

### Rate limits / volumen
El script maneja rate limits (throttling `--throttle`, default 0.4s, +
backoff exponencial ante códigos 4/17/32/613/80004/429). Antes de correr un
reel con miles de comentarios, avísale al usuario y considera subir el
throttle (`--throttle 1.0`) o hacerlo por tandas.

---

## 3 · Los cuatro objetivos del análisis

Lee los JSON de `out/` y produce, **en este orden** (3c primero: detecta ahí
los triggers ocultos antes de calcular el pool de ruido que usan 3a y 3b):

### 3c · Leads / intención de compra  ⚠️ lógica invertida (hazla primero)
Aquí **no descartes** los triggers de automatización — **son la señal**.

> **Detecta el trigger de la campaña primero.** Cada reel con lead magnet usa
> una palabra-CTA propia ("comenta **GUÍA** y te la mando"). Antes de contar
> leads, mira el `caption` y busca comentarios cortos cuyo texto sea (casi)
> idéntico al de un comentario que **el dueño respondió con un DM
> automático** (mismo mensaje de respuesta, ej. "Te lo mandé al DM") — esa
> palabra ES el trigger de ese reel, aunque no esté en la lista default y
> **aunque aparezca una sola vez**. No hace falta que se repita varias veces
> para contar: una sola coincidencia patrón-de-respuesta-del-dueño + texto
> corto ya es evidencia suficiente. Marca mentalmente estos comentarios como
> "trigger detectado en 3c" — los necesitas también en 3a/3b.

- Pool de leads = comentarios con `is_trigger == true` **más** los triggers
  detectados en el paso anterior.
- Súmale cualquier comentario real con **intención explícita de adquirir o
  pagar** por lo ofrecido: menciona precio/costo, forma de pago, o pide
  directamente "cómo lo consigo" / "dónde lo compro". El criterio es
  adquisición, no solo interés en el tema — una pregunta sobre si el
  producto sirve para su caso (compatibilidad, requisitos) es una **duda**
  (va a 3b), no un lead, a menos que además pregunte precio o cómo
  comprarlo.
- Entregable: lista de usuarios interesados (`username`, comentario(s), reel,
  trigger/frase). **Deduplica por usuario**: si un mismo usuario aporta más
  de una señal (ej. un trigger + una pregunta de precio), fusiónalas en una
  sola fila con ambas señales listadas y márcalo como el más caliente de
  los dos.

### 3a · Temas y sentimiento
Agrupa los **comentarios reales** por tema y clasifica sentimiento (positivo
/ neutral / negativo).
- Excluye del sentimiento el ruido de automatización: `is_from_owner == true`,
  `is_trigger == true`, **y cualquier trigger oculto que hayas detectado en
  3c** (aunque el JSON no lo tuviera tagueado). Usa `real_comments` menos
  todo eso.
- Da % de cada sentimiento y los temas dominantes con ejemplos textuales
  reales (cita el comentario, no lo inventes).

### 3b · Preguntas frecuentes / dudas
Extrae comentarios que son **preguntas** (tienen `?`, o son interrogativas
implícitas: "y eso funciona en…", "sirve para…"), **excluyendo** los que ya
clasificaste como lead en 3c (precio/compra). Agrúpalos por similitud
semántica, ordena por frecuencia, entrega las más repetidas con conteo
aproximado.

### 3d · Ideas de contenido nuevo  ⭐ (el foco de esta skill)
De todo lo anterior, sintetiza qué grabar después:
- **Dudas repetidas → reel-respuesta**: cada FAQ del 3b es un guion.
  Prioriza por frecuencia.
- **Objeciones y fricciones** → contenido que las derriba.
- **Temas que encienden** (mejor sentimiento/engagement en `insights`) →
  ángulos nuevos del mismo tema.
- **Vacíos**: preguntas que nadie respondió, sub-temas con tracción.
- Para cada idea: gancho sugerido + formato (reel/carrusel) + por qué (qué
  comentario/patrón lo respalda). Ordena por impacto estimado.

---

## 4 · Entregable

Por defecto, en el chat:
1. **Resumen global** — nº de reels, comentarios totales, % sentimiento
   agregado, top 3 dudas, nº de leads, 5–8 ideas de contenido priorizadas.
2. **Por reel** — mini-ficha completa, nunca solo reach/likes/comments:
   - Alcance: `reach`, `views`
   - Interacción: `total_interactions`, `saved`, `shares`, likes, comments
   - **Retención (siempre inclúyela si está en el JSON):** `ig_reels_avg_watch_time`
     (tiempo promedio de reproducción, en ms) y `reels_skip_rate` (% que le
     pasó de largo casi al instante). Estas dos son la señal más directa de
     si el **hook** funcionó (skip rate alto = hook débil) y si la
     **estructura del guion** retuvo hasta el final (watch time alto
     respecto a la duración del reel = estructura sólida).
   - Sentimiento, dudas, leads
3. **Leads** — tabla de usuarios interesados.
4. **Si el usuario pide comparar reels** (qué hook/formato/estructura
   funciona mejor): cruza retención + skip rate de cada reel con lo que
   sepas de su guion o hook — si hay un guion correspondiente en su bóveda
   de Obsidian (`resources/guiones/`), léelo para relacionar el dato con la
   decisión creativa real (tipo de hook, si fue visual o verbal, dónde fue
   el tutorial). No inventes la relación causa-efecto si no tienes el guion
   — repórtala como hipótesis, no como hecho.

Si son varios reels o mucho volumen, ofrece exportar:
- **Markdown** — `reporte-YYYY-MM-DD.md` con el detalle completo.
- **CSV** — `leads.csv` (username, reel, comentario, trigger) y/o
  `comentarios.csv`. Pregunta qué formato prefiere antes de generar el
  archivo pesado.

---

## Notas

- El script falla-rápido ante un error duro de la API (token vencido, media
  inaccesible): revisa el mensaje (ya viene sin token) antes de reintentar.
  Token vencido → pide uno nuevo y actualiza el `.env`.
- `insights` prueba métricas una por una (la Graph API cambia el set válido
  entre versiones/tipos de media); las que fallan quedan en `_errors`, sin
  romper el resto del bundle. Confirmado con la API real: `impressions`,
  `profile_visits` y `follows` **no** están soportadas para media tipo
  REELS (siempre fallan) — por eso no están en la lista de métricas.
- Datos sensibles: los JSON en `out/` contienen usernames y comentarios de
  personas reales. No los subas a repos públicos ni los compartas fuera de
  quien los generó.
