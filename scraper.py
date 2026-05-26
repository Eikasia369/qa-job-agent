"""
QA Job Agent — Maxi Zaldua
Busca ofertas en múltiples fuentes, scorea con el CV, guarda JSON y manda email.
"""

import json
import os
import re
import smtplib
import hashlib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

# ─── Perfil extraído del CV de Maxi ──────────────────────────────────────────
PROFILE = {
    "roles": [
        "qa", "quality assurance", "tester", "qa engineer", "qa analyst",
        "qa lead", "qa automation", "qa manual", "sdet", "test engineer",
        "test analyst", "test lead", "quality engineer", "quality control",
        "software tester", "software testing", "game tester", "game qa",
    ],
    "skills": [
        "playwright", "postman", "api testing", "api rest", "automation",
        "selenium", "jira", "agile", "scrum", "manual testing", "regression",
        "javascript", "typescript", "sql", "cypress", "test case", "test plan",
        "bug", "defect", "ci/cd", "github actions", "zephyr", "testrail",
        "appium", "mobile testing", "functional testing", "exploratory",
        "acceptance testing", "e2e", "swagger", "insomnia", "web testing",
    ],
    "red_flags": [
        "10+ years", "15+ years", "20+ years",
        "staff engineer", "principal engineer",
    ],
    # Ubicaciones aceptadas — remoto sin restricción o Latam/Argentina
    "location_accept": [
        "remote", "worldwide", "anywhere", "work from home", "wfh",
        "latam", "latin america", "latinoamerica", "latinoamérica",
        "south america", "sudamerica", "sudamérica",
        "argentina", "buenos aires",
        # países Latam aceptados
        "colombia", "mexico", "méxico", "chile", "peru", "perú",
        "uruguay", "paraguay", "bolivia", "ecuador", "venezuela",
        "brazil", "brasil", "costa rica", "panama", "panamá",
    ],
    # Ubicaciones bloqueadas — NO aplicar aunque sea "remoto"
    "location_block": [
        "ireland", "irlanda", "uk", "united kingdom", "reino unido",
        "germany", "alemania", "france", "francia", "spain", "españa",
        "italy", "italia", "netherlands", "holanda", "portugal",
        "poland", "polonia", "sweden", "suecia", "norway", "noruega",
        "denmark", "dinamarca", "finland", "finlandia", "austria",
        "switzerland", "suiza", "belgium", "bélgica", "belgium",
        "australia", "new zealand", "nueva zelanda",
        "india", "china", "japan", "japón", "singapore", "singapur",
        "europe", "europa", "asia", "oceania",
        # USA/Canadá — solo si está explícito como requisito
        "us only", "usa only", "united states only", "canada only",
        "must be located in the us", "must reside in",
        "authorized to work in the us", "us citizen",
    ],
}


# ─── Filtro de ubicación ──────────────────────────────────────────────────────
def location_ok(job: dict) -> tuple[bool, str]:
    """
    Retorna (permitido, motivo).
    Lógica:
      - Si la ubicación contiene un término bloqueado → rechazar
      - Si la ubicación está vacía o es genérica ("remote", "worldwide") → aceptar
      - Si contiene un término aceptado → aceptar
      - Si no matchea nada → aceptar (beneficio de la duda, el scraper filtra después por score)
    """
    loc = (job.get("location") or "").lower()
    desc = (job.get("description") or "").lower()[:300]  # solo inicio de descripción
    full = f"{loc} {desc}"

    # Primero chequear bloqueos (tienen prioridad)
    for blocked in PROFILE["location_block"]:
        if blocked in full:
            return False, f"ubicación bloqueada: {blocked}"

    # Luego chequear aceptados
    for accepted in PROFILE["location_accept"]:
        if accepted in loc:
            return True, "ubicación aceptada"

    # Ubicación vacía o ambigua → aceptar con beneficio de la duda
    if not loc or loc in ("", "-", "—", "global", "n/a"):
        return True, "sin restricción"

    return True, "ubicación no determinada"

