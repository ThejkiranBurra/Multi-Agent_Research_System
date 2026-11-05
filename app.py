"""
Nexus Research - premium Streamlit front-end for the multi-agent research system.

Backend is untouched: this file imports `run_research_pipeline` from pipeline.py
and streams its console output into the UI to drive the live progress tracker.
"""
import html
import io
import json
import re
import time
from contextlib import redirect_stdout
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from pipeline import run_research_pipeline  # existing backend, unchanged

# ============================================================================
# PAGE CONFIG + STYLES
# ============================================================================
st.set_page_config(
    page_title="Nexus Research",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS_PATH = Path(__file__).parent / "styles.css"
st.markdown(f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

# ============================================================================
# CONSTANTS
# ============================================================================
STEPS = [
    ("Search Agent", "search", "Finds recent, reliable sources across the web."),
    ("Reader Agent", "book-open", "Scrapes the most relevant page for depth."),
    ("Writer Chain", "pen-line", "Synthesises all research into a report."),
    ("Critic Chain", "shield-check", "Reviews quality, gaps and accuracy."),
]
STEP_RE = re.compile(r"^step\s*(\d)\s*[-–]", re.I)  # matches pipeline.py's "step N - ..." prints

NAV = [
    ("research", "Research", ":material/search:"),
    ("history", "History", ":material/history:"),
    ("architecture", "Architecture", ":material/hub:"),
]
EXAMPLES = [
    "Solid-state batteries",
    "Agentic AI in healthcare",
    "Quantum computing in 2026",
    "India's EV market",
]

# ---- Lucide icon paths (24x24, stroke based) ----
ICONS = {
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "book-open": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "pen-line": '<path d="M12 20h9"/><path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z"/>',
    "shield-check": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "sparkles": '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "file-text": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "inbox": '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "chevron": '<path d="m9 18 6-6-6-6"/>',
}


def icon(name: str, size: int = 16) -> str:
    return (
        f'<svg class="ico" xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>'
    )


# ============================================================================
# SESSION STATE
# ============================================================================
for key, default in {
    "page": "research",
    "result": None,
    "history": [],
    "pending": None,     # topic queued by the form callback
    "notice": None,      # inline warning text
    "error": None,       # inline error text
    "topic_input": "",
}.items():
    st.session_state.setdefault(key, default)


# ============================================================================
# CALLBACKS
# ============================================================================
def go_page(name: str):
    st.session_state.page = name


def start_run():
    topic = st.session_state.topic_input.strip()
    st.session_state.error = None
    if not topic:
        st.session_state.notice = "Enter a topic first, then press Enter or Run."
        return
    st.session_state.notice = None
    st.session_state.pending = topic


def set_example(text: str):
    st.session_state.topic_input = text


def open_run(idx: int):
    st.session_state.result = st.session_state.history[idx]
    st.session_state.topic_input = st.session_state.history[idx]["topic"]
    st.session_state.page = "research"


def clear_all():
    st.session_state.result = None
    st.session_state.history = []
    st.session_state.topic_input = ""
    st.session_state.error = None
    st.session_state.notice = None


# ============================================================================
# HTML COMPONENT HELPERS
# ============================================================================
def to_text(value) -> str:
    return value.content if hasattr(value, "content") else str(value)


def pipeline_html(statuses, times) -> str:
    labels = {"pending": "Queued", "active": "Running", "done": "Complete", "error": "Failed"}
    cards = []
    for i, (title, ico, desc) in enumerate(STEPS):
        s = statuses[i]
        shown_icon = icon("check", 17) if s == "done" else icon("x", 17) if s == "error" else icon(ico, 17)
        meta = {
            "pending": f"Stage {i + 1} of 4",
            "active": "Working...",
            "done": f"{times[i]:.1f}s" if times[i] is not None else "Done",
            "error": "Stopped",
        }[s]
        cards.append(
            f'<div class="pstep {s}"><div class="pstep-top"><div class="pstep-ico">{shown_icon}</div>'
            f'<div class="pstep-chip">{labels[s]}</div></div>'
            f'<div class="pstep-title">{title}</div><div class="pstep-desc">{desc}</div>'
            f'<div class="pstep-meta">{meta}</div></div>'
        )
    return '<div class="pipe">' + "".join(cards) + "</div>"


def terminal_html(lines, running=False, title="agent.log") -> str:
    body = []
    for ln in lines:
        cls = "tl step" if STEP_RE.match(ln) else "tl"
        body.append(f'<div class="{cls}">{html.escape(ln)}</div>')
    if running:
        body.append('<span class="cursor"></span>')
    if not body:
        body.append('<div class="tl">No output captured.</div>')
    return (
        '<div class="term"><div class="term-bar"><i></i><i></i><i></i>'
        f"<span>{title}</span></div>"
        f'<div class="term-body">{"".join(body)}</div></div>'
    )


def stat_card(ico: str, label: str, value: str, sub: str) -> str:
    return (
        f'<div class="stat"><div class="stat-top">{icon(ico, 15)}{label}</div>'
        f'<div class="stat-value">{value}</div><div class="stat-sub">{sub}</div></div>'
    )


def section_header(eyebrow: str, title: str, desc: str = ""):
    desc_html = f'<div class="sec-desc">{desc}</div>' if desc else ""
    st.markdown(
        f'<div class="sec-eyebrow">{eyebrow}</div><div class="sec-title">{html.escape(title)}</div>{desc_html}',
        unsafe_allow_html=True,
    )


def empty_state(ico: str, title: str, desc: str):
    st.markdown(
        f'<div class="empty"><div class="empty-ico">{icon(ico, 22)}</div>'
        f'<div class="empty-title">{title}</div><div class="empty-desc">{desc}</div></div>',
        unsafe_allow_html=True,
    )


def alert(kind: str, title: str, desc: str):
    ico = "alert"
    st.markdown(
        f'<div class="alert {kind}"><div class="alert-ico">{icon(ico, 20)}</div>'
        f'<div><div class="alert-title">{html.escape(title)}</div>'
        f'<div class="alert-desc">{html.escape(desc)}</div></div></div>',
        unsafe_allow_html=True,
    )


def score_html(score: float) -> str:
    color = "#4ade80" if score >= 8 else "#fbbf24" if score >= 6 else "#f87171"
    verdict = "Excellent" if score >= 8 else "Good, needs polish" if score >= 6 else "Needs work"
    return (
        f'<div class="score"><div class="score-ring" style="background:conic-gradient({color} {score * 10}%,rgba(255,255,255,0.08) 0)">'
        f'<div class="score-in">{score:g}</div></div>'
        f'<div><div class="score-t">{verdict}</div><div class="score-s">Critic score out of 10</div></div></div>'
    )


COPY_HTML = """
<style>
  body{margin:0;font-family:Inter,system-ui,sans-serif;background:transparent}
  button{display:inline-flex;align-items:center;gap:8px;height:40px;padding:0 16px;border-radius:10px;cursor:pointer;
    background:#12151a;color:#ececef;border:1px solid rgba(255,255,255,.14);font-size:14px;font-weight:500;transition:all .15s ease;width:100%;justify-content:center}
  button:hover{border-color:rgba(124,131,255,.55);background:rgba(124,131,255,.1);color:#fff}
</style>
<button id="b"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg><span id="l">Copy report</span></button>
<script>
  const text = __PAYLOAD__;
  const l = document.getElementById('l');
  document.getElementById('b').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(text); }
    catch (e) { const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); }
    l.textContent = 'Copied!'; setTimeout(() => l.textContent = 'Copy report', 1600);
  });
</script>
"""


def copy_button(text: str):
    payload = json.dumps(text).replace("</", "<\\/")
    components.html(COPY_HTML.replace("__PAYLOAD__", payload), height=44)


def show_chart(fig):
    cfg = {"displayModeBar": False}
    try:
        st.plotly_chart(fig, width="stretch", config=cfg)
    except Exception:
        st.plotly_chart(fig, use_container_width=True, config=cfg)


# ============================================================================
# CHARTS (real run data)
# ============================================================================
def base_layout(fig, height=290):
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=24, t=8, b=0),
        font=dict(family="Geist, Inter, sans-serif", color="#8a8f98", size=12),
        showlegend=False,
    )
    return fig


