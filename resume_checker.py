import csv
import html
import io
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "resume_history.db"

SECTION_PATTERNS = {
    "Summary": r"\b(summary|profile|objective|about)\b",
    "Experience": r"\b(experience|employment|work history|professional experience)\b",
    "Education": r"\b(education|qualification|degree|university|college)\b",
    "Skills": r"\b(skills|technical skills|tools|technologies)\b",
    "Projects": r"\b(projects|portfolio|selected work)\b",
    "Certifications": r"\b(certifications|certificates|licenses)\b",
}

SKILL_KEYWORDS = {
    "Programming": [
        "python",
        "java",
        "javascript",
        "typescript",
        "c++",
        "c#",
        "php",
        "ruby",
        "go",
        "rust",
        "sql",
    ],
    "Data": [
        "excel",
        "power bi",
        "tableau",
        "pandas",
        "numpy",
        "scikit-learn",
        "machine learning",
        "data analysis",
        "statistics",
        "dashboard",
    ],
    "Web": [
        "html",
        "css",
        "react",
        "angular",
        "vue",
        "node",
        "django",
        "flask",
        "fastapi",
        "rest api",
    ],
    "Cloud and DevOps": [
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "git",
        "github",
        "ci/cd",
        "linux",
    ],
    "Professional": [
        "communication",
        "leadership",
        "teamwork",
        "problem solving",
        "project management",
        "stakeholder",
        "presentation",
    ],
}

CATEGORY_PROFILES = {
    "Software Engineer": ["python", "java", "javascript", "api", "git", "testing", "backend", "frontend"],
    "Data Analyst": ["sql", "excel", "tableau", "power bi", "dashboard", "statistics", "analysis"],
    "Data Scientist": ["python", "machine learning", "statistics", "pandas", "numpy", "model", "scikit-learn"],
    "Web Developer": ["html", "css", "react", "javascript", "node", "api", "frontend"],
    "DevOps Engineer": ["aws", "azure", "docker", "kubernetes", "linux", "ci/cd", "terraform"],
    "Project Manager": ["project management", "stakeholder", "planning", "delivery", "risk", "leadership"],
    "Marketing": ["campaign", "seo", "content", "brand", "analytics", "social media", "conversion"],
    "Human Resources": ["recruitment", "onboarding", "employee", "policy", "payroll", "training"],
}

ACTION_VERBS = {
    "achieved",
    "automated",
    "built",
    "created",
    "delivered",
    "designed",
    "developed",
    "improved",
    "increased",
    "launched",
    "led",
    "managed",
    "optimized",
    "reduced",
    "shipped",
}

WEAK_PHRASES = {
    "responsible for": "Replace 'responsible for' with a direct action verb such as 'managed', 'built', or 'delivered'.",
    "worked on": "Replace 'worked on' with the actual contribution and result.",
    "helped with": "Clarify ownership by saying what you personally improved, created, or supported.",
    "duties included": "Turn duties into achievement bullets with impact.",
    "hard worker": "Show evidence through outcomes, tools, and measurable results.",
}

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "you",
    "your",
    "will",
    "work",
    "team",
    "using",
    "role",
}


@dataclass
class BulletReview:
    bullet: str
    score: int
    notes: list[str]


@dataclass
class ResumeAnalysis:
    file_name: str
    text: str
    word_count: int
    contact: dict[str, str]
    sections: dict[str, bool]
    section_feedback: dict[str, str]
    skills: dict[str, list[str]]
    score: int
    ats_score: int
    category: str
    strengths: list[str]
    improvements: list[str]
    missing_keywords: list[str]
    matched_keywords: list[str]
    missing_skills: list[str]
    wording_suggestions: list[str]
    bullet_reviews: list[BulletReview]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z+#./-]{1,}", text.lower())
        if token not in STOP_WORDS and len(token) > 2
    ]


def contains_keyword(text: str, keyword: str) -> bool:
    pattern = r"(?<!\w)" + re.escape(keyword.lower()) + r"(?!\w)"
    return bool(re.search(pattern, text.lower()))


def extract_content(uploaded_file) -> str:
    import PyPDF2

    file_bytes = uploaded_file.getvalue()
    suffix = uploaded_file.name.lower().rsplit(".", 1)[-1]

    if suffix == "pdf":
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(page.strip() for page in pages if page.strip())

    return file_bytes.decode("utf-8", errors="ignore")