# ─── Scoring ──────────────────────────────────────────────────────────────────
def score_job(job: dict) -> dict:
    title = job.get("title", "").lower()
    desc  = job.get("description", "").lower()
    text  = f" {title} {desc} "
    score = 0
    matches = []
    warnings = []

    # Rol: más puntos si está en el título
    role_in_title = any(r in title for r in PROFILE["roles"])
    role_in_desc  = any(f" {r} " in text for r in PROFILE["roles"])

    if not role_in_title and not role_in_desc:
        return {"score": 0, "matches": [], "warnings": [], "verdict": "irrelevante"}

    score += 40 if role_in_title else 20
    matches.append("Rol QA ✓" if role_in_title else "Rol QA (desc)")

    for skill in PROFILE["skills"]:
        if skill in text:
            score += 5
            matches.append(skill)

    for flag in PROFILE["red_flags"]:
        if flag in text:
            score -= 20
            warnings.append(flag)

    loc = job.get("location", "").lower()
    if any(a in loc for a in PROFILE["location_accept"]):
        score += 10
        matches.append("Remoto/Latam 🌐")

    if job.get("salary"):
        score += 5
        matches.append("Salario 💰")

    score = max(0, min(100, score))
    verdict = (
        "excelente" if score >= 65 else
        "bueno"     if score >= 45 else
        "regular"   if score >= 20 else
        "bajo"
    )

    return {
        "score": score,
        "matches": matches[:8],
        "warnings": warnings,
        "verdict": verdict,
    }


# ─── Job ID para deduplicación ────────────────────────────────────────────────
def job_id(job: dict) -> str:
    key = f"{job.get('title','').lower().strip()}_{job.get('company','').lower().strip()}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


# ─── Fetchers ─────────────────────────────────────────────────────────────────
def fetch_remotive() -> list[dict]:
    url = "https://remotive.com/api/remote-jobs?search=QA&limit=50"
    data = requests.get(url, timeout=15).json()
    jobs = []
    for j in data.get("jobs", []):
        desc = re.sub(r"<[^>]+>", " ", j.get("description", ""))
        jobs.append({
            "title": j.get("title", ""),
            "company": j.get("company_name", ""),
            "location": j.get("candidate_required_location", "Remote"),
            "description": desc[:800],
            "date": j.get("publication_date", ""),
            "salary": j.get("salary") or None,
            "url": j.get("url", ""),
            "source": "Remotive",
        })
    return jobs


def fetch_workingnomads() -> list[dict]:
    url = "https://www.workingnomads.com/api/exposed_jobs/?category=testing&limit=50"
    data = requests.get(url, timeout=15).json()
    items = data if isinstance(data, list) else data.get("results", [])
    jobs = []
    for j in items:
        desc = re.sub(r"<[^>]+>", " ", str(j.get("description", "")))
        jobs.append({
            "title": j.get("title", ""),
            "company": j.get("company_name") or j.get("company", ""),
            "location": j.get("location", "Remote"),
            "description": desc[:800],
            "date": j.get("pub_date") or j.get("created_at", ""),
            "salary": None,
            "url": j.get("url") or j.get("apply_url", ""),
            "source": "WorkingNomads",
        })
    return jobs


def fetch_getonboard() -> list[dict]:
    url = "https://www.getonbrd.com/api/v0/search/jobs?query=QA&per_page=50"
    data = requests.get(url, timeout=15).json()
    jobs = []
    for item in data.get("data", []):
        a = item.get("attributes", {})
        desc = re.sub(r"<[^>]+>", " ", str(a.get("description", "")))
        salary = None
        if a.get("min_salary"):
            salary = f"{a.get('min_salary')}–{a.get('max_salary')}"
        jobs.append({
            "title": a.get("title", ""),
            "company": a.get("company_name") or a.get("company-name", ""),
            "location": a.get("remote_modality") or a.get("modality", "Remote"),
            "description": desc[:800],
            "date": a.get("published_at") or a.get("published-at", ""),
            "salary": salary,
            "url": a.get("url") or f"https://www.getonbrd.com/jobs/{item.get('id','')}",
            "source": "GetOnBoard",
        })
    return jobs


def fetch_himalayas() -> list[dict]:
    url = "https://himalayas.app/jobs/api?q=QA+quality+assurance&limit=30"
    data = requests.get(url, timeout=15).json()
    jobs = []
    for j in data.get("jobs", []):
        desc = re.sub(r"<[^>]+>", " ", str(j.get("description", "")))
        company = j.get("company", {})
        company_name = company.get("name", "") if isinstance(company, dict) else str(company)
        jobs.append({
            "title": j.get("title", ""),
            "company": company_name,
            "location": str(j.get("locationRestrictions") or j.get("location", "Remote")),
            "description": desc[:800],
            "date": j.get("publishedAt") or j.get("createdAt", ""),
            "salary": str(j.get("salary", "")) or None,
            "url": j.get("applicationLink") or j.get("url", ""),
            "source": "Himalayas",
        })
    return jobs