def timing_chart(times):
    names = [s[0] for s in STEPS]
    vals = [t or 0 for t in times]
    fig = go.Figure(
        go.Bar(
            x=vals, y=names, orientation="h",
            marker=dict(color=["#6366f1", "#7c83ff", "#8b5cf6", "#a78bfa"], cornerradius=6),
            text=[f"{v:.1f}s" for v in vals], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: %{x:.1f}s<extra></extra>",
        )
    )
    base_layout(fig)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color="#c9ccd3"))
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=False, ticksuffix="s")
    return fig


def volume_chart(state):
    labels = ["Search results", "Scraped content", "Report", "Critic review"]
    keys = ["search_results", "scraped_content", "report", "feedback"]
    vals = [len(to_text(state[k])) for k in keys]
    fig = go.Figure(
        go.Pie(
            labels=labels, values=vals, hole=0.66, sort=False,
            marker=dict(colors=["#6366f1", "#8b5cf6", "#a78bfa", "#f0abfc"], line=dict(color="#08090c", width=3)),
            textinfo="percent", textfont=dict(color="#fff"),
            hovertemplate="%{label}: %{value:,} chars<extra></extra>",
        )
    )
    base_layout(fig)
    fig.update_layout(showlegend=True, legend=dict(font=dict(color="#c9ccd3")), margin=dict(l=0, r=0, t=8, b=0))
    return fig