def find_contact(text: str) -> dict[str, str]:
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(\+?\d[\d\s().-]{7,}\d)", text)
    linkedin = re.search(r"(https?://)?(www\.)?linkedin\.com/[^\s)]+", text, re.I)
    github = re.search(r"(https?://)?(www\.)?github\.com/[^\s)]+", text, re.I)

    return {
        "Email": email.group(0) if email else "Not found",
        "Phone": phone.group(0).strip() if phone else "Not found",
        "LinkedIn": linkedin.group(0) if linkedin else "Not found",
        "GitHub": github.group(0) if github else "Not found",
    }


def find_sections(text: str) -> dict[str, bool]:
    lowered = text.lower()
    return {
        section: bool(re.search(pattern, lowered))
        for section, pattern in SECTION_PATTERNS.items()
    }


def build_section_feedback(sections: dict[str, bool]) -> dict[str, str]:
    feedback = {}
    for section, present in sections.items():
        if present:
            feedback[section] = "Found. Make sure this section is concise and result-focused."
        else:
            feedback[section] = f"Missing. Add a clear {section.lower()} section if it applies to the role."
    return feedback


def find_skills(text: str) -> dict[str, list[str]]:
    return {
        group: [keyword for keyword in keywords if contains_keyword(text, keyword)]
        for group, keywords in SKILL_KEYWORDS.items()
    }


def flatten_skills(skills: dict[str, list[str]]) -> list[str]:
    return [skill for values in skills.values() for skill in values]


def top_keywords(text: str, limit: int = 25) -> list[str]:
    counts = Counter(tokens(text))
    return [word for word, _ in counts.most_common(limit)]


def keyword_overlap(resume_text: str, job_description: str) -> tuple[list[str], list[str]]:
    if not job_description.strip():
        return [], []

    resume_words = set(tokens(resume_text))
    job_words = top_keywords(job_description, 35)
    matched = [word for word in job_words if word in resume_words]
    missing = [word for word in job_words if word not in resume_words]
    return matched[:20], missing[:20]


def missing_job_skills(resume_text: str, job_description: str) -> list[str]:
    if not job_description.strip():
        return []

    missing = []
    all_skills = [skill for values in SKILL_KEYWORDS.values() for skill in values]
    for skill in all_skills:
        if contains_keyword(job_description, skill) and not contains_keyword(resume_text, skill):
            missing.append(skill)
    return missing[:20]


def calculate_ats_score(matched_keywords: Iterable[str], missing_keywords: Iterable[str], sections: dict[str, bool]) -> int:
    matched_count = len(list(matched_keywords))
    missing_count = len(list(missing_keywords))
    keyword_score = 60 if matched_count + missing_count == 0 else round(70 * matched_count / max(1, matched_count + missing_count))
    section_score = round(30 * sum(sections.values()) / max(1, len(sections)))
    return max(0, min(100, keyword_score + section_score))


def predict_category(text: str, job_description: str = "") -> str:
    combined = f"{text} {job_description}".lower()
    scores = {}
    for category, keywords in CATEGORY_PROFILES.items():
        scores[category] = sum(2 if " " in keyword else 1 for keyword in keywords if contains_keyword(combined, keyword))
    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    return best_category if best_score else "General"


def extract_bullets(text: str) -> list[str]:
    bullets = []
    for line in text.splitlines():
        cleaned = line.strip(" \t-*•–—")
        if len(cleaned) < 25:
            continue
        if line.lstrip().startswith(("-", "*", "•", "–", "—")) or re.match(r"^\s*\d+[.)]", line):
            bullets.append(cleaned)
    if bullets:
        return bullets[:12]

    sentences = re.split(r"(?<=[.!?])\s+", normalize_text(text))
    return [sentence for sentence in sentences if 45 <= len(sentence) <= 220][:8]