def fetch_jobicy() -> list[dict]:
    jobs = []
    for tag in ["quality+assurance", "game+tester"]:
        try:
            url = f"https://jobicy.com/api/v2/remote-jobs?count=30&tag={tag}"
            data = requests.get(url, timeout=15).json()
            for j in data.get("jobs", []):
                desc = re.sub(r"<[^>]+>", " ", str(j.get("jobDescription", "")))
                salary = None
                if j.get("salaryMin"):
                    salary = f"{j.get('salaryCurrency','')}{j.get('salaryMin')}–{j.get('salaryMax')}"
                jobs.append({
                    "title": j.get("jobTitle", ""),
                    "company": j.get("companyName", ""),
                    "location": j.get("jobGeo", "Remote"),
                    "description": desc[:800],
                    "date": j.get("pubDate", ""),
                    "salary": salary,
                    "url": j.get("url", ""),
                    "source": "Jobicy",
                })
        except Exception as e:
            print(f"  Jobicy tag={tag} error: {e}")
    return jobs


ALL_FETCHERS = {
    "Remotive":     fetch_remotive,
    "WorkingNomads": fetch_workingnomads,
    "GetOnBoard":   fetch_getonboard,
    "Himalayas":    fetch_himalayas,
    "Jobicy":       fetch_jobicy,
}


# ─── Deduplicación con historial ──────────────────────────────────────────────
SEEN_FILE = Path("data/seen_ids.json")

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()

def save_seen(seen: set):
    SEEN_FILE.parent.mkdir(exist_ok=True)
    SEEN_FILE.write_text(json.dumps(list(seen)))


# ─── Email HTML ───────────────────────────────────────────────────────────────
VERDICT_COLOR = {
    "excelente": "#00b894",
    "bueno":     "#fdcb6e",
    "regular":   "#a29bfe",
    "bajo":      "#888888",
}

def build_email_html(new_jobs: list[dict], run_stats: dict) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    total = run_stats.get("total_fetched", 0)
    sources = run_stats.get("sources", {})

    rows = ""
    for job in new_jobs[:30]:  # max 30 en el mail
        color = VERDICT_COLOR.get(job.get("verdict", "bajo"), "#888")
        matches = ", ".join(job.get("matches", [])[:5])
        warnings = " | ".join(f"⚠ {w}" for w in job.get("warnings", []))
        salary_tag = f'<span style="color:#00cec9">💰 {job["salary"]}</span> &nbsp;' if job.get("salary") else ""
        url_btn = (f'<a href="{job["url"]}" style="display:inline-block;padding:5px 12px;'
                   f'background:{color};color:#000;border-radius:5px;font-size:11px;'
                   f'font-weight:bold;text-decoration:none;margin-top:8px">Ver oferta →</a>'
                   if job.get("url") else "")
        rows += f"""
        <tr>
          <td style="padding:14px 16px;border-bottom:1px solid #1e1e1e;vertical-align:top">
            <div style="margin-bottom:4px">
              <span style="background:{color}22;color:{color};font-size:10px;font-weight:700;
                padding:2px 8px;border-radius:12px;letter-spacing:0.5px">
                {job.get('verdict','').upper()} · {job.get('score',0)}
              </span>
              &nbsp;
              <span style="color:#555;font-size:10px">{job.get('source','')}</span>
              &nbsp;{salary_tag}
            </div>
            <div style="font-size:15px;color:#e0e0e0;font-weight:600;margin:4px 0 2px">
              {job.get('title','')}
            </div>
            <div style="font-size:12px;color:#666;margin-bottom:6px">
              {job.get('company','')} · {job.get('location','')}
            </div>
            <div style="font-size:11px;color:#555;margin-bottom:4px">
              🏷 {matches}
            </div>
            {"<div style='font-size:10px;color:#ff6b6b'>" + warnings + "</div>" if warnings else ""}
            <div style="font-size:11px;color:#444;line-height:1.6;margin-top:6px">
              {job.get('description','')[:200]}{'...' if len(job.get('description',''))>200 else ''}
            </div>
            {url_btn}
          </td>
        </tr>"""

    source_summary = " &nbsp;·&nbsp; ".join(
        f'<span style="color:{["#00b894","#fd79a8","#e17055","#00cec9","#6c5ce7"][i%5]}">'
        f'{k}: {v}</span>'
        for i, (k, v) in enumerate(sources.items())
    )

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#0d0d0f;font-family:'Segoe UI',Arial,sans-serif">
  <div style="max-width:620px;margin:0 auto;padding:20px 16px">

    <!-- Header -->
    <div style="padding:20px 24px;border-bottom:1px solid #1a1a1a;margin-bottom:16px">
      <div style="font-size:9px;color:#333;letter-spacing:3px;margin-bottom:6px">JOB RADAR · QA</div>
      <h1 style="margin:0;font-size:22px;color:#eee;font-weight:400">
        {len(new_jobs)} ofertas nuevas
      </h1>
      <div style="font-size:11px;color:#444;margin-top:4px">{now} &nbsp;·&nbsp; {total} revisadas en total</div>
      <div style="font-size:10px;color:#333;margin-top:6px">{source_summary}</div>
    </div>

    <!-- Stats row -->
    <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap">
      {"".join(
        f'<div style="background:#111;border:1px solid #1e1e1e;border-radius:8px;padding:8px 14px">'
        f'<div style="font-size:18px;color:{VERDICT_COLOR[v]}">{sum(1 for j in new_jobs if j.get("verdict")==v)}</div>'
        f'<div style="font-size:9px;color:#444">{v.capitalize()}</div></div>'
        for v in ["excelente","bueno","regular"]
      )}
    </div>

    <!-- Jobs table -->
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#111;border:1px solid #1a1a1a;border-radius:10px;overflow:hidden">
      {rows if rows else '<tr><td style="padding:20px;color:#444;text-align:center">No hay ofertas nuevas en esta corrida</td></tr>'}
    </table>

    <div style="text-align:center;margin-top:16px;font-size:10px;color:#2a2a2a">
      QA Job Agent · GitHub Actions · {now}
    </div>
  </div>