# ============================================================================
# BACKEND BRIDGE - runs pipeline.py and mirrors its console output into the UI
# ============================================================================
class StreamCapture(io.TextIOBase):
    """File-like object that forwards each printed line to a callback."""

    def __init__(self, on_line):
        self.on_line = on_line
        self.buf = ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.on_line(line)
        return len(s)

    def flush(self):
        if self.buf:
            self.on_line(self.buf)
            self.buf = ""


def execute_pipeline(topic: str, tracker, terminal) -> dict:
    statuses, times, starts, log = ["pending"] * 4, [None] * 4, [None] * 4, []
    last_paint = [0.0]

    def paint_tracker():
        try:
            tracker.markdown(pipeline_html(statuses, times), unsafe_allow_html=True)
        except Exception:
            pass

    def paint_terminal(force=False):
        now = time.time()
        if force or now - last_paint[0] > 0.2:
            last_paint[0] = now
            try:
                terminal.markdown(terminal_html(log[-14:], running=True, title="live agent log"), unsafe_allow_html=True)
            except Exception:
                pass

    def on_line(line):
        text = line.strip()
        if not text or set(text) <= {"=", " "}:
            return
        m = STEP_RE.match(text)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < 4:
                now = time.time()
                for j in range(idx):
                    if statuses[j] == "active":
                        statuses[j], times[j] = "done", now - starts[j]
                statuses[idx], starts[idx] = "active", now
                paint_tracker()
        log.append(text[:200])
        paint_terminal(force=bool(m))

    paint_tracker()
    capture = StreamCapture(on_line)
    t_start = time.time()
    try:
        with redirect_stdout(capture):
            state = run_research_pipeline(topic)   # <-- your existing backend
        capture.flush()
    except Exception:
        for j in range(4):
            if statuses[j] == "active":
                statuses[j] = "error"
        paint_tracker()
        raise

    now = time.time()
    for j in range(4):
        if statuses[j] == "active":
            statuses[j], times[j] = "done", now - starts[j]
    return {
        "topic": topic, "state": state, "step_times": times,
        "elapsed": now - t_start, "log": log, "ts": time.time(),
    }


def extract_score(text: str):
    m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", text)
    if m and 0 <= float(m.group(1)) <= 10:
        return float(m.group(1))
    return None


