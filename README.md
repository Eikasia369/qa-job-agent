# QA Job Agent · Maxi

Agente automático que busca ofertas de QA 3 veces por día, scorea con tu CV,
manda un email con las novedades y publica un dashboard con todos los resultados.

---

## Estructura

```
qa-job-agent/
├── scraper.py                        # Script principal
├── requirements.txt
├── .github/
│   └── workflows/
│       └── job-agent.yml             # GitHub Actions (corre automático)
├── dashboard/
│   └── index.html                    # Dashboard estático
└── data/                             # Generado automáticamente
    ├── jobs.json                     # Resultados del último run
    └── seen_ids.json                 # Historial de ofertas ya vistas
```

---

## Setup paso a paso

### 1. Crear el repo en GitHub

1. Entrá a github.com → **New repository**
2. Nombre: `qa-job-agent` (o el que quieras)
3. **Public** (necesario para el dashboard gratis con GitHub Pages)
4. Crear

### 2. Subir los archivos

Opción A — desde la web de GitHub:
- Upload files → arrastrás todo el contenido de esta carpeta

Opción B — desde terminal:
```bash
cd qa-job-agent
git init
git remote add origin https://github.com/TU_USUARIO/qa-job-agent.git
git add .
git commit -m "init"
git push -u origin main
```

### 3. Configurar los secrets de Gmail

En GitHub → tu repo → **Settings → Secrets and variables → Actions → New secret**:

| Secret | Valor |
|--------|-------|
| `EMAIL_SENDER` | tu Gmail (ej: maxizaldua@gmail.com) |
| `EMAIL_PASSWORD` | App Password de Gmail (ver abajo) |
| `EMAIL_RECIPIENT` | donde querés recibir el mail (puede ser el mismo) |

**Cómo obtener el App Password de Gmail:**
1. Entrá a myaccount.google.com → Seguridad
2. Activá la verificación en dos pasos (si no la tenés)
3. Buscá "Contraseñas de aplicación"
4. Generá una para "Correo" → "Otro" → nombre: "QA Job Agent"
5. Copiá las 16 letras que aparecen → ese es el `EMAIL_PASSWORD`

### 4. Activar GitHub Actions

1. Ir a tu repo → pestaña **Actions**
2. Si pide confirmación, aceptar
3. Podés hacer un run manual: Actions → "QA Job Agent" → **Run workflow**
4. Chequeá que corra sin errores (tarda ~30 segundos)

### 5. Configurar el Dashboard

#### Opción A — GitHub Pages (recomendado, gratis)

1. Settings → Pages → Source: **Deploy from branch**
2. Branch: `main` / Folder: `/dashboard`
3. Guardá → en ~2 minutos tenés la URL: `https://TU_USUARIO.github.io/qa-job-agent`

4. Editá `dashboard/index.html` — buscá esta línea:
```js
const JOBS_URL = "REEMPLAZAR_CON_TU_URL_RAW";
```
Reemplazala con:
```js
const JOBS_URL = "https://raw.githubusercontent.com/TU_USUARIO/qa-job-agent/main/data/jobs.json";
```

#### Opción B — Abrir localmente

Misma config de JOBS_URL, pero abrís el HTML con el Python server:
```bash
cd dashboard
python -m http.server 8080
# Abrís http://localhost:8080
```

---

## Horario de ejecución

El agente corre automáticamente a las:
- **8:00 AM** hora Argentina
- **2:00 PM** hora Argentina  
- **8:00 PM** hora Argentina

Solo manda email cuando hay **ofertas nuevas** (que no viste antes).
El dashboard siempre muestra todas las relevantes del último run.

---

## Agregar Claude scoring (futuro)

Cuando quieras activar el análisis con IA, agregá el secret `ANTHROPIC_API_KEY`
y avisame — agrego el código al scraper para que Claude lea cada oferta
contra tu CV y dé un análisis real en lugar de keywords.