</body>
</html>"""


# ─── Envío de email ───────────────────────────────────────────────────────────
def send_email(subject: str, html: str):
    sender    = os.environ["EMAIL_SENDER"]
    password  = os.environ["EMAIL_PASSWORD"]   # Gmail App Password
    recipient = os.environ["EMAIL_RECIPIENT"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    print(f"  Email enviado a {recipient}")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"QA Job Agent — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*50}\n")

    seen = load_seen()
    all_jobs = []
    sources_count = {}

    for name, fetcher in ALL_FETCHERS.items():
        print(f"Fetching {name}...")
        try:
            jobs = fetcher()
            sources_count[name] = len(jobs)
            all_jobs.extend(jobs)
            print(f"  ✓ {len(jobs)} ofertas")
        except Exception as e:
            sources_count[name] = 0
            print(f"  ✗ Error: {e}")

    print(f"\nTotal fetched: {len(all_jobs)}")

    # Dedup dentro de esta corrida
    seen_this_run = set()
    unique_jobs = []
    for job in all_jobs:
        jid = job_id(job)
        if jid not in seen_this_run:
            seen_this_run.add(jid)
            unique_jobs.append({**job, "id": jid})

    print(f"Unique jobs: {len(unique_jobs)}")

    # Scorear todos
    scored = []
    blocked_count = 0
    for job in unique_jobs:
        # Filtro de ubicación primero
        ok, reason = location_ok(job)
        if not ok:
            blocked_count += 1
            print(f"  Bloqueado ({reason}): {job.get('title')} @ {job.get('location')}")
            continue
        s = score_job(job)
        if s["verdict"] != "irrelevante":
            scored.append({**job, **s})
    print(f"Bloqueadas por ubicación: {blocked_count}")

    scored.sort(key=lambda x: x["score"], reverse=True)
    print(f"Relevant jobs: {len(scored)}")

    # Separar nuevas vs ya vistas
    new_jobs = [j for j in scored if j["id"] not in seen]
    print(f"New jobs: {len(new_jobs)}")

    # Actualizar seen
    new_seen = seen | {j["id"] for j in scored}
    save_seen(new_seen)

    # Guardar JSON para el dashboard
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_fetched": len(all_jobs),
        "sources": sources_count,
        "new_count": len(new_jobs),
        "jobs": scored,           # todas las relevantes (para el dashboard)
        "new_jobs": new_jobs,     # solo las nuevas (para el email)
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/jobs.json").write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print("  ✓ data/jobs.json guardado")

    # Email
    if new_jobs:
        stats = {"total_fetched": len(all_jobs), "sources": sources_count}
        html = build_email_html(new_jobs, stats)
        subject = f"🎯 {len(new_jobs)} ofertas QA nuevas — {datetime.now().strftime('%d/%m %H:%M')}"
        try:
            send_email(subject, html)
        except Exception as e:
            print(f"  ✗ Error enviando email: {e}")
    else:
        print("  Sin ofertas nuevas, no se envía email.")

    print(f"\n{'='*50}")
    print("Done.")


if __name__ == "__main__":
    main()