def review_bullet(bullet: str) -> BulletReview:
    lowered = bullet.lower()
    score = 40
    notes = []

    if any(lowered.startswith(verb) or f" {verb} " in lowered for verb in ACTION_VERBS):
        score += 20
    else:
        notes.append("Start with a stronger action verb.")

    if re.search(r"\d|%|\$|revenue|users|hours|days|cost", lowered):
        score += 25
    else:
        notes.append("Add a number, percentage, or measurable result.")

    if 55 <= len(bullet) <= 160:
        score += 15
    else:
        notes.append("Keep the bullet focused and easy to scan.")

    if any(phrase in lowered for phrase in WEAK_PHRASES):
        score -= 10
        notes.append("Replace weak wording with specific ownership and outcome.")

    return BulletReview(bullet=bullet, score=max(0, min(100, score)), notes=notes or ["Strong, specific bullet."])


def wording_suggestions(text: str) -> list[str]:
    lowered = text.lower()
    suggestions = [message for phrase, message in WEAK_PHRASES.items() if phrase in lowered]
    passive_matches = re.findall(r"\b(was|were|been|being)\s+\w+ed\b", lowered)
    if passive_matches:
        suggestions.append("Reduce passive voice by making the person and action clearer.")
    return suggestions[:10]


def calculate_score(
    text: str,
    contact: dict[str, str],
    sections: dict[str, bool],
    skills: dict[str, list[str]],
    ats_score: int,
    bullet_reviews: list[BulletReview],
) -> int:
    word_count = len(tokens(text))
    skill_count = len(flatten_skills(skills))
    contact_score = sum(4 for value in contact.values() if value != "Not found")
    section_score = round(22 * sum(sections.values()) / max(1, len(sections)))
    skill_score = min(20, skill_count * 2)
    length_score = min(16, word_count // 25)
    bullet_score = 10 if not bullet_reviews else round(16 * sum(item.score for item in bullet_reviews) / (100 * len(bullet_reviews)))
    total = contact_score + section_score + skill_score + length_score + bullet_score + round(ats_score * 0.1)
    return max(0, min(100, total))


def build_feedback(
    word_count: int,
    contact: dict[str, str],
    sections: dict[str, bool],
    skills: dict[str, list[str]],
    missing_keywords: list[str],
    missing_skills: list[str],
    bullet_reviews: list[BulletReview],
) -> tuple[list[str], list[str]]:
    strengths = []
    improvements = []
    skill_count = len(flatten_skills(skills))

    if word_count >= 250:
        strengths.append("Resume has enough text for a meaningful review.")
    else:
        improvements.append("Add more detail about responsibilities, tools, and measurable outcomes.")

    if contact["Email"] != "Not found" and contact["Phone"] != "Not found":
        strengths.append("Core contact information is easy to find.")
    else:
        improvements.append("Include a clear email address and phone number near the top.")

    found_sections = [section for section, present in sections.items() if present]
    missing_sections = [section for section, present in sections.items() if not present]
    if found_sections:
        strengths.append("Detected sections: " + ", ".join(found_sections) + ".")
    if missing_sections:
        improvements.append("Consider adding these sections: " + ", ".join(missing_sections) + ".")

    if skill_count >= 6:
        strengths.append(f"Detected {skill_count} relevant skills.")
    else:
        improvements.append("Add a concise skills section with tools, technologies, and domain strengths.")

    weak_bullets = [item for item in bullet_reviews if item.score < 70]
    if weak_bullets:
        improvements.append("Improve experience bullets with stronger verbs and measurable outcomes.")
    elif bullet_reviews:
        strengths.append("Experience bullets are written with good impact signals.")

    if missing_skills:
        improvements.append("Missing role skills from the job description: " + ", ".join(missing_skills[:8]) + ".")
    elif missing_keywords:
        improvements.append("Work in job-description keywords where truthful: " + ", ".join(missing_keywords[:8]) + ".")

    return strengths, improvements


def analyze_resume(file_name: str, text: str, job_description: str) -> ResumeAnalysis:
    clean_text = normalize_text(text)
    contact = find_contact(clean_text)
    sections = find_sections(clean_text)
    section_feedback = build_section_feedback(sections)
    skills = find_skills(clean_text)
    matched_keywords, missing_keywords = keyword_overlap(clean_text, job_description)
    missing_skills = missing_job_skills(clean_text, job_description)
    bullet_reviews = [review_bullet(bullet) for bullet in extract_bullets(text)]
    ats_score = calculate_ats_score(matched_keywords, missing_keywords, sections)
    score = calculate_score(clean_text, contact, sections, skills, ats_score, bullet_reviews)
    strengths, improvements = build_feedback(
        len(tokens(clean_text)),
        contact,
        sections,
        skills,
        missing_keywords,
        missing_skills,
        bullet_reviews,
    )

    return ResumeAnalysis(
        file_name=file_name,
        text=clean_text,
        word_count=len(tokens(clean_text)),
        contact=contact,
        sections=sections,
        section_feedback=section_feedback,
        skills=skills,
        score=score,
        ats_score=ats_score,
        category=predict_category(clean_text, job_description),
        strengths=strengths,
        improvements=improvements,
        missing_keywords=missing_keywords,
        matched_keywords=matched_keywords,
        missing_skills=missing_skills,
        wording_suggestions=wording_suggestions(clean_text),
        bullet_reviews=bullet_reviews,
    )


def answer_question(question: str, analysis: ResumeAnalysis) -> str:
    question = question.lower().strip()

    if any(word in question for word in ["ats", "match", "job"]):
        return f"ATS job match is {analysis.ats_score}/100. Missing keywords: {', '.join(analysis.missing_keywords) or 'none'}."
    if any(word in question for word in ["score", "rating"]):
        return f"The overall resume score is {analysis.score}/100."
    if "category" in question or "role" in question:
        return f"This resume looks closest to: {analysis.category}."
    if "skill" in question:
        skills = flatten_skills(analysis.skills)
        return "Detected skills: " + (", ".join(skills) if skills else "none found yet.")
    if any(word in question for word in ["email", "phone", "contact", "linkedin", "github"]):
        return "\n".join(f"{key}: {value}" for key, value in analysis.contact.items())
    if any(word in question for word in ["missing", "improve", "weak"]):
        return "\n".join(analysis.improvements) if analysis.improvements else "No major improvements found."
    if "bullet" in question:
        return "\n".join(f"{item.score}/100 - {item.bullet}" for item in analysis.bullet_reviews[:5]) or "No bullets found."
    if "summary" in question:
        return analysis.text[:700] + ("..." if len(analysis.text) > 700 else "")

    return "Try asking about ATS match, score, category, skills, contact details, bullets, or improvements."


def analysis_row(analysis: ResumeAnalysis) -> dict[str, object]:
    return {
        "file_name": analysis.file_name,
        "score": analysis.score,
        "ats_score": analysis.ats_score,
        "category": analysis.category,
        "word_count": analysis.word_count,
        "skills": ", ".join(flatten_skills(analysis.skills)),
        "matched_keywords": ", ".join(analysis.matched_keywords),
        "missing_keywords": ", ".join(analysis.missing_keywords),
        "missing_skills": ", ".join(analysis.missing_skills),
    }


def analyses_csv(analyses: list[ResumeAnalysis]) -> bytes:
    output = io.StringIO()
    rows = [analysis_row(item) for item in analyses]
    if not rows:
        return b""
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def html_report(analysis: ResumeAnalysis) -> bytes:
    strengths = "".join(f"<li>{html.escape(item)}</li>" for item in analysis.strengths)
    improvements = "".join(f"<li>{html.escape(item)}</li>" for item in analysis.improvements)
    bullets = "".join(
        f"<li><strong>{item.score}/100</strong> {html.escape(item.bullet)}<br><small>{html.escape('; '.join(item.notes))}</small></li>"
        for item in analysis.bullet_reviews
    )
    content = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Resume Analysis - {html.escape(analysis.file_name)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 40px; color: #172033; }}
    h1, h2 {{ color: #0f3d5e; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
    .metric {{ border: 1px solid #ccd6e0; padding: 12px; border-radius: 6px; }}
    li {{ margin: 8px 0; }}
  </style>
</head>
<body>
  <h1>Resume Analysis</h1>
  <p><strong>File:</strong> {html.escape(analysis.file_name)}</p>
  <div class="metrics">
    <div class="metric"><strong>Overall</strong><br>{analysis.score}/100</div>
    <div class="metric"><strong>ATS Match</strong><br>{analysis.ats_score}/100</div>
    <div class="metric"><strong>Category</strong><br>{html.escape(analysis.category)}</div>
    <div class="metric"><strong>Words</strong><br>{analysis.word_count}</div>
  </div>
  <h2>Strengths</h2><ul>{strengths}</ul>
  <h2>Improvements</h2><ul>{improvements}</ul>
  <h2>Missing Keywords</h2><p>{html.escape(", ".join(analysis.missing_keywords) or "None")}</p>
  <h2>Bullet Review</h2><ul>{bullets or "<li>No bullets found.</li>"}</ul>
</body>
</html>"""
    return content.encode("utf-8")


def pdf_report(analysis: ResumeAnalysis) -> bytes | None:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except Exception:
        return None

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Resume Analysis", styles["Title"]),
        Paragraph(f"File: {analysis.file_name}", styles["Normal"]),
        Paragraph(f"Overall score: {analysis.score}/100", styles["Normal"]),
        Paragraph(f"ATS match: {analysis.ats_score}/100", styles["Normal"]),
        Paragraph(f"Predicted category: {analysis.category}", styles["Normal"]),
        Spacer(1, 12),
        Paragraph("Strengths", styles["Heading2"]),
    ]
    for item in analysis.strengths:
        story.append(Paragraph(f"- {item}", styles["Normal"]))
    story.append(Paragraph("Improvements", styles["Heading2"]))
    for item in analysis.improvements:
        story.append(Paragraph(f"- {item}", styles["Normal"]))
    story.append(Paragraph("Missing Keywords", styles["Heading2"]))
    story.append(Paragraph(", ".join(analysis.missing_keywords) or "None", styles["Normal"]))
    doc.build(story)
    return output.getvalue()


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                file_name TEXT NOT NULL,
                score INTEGER NOT NULL,
                ats_score INTEGER NOT NULL,
                category TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                missing_keywords TEXT NOT NULL,
                missing_skills TEXT NOT NULL
            )
            """
        )


def save_history(analyses: list[ResumeAnalysis]) -> None:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO analyses (
                created_at, file_name, score, ats_score, category, word_count,
                missing_keywords, missing_skills
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    now,
                    item.file_name,
                    item.score,
                    item.ats_score,
                    item.category,
                    item.word_count,
                    ", ".join(item.missing_keywords),
                    ", ".join(item.missing_skills),
                )
                for item in analyses
            ],
        )


def load_history(limit: int = 50) -> list[dict[str, object]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM analyses ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def render_analysis(st, analysis: ResumeAnalysis) -> None:
    score_col, ats_col, category_col, skills_col = st.columns(4)
    score_col.metric("Overall score", f"{analysis.score}/100")
    ats_col.metric("ATS match", f"{analysis.ats_score}/100")
    category_col.metric("Category", analysis.category)
    skills_col.metric("Skills found", len(flatten_skills(analysis.skills)))

    overview_tab, sections_tab, bullets_tab, wording_tab, report_tab = st.tabs(
        ["Overview", "Sections", "Bullets", "Wording", "Export"]
    )

    with overview_tab:
        left, right = st.columns(2)
        with left:
            st.subheader("Strengths")
            for item in analysis.strengths:
                st.success(item)
            st.subheader("Detected skills")
            for group, values in analysis.skills.items():
                st.write(f"**{group}:** {', '.join(values) if values else 'None found'}")
        with right:
            st.subheader("Improvements")
            for item in analysis.improvements:
                st.warning(item)
            st.subheader("Contact details")
            for key, value in analysis.contact.items():
                st.write(f"**{key}:** {value}")

        st.subheader("Job keyword match")
        keyword_left, keyword_right, skill_gap = st.columns(3)
        keyword_left.write("**Matched keywords**")
        keyword_left.write(", ".join(analysis.matched_keywords) if analysis.matched_keywords else "No job description provided.")
        keyword_right.write("**Missing keywords**")
        keyword_right.write(", ".join(analysis.missing_keywords) if analysis.missing_keywords else "None")
        skill_gap.write("**Missing skills**")
        skill_gap.write(", ".join(analysis.missing_skills) if analysis.missing_skills else "None")

    with sections_tab:
        st.dataframe(
            [
                {"section": name, "status": "Found" if found else "Missing", "feedback": analysis.section_feedback[name]}
                for name, found in analysis.sections.items()
            ],
            use_container_width=True,
            hide_index=True,
        )

    with bullets_tab:
        if not analysis.bullet_reviews:
            st.info("No resume bullets were found.")
        for item in analysis.bullet_reviews:
            st.progress(item.score / 100, text=f"{item.score}/100")
            st.write(item.bullet)
            st.caption("; ".join(item.notes))

    with wording_tab:
        if analysis.wording_suggestions:
            for item in analysis.wording_suggestions:
                st.warning(item)
        else:
            st.success("No common weak wording patterns were detected.")
        with st.expander("Resume text"):
            st.write(analysis.text)

    with report_tab:
        st.download_button(
            "Download CSV",
            analyses_csv([analysis]),
            file_name=f"{analysis.file_name}_analysis.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download printable HTML report",
            html_report(analysis),
            file_name=f"{analysis.file_name}_analysis.html",
            mime="text/html",
        )
        pdf_bytes = pdf_report(analysis)
        if pdf_bytes:
            st.download_button(
                "Download PDF report",
                pdf_bytes,
                file_name=f"{analysis.file_name}_analysis.pdf",
                mime="application/pdf",
            )
        else:
            st.caption("Install `reportlab` to enable direct PDF export. The HTML report can be printed to PDF.")

    st.subheader("Ask about this resume")
    question = st.text_input("Question", placeholder="Example: What should I improve?", key=f"q_{analysis.file_name}")
    if question:
        st.write(answer_question(question, analysis))


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Resume Checker", page_icon=":page_facing_up:", layout="wide")
    init_db()

    st.title("Resume Checker")
    st.caption("ATS matching, resume quality checks, recruiter ranking, history, and exportable reports.")

    with st.sidebar:
        st.header("Inputs")
        mode = st.radio("Mode", ["Candidate", "Recruiter"], horizontal=True)
        uploaded_files = st.file_uploader(
            "Resume files",
            type=["pdf", "txt"],
            accept_multiple_files=True,
        )
        job_description = st.text_area(
            "Job description",
            height=240,
            placeholder="Paste the job description here for ATS matching.",
        )
        analyze_button = st.button("Analyze", type="primary", use_container_width=True)

    if "analyses" not in st.session_state:
        st.session_state.analyses = []

    if analyze_button:
        if not uploaded_files:
            st.error("Upload at least one PDF or TXT resume.")
        else:
            analyses = []
            for uploaded_file in uploaded_files:
                try:
                    resume_text = extract_content(uploaded_file)
                    if resume_text.strip():
                        analyses.append(analyze_resume(uploaded_file.name, resume_text, job_description))
                    else:
                        st.warning(f"No readable text found in {uploaded_file.name}.")
                except Exception as exc:
                    st.error(f"Could not analyze {uploaded_file.name}: {exc}")
            st.session_state.analyses = sorted(analyses, key=lambda item: (item.ats_score, item.score), reverse=True)
            if analyses:
                save_history(st.session_state.analyses)

    analyses: list[ResumeAnalysis] = st.session_state.analyses

    dashboard_tab, analysis_tab, history_tab = st.tabs(["Dashboard", "Analysis", "History"])

    with dashboard_tab:
        if not analyses:
            st.info("Upload one or more resumes from the sidebar to begin.")
        else:
            rows = [analysis_row(item) for item in analyses]
            st.subheader("Ranking")
            st.dataframe(rows, use_container_width=True, hide_index=True)
            st.download_button("Download all results CSV", analyses_csv(analyses), "resume_rankings.csv", "text/csv")

            if mode == "Recruiter":
                st.subheader("Recruiter shortlist")
                min_ats = st.slider("Minimum ATS score", 0, 100, 65)
                required_skill = st.text_input("Required skill filter", placeholder="Example: python")
                shortlisted = [
                    item
                    for item in analyses
                    if item.ats_score >= min_ats
                    and (not required_skill or contains_keyword(" ".join(flatten_skills(item.skills)), required_skill))
                ]
                st.dataframe([analysis_row(item) for item in shortlisted], use_container_width=True, hide_index=True)

    with analysis_tab:
        if not analyses:
            st.info("No analysis yet.")
        else:
            selected_name = st.selectbox("Select resume", [item.file_name for item in analyses])
            selected = next(item for item in analyses if item.file_name == selected_name)
            render_analysis(st, selected)

    with history_tab:
        rows = load_history()
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No saved analyses yet.")


if __name__ == "__main__":
    main()