# ============================================================================
# SHELL: SIDEBAR + TOP BAR
# ============================================================================
def render_sidebar():
    with st.sidebar:
        st.markdown(
            f'<div class="brand"><div class="brand-mark">{icon("sparkles", 18)}</div>'
            '<div><div class="brand-name">Nexus Research</div>'
            '<div class="brand-sub">Multi-agent intelligence</div></div></div>'
            '<div class="nav-label">Workspace</div>',
            unsafe_allow_html=True,
        )
        with st.container(key="nav"):
            for name, label, mat_icon in NAV:
                st.button(
                    label, key=f"nav_{name}", icon=mat_icon, on_click=go_page, args=(name,),
                    type="primary" if st.session_state.page == name else "secondary",
                )

        runs = len(st.session_state.history)
        last = st.session_state.result
        st.markdown(
            '<div class="side-card">'
            f'<div class="row"><span>Runs this session</span><b>{runs}</b></div>'
            f'<div class="row"><span>Last run</span><b>{(str(round(last["elapsed"])) + "s") if last else "-"}</b></div>'
            '<div class="row"><span>Backend</span><b>pipeline.py</b></div></div>',
            unsafe_allow_html=True,
        )
        st.write("")
        st.button("Clear session", key="clear", icon=":material/delete:", on_click=clear_all)


def render_topbar():
    page_label = {"research": "Research", "history": "History", "architecture": "Architecture"}[st.session_state.page]
    st.markdown(
        f'<div class="topbar"><div class="crumbs">Nexus {icon("chevron", 14)} <b>{page_label}</b></div>'
        '<div class="pill"><span class="dot"></span>Agents ready</div></div>',
        unsafe_allow_html=True,
    )


# ============================================================================
# PAGES
# ============================================================================
def render_results(result: dict):
    state = result["state"]
    report = to_text(state["report"])
    feedback = to_text(state["feedback"])
    search = to_text(state["search_results"])
    scraped = to_text(state["scraped_content"])

    words = len(report.split())
    minutes = max(1, round(words / 220))
    sources = len(set(re.findall(r"https?://[^\s\)\]>\"']+", search + scraped)))
    score = extract_score(feedback)

    st.markdown(
        '<div class="stats">'
        + stat_card("clock", "Total time", f"{result['elapsed']:.0f}s", "4 agents, end to end")
        + stat_card("file-text", "Report length", f"{words:,}", f"words, ~{minutes} min read")
        + stat_card("link", "Sources", f"{sources}", "unique URLs referenced")
        + stat_card("gauge", "Critic score", f"{score:g}/10" if score is not None else "n/a", "automated review")
        + "</div>",
        unsafe_allow_html=True,
    )

    section_header("Results", result["topic"], "Generated by the full multi-agent pipeline.")

    t_report, t_review, t_insights, t_sources, t_log = st.tabs(
        ["Report", "Critic review", "Insights", "Sources", "Run log"]
    )

    with t_report:
        with st.container(border=True):
            st.markdown(report)
        c1, c2, c3, _ = st.columns([1, 1, 1, 2])
        with c1:
            copy_button(report)
        with c2:
            st.download_button("Markdown", report, "research_report.md", "text/markdown",
                               icon=":material/download:", key="dl_md")
        with c3:
            st.download_button("Plain text", report, "research_report.txt", "text/plain",
                               icon=":material/description:", key="dl_txt")

    with t_review:
        with st.container(border=True):
            if score is not None:
                st.markdown(score_html(score), unsafe_allow_html=True)
            st.markdown(feedback)
        c1, _ = st.columns([1, 3])
        with c1:
            st.download_button("Download review", feedback, "critic_review.md", "text/markdown",
                               icon=":material/download:", key="dl_review")

    with t_insights:
        left, right = st.columns(2)
        with left:
            st.markdown("**Time per agent**")
            show_chart(timing_chart(result["step_times"]))
        with right:
            st.markdown("**Output volume by stage**")
            show_chart(volume_chart(state))

    with t_sources:
        with st.container(border=True):
            st.markdown("#### Search results")
            st.markdown(search)
        with st.expander("Scraped page content"):
            st.markdown(scraped)

    with t_log:
        st.markdown(terminal_html(result["log"][-150:], title="agent.log"), unsafe_allow_html=True)


