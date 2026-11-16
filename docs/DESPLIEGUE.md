# FireSeason — Cómo publicarlo en internet

Dos partes, dos servicios gratuitos:

| Parte | Carpeta | Servicio | Qué hace |
|---|---|---|---|
| Backend (Python, FastAPI) | `backend/` | **Render** | Lee los datos, consulta NASA FIRMS cada 15 min, calcula riesgos y predicciones |
| Frontend (React) | `frontend/` | **Vercel** | Las páginas que ve la gente |

Vercel reenvía todo lo que empieza con `/api/` al backend de Render (archivo `frontend/vercel.json`).

---

## 1. Subir el proyecto a GitHub

1. Crea un repositorio nuevo en https://github.com/new (por ejemplo `fireseason`). Puede ser público.
2. Desde la carpeta `fireseason/`:
   ```
   git remote add origin https://github.com/TU_USUARIO/fireseason.git
   git push -u origin master
   ```
   El archivo `.env` (con tu clave de FIRMS) **no** se sube: está en `.gitignore`.
   Los datos que necesita el backend (~28 MB en `data/processed/`) **sí** se suben.

## 2. Backend en Render

1. Entra a https://render.com y regístrate con tu cuenta de GitHub.
2. **New → Blueprint** → elige el repositorio `fireseason`. Render lee `render.yaml`.
3. Te pedirá **FIRMS_MAP_KEY**: pega tu clave (la misma de tu archivo `.env`).
4. Espera a que termine (5–10 min la primera vez). Te dará una dirección como
   `https://fireseason-api.onrender.com`.
5. Pruébala: abre `https://fireseason-api.onrender.com/api/salud` → debe decir `{"estado":"ok"}`.

> Plan gratuito: si nadie entra por 15 min, el backend "se duerme" y la siguiente visita tarda ~1 min
> en despertar. Antes de presentar a los jueces, abre la página un minuto antes.

## 3. Frontend en Vercel

1. En `frontend/vercel.json`, cambia `CAMBIAR-POR-TU-BACKEND.onrender.com` por la dirección que te dio Render.
   Guarda, haz commit y `git push`.
2. Entra a https://vercel.com, regístrate con GitHub → **Add New → Project** → elige `fireseason`.
3. En **Root Directory** elige `frontend`. Vercel detecta Vite solo. **Deploy**.
4. Te dará una dirección como `https://fireseason.vercel.app`. ¡Listo!

## Actualizar después

Cada `git push` a GitHub vuelve a publicar automáticamente en Render y en Vercel.
Si vuelves a correr el pipeline (pasos 1–6), haz commit de los archivos nuevos de `data/processed/`.