def page_research():
    result = st.session_state.result
    running = st.session_state.pending is not None

    if result is None and not running:
        st.markdown(
            f'<div class="hero"><span class="hero-badge">{icon("sparkles", 14)} Four specialised agents, one question</span>'
            '<div class="hero-title">Research anything.<br><span class="grad">Reviewed before you read it.</span></div>'
            '<div class="hero-sub">Nexus searches the web, reads the best source, writes a structured report '
            "and has an AI critic review it, all in one run.</div></div>",
            unsafe_allow_html=True,
        )

    # ---- command bar ----
    with st.container(key="cmd"):
        with st.form("research_form", border=True, clear_on_submit=False):
            c_in, c_btn = st.columns([6, 1.5], vertical_alignment="center")
            with c_in:
                st.text_input("Topic", key="topic_input", placeholder="What do you want to research?",
                              label_visibility="collapsed", disabled=running)
            with c_btn:
                st.form_submit_button("Run research", icon=":material/arrow_forward:",
                                      on_click=start_run, disabled=running)

    if st.session_state.notice:
        alert("warn", "Missing topic", st.session_state.notice)

    if result is None and not running:
        st.markdown('<div class="chips-label">Try an example</div>', unsafe_allow_html=True)
        with st.container(key="chips"):
            cols = st.columns(len(EXAMPLES))
            for col, ex in zip(cols, EXAMPLES):
                with col:
                    st.button(ex, key=f"ex_{ex}", on_click=set_example, args=(ex,))

    tracker = st.empty()
    terminal = st.empty()

    # ---- run pipeline ----
    if running:
        topic = st.session_state.pending
        try:
            res = execute_pipeline(topic, tracker, terminal)
            st.session_state.result = res
            st.session_state.history.append(res)
            st.session_state.error = None
        except Exception as e:
            st.session_state.error = str(e) or e.__class__.__name__
            st.session_state.result = None
        finally:
            st.session_state.pending = None
        st.rerun()

    # ---- error state ----
    if st.session_state.error:
        alert("err", "The pipeline hit an error", st.session_state.error)
        st.caption("Check your API keys in .env and your network connection, then try again.")
        return

    # ---- idle / results ----
    if result is None:
        tracker.markdown(pipeline_html(["pending"] * 4, [None] * 4), unsafe_allow_html=True)
        return

    tracker.markdown(pipeline_html(["done"] * 4, result["step_times"]), unsafe_allow_html=True)
    render_results(result)


def page_history():
    section_header("History", "Past research", "Runs from this session. Open one to view it again.")
    history = st.session_state.history
    if not history:
        empty_state("inbox", "No research yet",
                    "Completed runs will appear here so you can reopen reports without re-running the agents.")
        return
    for idx in range(len(history) - 1, -1, -1):
        item = history[idx]
        words = len(to_text(item["state"]["report"]).split())
        score = extract_score(to_text(item["state"]["feedback"]))
        meta = f'{time.strftime("%H:%M", time.localtime(item["ts"]))}  |  {item["elapsed"]:.0f}s  |  {words:,} words'
        if score is not None:
            meta += f"  |  {score:g}/10"
        with st.container(border=True):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            with c1:
                st.markdown(
                    f'<div class="run-title">{html.escape(item["topic"])}</div><div class="run-meta">{meta}</div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.button("Open", key=f"open_{idx}", on_click=open_run, args=(idx,),
                          icon=":material/open_in_new:")


def page_architecture():
    section_header("Architecture", "How the system works",
                   "A sequential multi-agent pipeline. Each stage hands its output to the next.")
    descs = [
        "A tool-using agent queries the web and returns recent, relevant sources for the topic.",
        "A second agent picks the strongest URL from the results and scrapes it for full-text depth.",
        "A writing chain combines search results and scraped content into a structured report.",
        "A critic chain reviews the draft for quality, gaps and accuracy, and returns feedback.",
    ]
    cards = ""
    for i, ((title, ico, _), d) in enumerate(zip(STEPS, descs), start=1):
        cards += (
            f'<div class="arch-card"><div class="arch-num">0{i}</div>'
            f'<div class="arch-title">{icon(ico, 18)}{title}</div><div class="arch-desc">{d}</div></div>'
        )
    st.markdown(f'<div class="arch">{cards}</div>', unsafe_allow_html=True)


# ============================================================================
# ROUTER
# ============================================================================
render_sidebar()
render_topbar()
{"research": page_research, "history": page_history, "architecture": page_architecture}[st.session_state.page]()