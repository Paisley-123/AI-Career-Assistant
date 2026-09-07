import html
import json
from textwrap import dedent

import streamlit as st
import streamlit.components.v1 as components
from pypdf import PdfReader

from main import run_case


# ============================================================
# 1. 页面配置
# ============================================================

st.set_page_config(
    page_title="AI简历优化助手",
    page_icon="📄",
    layout="wide",
)

APP_VERSION = "v0.8.1-product-ui"

# V0.8 仅重做前端展示；main.py 的 V0.7 结构化链路保持冻结。
if st.session_state.get("_app_version") != APP_VERSION:
    for key in [
        "resume_facts",
        "jd_requirements",
        "jd_mapping",
        "optimized_result",
        "verified_result",
        "resume_text",
        "last_error",
    ]:
        st.session_state.pop(key, None)

    st.session_state["_app_version"] = APP_VERSION


# ============================================================
# 2. HTML / 文本工具
# ============================================================

def render_html(raw_html):
    """渲染应用内部 HTML，并消除 Markdown 对缩进 HTML 的误判。"""
    cleaned = dedent(str(raw_html)).strip()
    # Streamlit 的 Markdown 解析器会把 4 个空格开头的 HTML 当成代码块。
    # 动态拼接多个区块时统一去掉每行前导缩进，避免简历后半段显示成源码。
    cleaned = "\n".join(line.lstrip() for line in cleaned.splitlines())
    st.markdown(
        cleaned,
        unsafe_allow_html=True,
    )


def esc(value):
    """对模型输出 / 用户输入进行 HTML 转义后再进入 unsafe HTML。"""
    return html.escape(str(value), quote=True)


def render_page_title(title, subtitle=None):
    subtitle_html = (
        f'<div class="page-subtitle">{esc(subtitle)}</div>'
        if subtitle
        else ""
    )
    render_html(
        f"""
        <div class="page-title">{esc(title)}</div>
        {subtitle_html}
        """
    )


def render_section_title(title, small=False):
    css_class = "section-title small" if small else "section-title"
    render_html(
        f'<div class="{css_class}">{esc(title)}</div>'
    )


# ============================================================
# 3. 页面样式
# ============================================================

st.markdown(
    dedent(
        """
        <style>
        :root {
            --primary: #1f4e79;
            --primary-dark: #173d60;
            --primary-light: #4f86c6;
            --background: #f5f8fc;
            --border: #dce6f0;
            --text: #1f2d3d;
            --muted: #6b7b8c;
            --soft-blue: #edf4fb;
            --soft-green: #eef8f3;
            --soft-yellow: #fff8e8;
            --soft-red: #fff1f0;
            --soft-gray: #f7f9fb;
        }

        .stApp {
            background-color: var(--background);
        }

        .block-container {
            max-width: 1220px;
            /* 给 Streamlit 顶栏及桌面悬浮组件留出安全区，避免标题贴顶/被遮挡。 */
            padding-top: 4.0rem !important;
            padding-bottom: 2.5rem;
        }

        @media (max-width: 768px) {
            .block-container {
                padding-top: 3.25rem !important;
            }
        }

        p, li {
            font-size: 0.9rem !important;
            line-height: 1.68 !important;
        }

        .page-title {
            font-size: 2rem;
            line-height: 1.25;
            color: var(--primary);
            font-weight: 750;
            letter-spacing: -0.01em;
            margin-bottom: 0.15rem;
        }

        .page-subtitle {
            color: var(--muted);
            font-size: 0.88rem;
            margin-bottom: 1.0rem;
        }

        .section-title {
            color: var(--primary-dark);
            font-size: 1.22rem;
            line-height: 1.4;
            font-weight: 700;
            margin-top: 0.35rem;
            margin-bottom: 0.55rem;
        }

        .section-title.small {
            font-size: 0.98rem;
            margin-top: 0.2rem;
            margin-bottom: 0.45rem;
        }

        .field-label {
            color: var(--primary-dark);
            font-size: 1rem;
            font-weight: 650;
            margin-bottom: 0.4rem;
        }

        .stCaption {
            font-size: 0.8rem !important;
            color: var(--muted) !important;
        }

        [data-testid="stFileUploaderDropzone"] {
            background: #ffffff !important;
            border: 1px solid var(--border) !important;
            border-radius: 12px !important;
        }

        .stTextArea textarea {
            background: #ffffff !important;
            border: 1px solid var(--border) !important;
            border-radius: 12px !important;
            font-size: 0.9rem !important;
        }

        [data-testid="stFormSubmitButton"] button {
            width: 100%;
            border: none !important;
            border-radius: 9px !important;
            background: linear-gradient(90deg, #1f4e79, #2f6ea3) !important;
            color: white !important;
            font-size: 0.92rem !important;
            font-weight: 650 !important;
            padding: 0.64rem 1rem !important;
            box-shadow: 0 4px 10px rgba(31, 78, 121, 0.12);
        }

        [data-testid="stFormSubmitButton"] button:hover {
            background: linear-gradient(90deg, #193f63, #285f8d) !important;
        }

        .stDownloadButton > button {
            width: 100%;
            background: #ffffff !important;
            color: var(--primary) !important;
            border: 1px solid var(--border) !important;
            border-radius: 9px !important;
            font-size: 0.88rem !important;
            font-weight: 650 !important;
            min-height: 42px;
        }

        button[data-baseweb="tab"] {
            color: var(--muted) !important;
            font-size: 0.9rem !important;
            font-weight: 500 !important;
            padding-left: 0 !important;
            padding-right: 1.1rem !important;
        }

        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--primary) !important;
            font-weight: 650 !important;
        }

        button[data-baseweb="tab"][aria-selected="true"] p,
        button[data-baseweb="tab"][aria-selected="true"] span {
            color: var(--primary) !important;
        }

        [data-baseweb="tab-highlight"] {
            background-color: var(--primary) !important;
        }

        .status-strip {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            padding: 0.31rem 0.62rem;
            margin-top: 0.35rem;
            margin-bottom: 0.45rem;
            background: var(--soft-blue);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--primary);
            font-size: 0.76rem;
            font-weight: 550;
        }

        .status-dot {
            display: inline-block;
            width: 7px;
            height: 7px;
            background: var(--primary-light);
            border-radius: 50%;
        }

        .match-banner {
            padding: 0.62rem 0.82rem;
            background: linear-gradient(90deg, #eaf3fc, #f5f9fd);
            border: 1px solid #d3e2f1;
            border-radius: 10px;
            color: var(--primary);
            font-size: 0.9rem;
            font-weight: 650;
            margin-bottom: 0.4rem;
        }

        .progress-track {
            width: 100%;
            height: 4px;
            background: #e1eaf3;
            border-radius: 999px;
            overflow: hidden;
            margin-bottom: 0.75rem;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #2f6ea3, #4f86c6);
            border-radius: 999px;
        }

        .callout {
            padding: 0.5rem 0.74rem;
            border: 1px solid var(--border);
            border-radius: 9px;
            margin-bottom: 0.55rem;
            font-size: 0.78rem;
            line-height: 1.55;
        }

        .callout.green { background: var(--soft-green); color: #287454; }
        .callout.blue  { background: var(--soft-blue);  color: var(--primary); }
        .callout.gray  { background: var(--soft-gray);  color: var(--muted); }

        .match-card,
        .suggestion-card,
        .resume-card {
            background: #ffffff;
            border: 1px solid var(--border);
            border-radius: 11px;
            padding: 0.78rem 0.88rem;
            margin-bottom: 0.65rem;
        }

        .match-requirement {
            color: var(--primary-dark);
            font-size: 0.93rem;
            font-weight: 680;
            margin-bottom: 0.42rem;
        }

        .status-badge {
            display: inline-block;
            border-radius: 999px;
            padding: 0.16rem 0.48rem;
            font-size: 0.72rem;
            font-weight: 650;
            margin-bottom: 0.45rem;
        }

        .status-ok { background: var(--soft-green); color: #287454; }
        .status-partial { background: var(--soft-yellow); color: #8a6817; }
        .status-missing { background: var(--soft-red); color: #a23d37; }

        .mini-label {
            color: var(--muted);
            font-size: 0.74rem;
            font-weight: 650;
            margin-top: 0.28rem;
            margin-bottom: 0.18rem;
        }

        .match-card ul,
        .resume-card ul {
            margin-top: 0.15rem;
            margin-bottom: 0.4rem;
            padding-left: 1.22rem;
        }

        .match-card li,
        .resume-card li {
            font-size: 0.86rem !important;
            line-height: 1.58 !important;
            margin-bottom: 0.12rem;
        }

        .explanation {
            color: var(--text);
            font-size: 0.84rem;
            line-height: 1.58;
        }

        .suggestion-group {
            color: var(--primary-dark);
            font-size: 0.92rem;
            font-weight: 700;
            margin-top: 0.4rem;
            margin-bottom: 0.45rem;
        }

        .suggestion-text {
            color: var(--text);
            font-size: 0.86rem;
            line-height: 1.58;
            margin-bottom: 0.28rem;
        }

        .suggestion-reason {
            color: var(--muted);
            font-size: 0.8rem;
            line-height: 1.55;
        }

        .rewrite-box {
            background: var(--soft-gray);
            border-radius: 8px;
            padding: 0.5rem 0.62rem;
            margin: 0.35rem 0;
            font-size: 0.83rem;
            line-height: 1.55;
        }

        .rewrite-arrow {
            color: var(--primary);
            font-weight: 700;
            padding: 0 0.25rem;
        }

        .resume-card {
            padding: 0.9rem 1rem;
        }

        .resume-section-title {
            color: var(--primary-dark);
            font-size: 0.93rem;
            font-weight: 720;
            border-bottom: 1px solid #edf1f5;
            padding-bottom: 0.28rem;
            margin-top: 0.45rem;
            margin-bottom: 0.25rem;
        }

        .resume-section-title:first-child {
            margin-top: 0;
        }

        [data-testid="stExpander"] {
            background: #ffffff !important;
            border: 1px solid var(--border) !important;
            border-radius: 10px !important;
        }

        .download-note {
            color: var(--muted);
            font-size: 0.75rem;
            margin-top: 0.35rem;
        }

        .privacy-note {
            color: var(--muted);
            font-size: 0.75rem;
            margin-top: 0.45rem;
        }
        </style>
        """
    ),
    unsafe_allow_html=True,
)


# ============================================================
# 4. 数据 / 业务辅助函数
# ============================================================

def read_pdf(uploaded_file):
    """读取可提取文本的 PDF。扫描件若无文本会返回空字符串。"""
    reader = PdfReader(uploaded_file)
    pages = []

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text and page_text.strip():
            pages.append(page_text.strip())

    return "\n".join(pages).strip()


def count_match_levels(jd_mapping):
    if not isinstance(jd_mapping, dict):
        return 0, 0, 0

    matches = jd_mapping.get("matches", [])
    if not isinstance(matches, list):
        return 0, 0, 0

    satisfied = sum(
        1 for item in matches
        if isinstance(item, dict) and item.get("status") == "已满足"
    )
    partial = sum(
        1 for item in matches
        if isinstance(item, dict) and item.get("status") == "部分相关"
    )
    missing = sum(
        1 for item in matches
        if isinstance(item, dict) and item.get("status") == "当前未体现"
    )

    return satisfied, partial, missing


def get_safe_resume_sections(verified_result):
    if not isinstance(verified_result, dict):
        return []

    safe_resume = verified_result.get("safe_resume", {})
    if not isinstance(safe_resume, dict):
        return []

    sections = safe_resume.get("sections", [])
    return sections if isinstance(sections, list) else []


def safe_resume_to_text(verified_result):
    """生成用于复制 / 下载的纯文本，不含 Markdown、链接或 HTML。"""
    sections = get_safe_resume_sections(verified_result)
    blocks = []

    for section in sections:
        if not isinstance(section, dict):
            continue

        name = str(section.get("name", "")).strip()
        items = section.get("items", [])

        if not name or not isinstance(items, list):
            continue

        clean_items = [
            str(item).strip()
            for item in items
            if str(item).strip()
        ]

        if not clean_items:
            continue

        block = [name]
        block.extend(f"• {item}" for item in clean_items)
        blocks.append("\n".join(block))

    return "\n\n".join(blocks).strip()


def validate_analysis_result(jd_mapping, optimized_result, verified_result):
    """前端做最低限度结构校验，避免把异常结构直接展示给用户。"""
    if not isinstance(jd_mapping, dict) or not isinstance(
        jd_mapping.get("matches", []), list
    ):
        raise ValueError("岗位匹配结构异常")

    if not isinstance(optimized_result, dict):
        raise ValueError("修改建议结构异常")

    suggestions = optimized_result.get("suggestions", {})
    if not isinstance(suggestions, dict):
        raise ValueError("修改建议结构异常")

    if not isinstance(verified_result, dict):
        raise ValueError("优化版简历结构异常")

    sections = get_safe_resume_sections(verified_result)
    if not sections:
        raise ValueError("优化版简历为空")


def friendly_error_message(error):
    message = str(error)
    lowered = message.lower()

    if "402" in message or "insufficient balance" in lowered:
        return "DeepSeek API 余额不足，请充值后重新尝试。"

    if (
        "401" in message
        or "authentication" in lowered
        or "api key" in lowered
    ):
        return "API Key 无效，请检查 .env 中的 DeepSeek API Key。"

    if "岗位匹配" in message and ("json" in lowered or "结构" in message):
        return "岗位匹配结果生成异常，请重新分析一次。"

    if "修改建议" in message and ("json" in lowered or "结构" in message):
        return "修改建议生成异常，请重新分析一次。"

    if (
        "事实审核" in message
        or "safe_resume" in message
        or "优化版简历" in message
    ):
        return "优化版简历生成异常，请重新分析一次。"

    if "rate limit" in lowered or "429" in message:
        return "当前请求较多，请稍等片刻后重新尝试。"

    if "timeout" in lowered or "timed out" in lowered:
        return "模型响应超时，请稍后重新尝试。"

    return "分析暂时失败，请稍后重新尝试。"


# ============================================================
# 5. 用户界面渲染函数
# ============================================================

def render_job_matches(jd_mapping):
    if not isinstance(jd_mapping, dict):
        st.warning("岗位匹配结果暂不可用，请重新分析一次。")
        return

    matches = jd_mapping.get("matches", [])
    if not matches:
        st.info("暂未获得可展示的岗位匹配结果。")
        return

    for item in matches:
        if not isinstance(item, dict):
            continue

        requirement = str(item.get("requirement", "")).strip()
        status = str(item.get("status", "")).strip()
        evidence = item.get("evidence", [])
        explanation = str(item.get("explanation", "")).strip()

        if status == "已满足":
            badge_class = "status-ok"
        elif status == "部分相关":
            badge_class = "status-partial"
        else:
            badge_class = "status-missing"

        if isinstance(evidence, list) and evidence:
            evidence_html = "".join(
                f"<li>{esc(x)}</li>"
                for x in evidence
                if str(x).strip()
            )
        else:
            evidence_html = "<li>暂无直接证据</li>"

        explanation_html = (
            f"""
            <div class="mini-label">说明</div>
            <div class="explanation">{esc(explanation)}</div>
            """
            if explanation
            else ""
        )

        render_html(
            f"""
            <div class="match-card">
                <div class="match-requirement">岗位要求：{esc(requirement)}</div>
                <span class="status-badge {badge_class}">{esc(status)}</span>
                <div class="mini-label">简历中已有证据</div>
                <ul>{evidence_html}</ul>
                {explanation_html}
            </div>
            """
        )


def render_suggestions(optimized_result):
    if not isinstance(optimized_result, dict):
        st.warning("修改建议暂不可用，请重新分析一次。")
        return

    suggestions = optimized_result.get("suggestions", {})
    if not isinstance(suggestions, dict):
        st.warning("修改建议暂不可用，请重新分析一次。")
        return

    ordering = suggestions.get("ordering", [])
    wording = suggestions.get("wording", [])

    if ordering:
        render_html('<div class="suggestion-group">排序调整</div>')

        for item in ordering:
            if not isinstance(item, dict):
                continue

            suggestion = str(item.get("suggestion", "")).strip()
            reason = str(item.get("reason", "")).strip()

            render_html(
                f"""
                <div class="suggestion-card">
                    <div class="suggestion-text"><strong>建议：</strong>{esc(suggestion)}</div>
                    <div class="suggestion-reason"><strong>原因：</strong>{esc(reason)}</div>
                </div>
                """
            )

    if wording:
        render_html('<div class="suggestion-group">表达精简</div>')

        for item in wording:
            if not isinstance(item, dict):
                continue

            original = str(item.get("original", "")).strip()
            optimized = str(item.get("optimized", "")).strip()
            reason = str(item.get("reason", "")).strip()

            render_html(
                f"""
                <div class="suggestion-card">
                    <div class="suggestion-text"><strong>建议：</strong></div>
                    <div class="rewrite-box">
                        {esc(original)}
                        <span class="rewrite-arrow">→</span>
                        {esc(optimized)}
                    </div>
                    <div class="suggestion-reason"><strong>原因：</strong>{esc(reason)}</div>
                </div>
                """
            )

    if not ordering and not wording:
        st.info("当前没有必要的修改建议。")


def render_follow_up(optimized_result):
    if not isinstance(optimized_result, dict):
        return

    follow_up = optimized_result.get("follow_up", {})
    if not isinstance(follow_up, dict):
        return

    jd_related = follow_up.get("jd_related", [])
    general_advice = follow_up.get("general_advice", [])

    if not jd_related and not general_advice:
        return

    with st.expander("未来可继续补充的能力", expanded=False):
        if jd_related:
            render_section_title("当前 JD 相关", small=True)
            items_html = "".join(
                f"<li>{esc(item)}</li>"
                for item in jd_related
                if str(item).strip()
            )
            render_html(f"<ul>{items_html}</ul>")

        if general_advice:
            render_section_title("通用建议", small=True)
            render_html(
                '<div class="callout gray">以下并非当前 JD 明确要求。</div>'
            )
            items_html = "".join(
                f"<li>{esc(item)}</li>"
                for item in general_advice
                if str(item).strip()
            )
            render_html(f"<ul>{items_html}</ul>")


def render_safe_resume(verified_result):
    """直接从结构化 safe_resume 渲染，不再依赖 Markdown 字符串。"""
    sections = get_safe_resume_sections(verified_result)

    if not sections:
        st.warning("暂未获得可展示的优化版简历。")
        return

    blocks = []

    for section in sections:
        if not isinstance(section, dict):
            continue

        name = str(section.get("name", "")).strip()
        items = section.get("items", [])

        if not name or not isinstance(items, list):
            continue

        clean_items = [
            str(item).strip()
            for item in items
            if str(item).strip()
        ]

        if not clean_items:
            continue

        items_html = "".join(
            f"<li>{esc(item)}</li>"
            for item in clean_items
        )

        # 使用紧凑 HTML，杜绝换行缩进被 Markdown 识别成代码块。
        blocks.append(
            '<div class="resume-section">'
            f'<div class="resume-section-title">{esc(name)}</div>'
            f'<ul>{items_html}</ul>'
            '</div>'
        )

    if not blocks:
        st.warning("暂未获得可展示的优化版简历。")
        return

    resume_html = '<div class="resume-card">' + "".join(blocks) + '</div>'
    render_html(resume_html)


def render_copy_button(text):
    """独立的纯文本复制按钮；失败时给出提示，不影响下载功能。"""
    js_text = json.dumps(text, ensure_ascii=False).replace("</", "<\\/")

    copy_component = f"""
    <!doctype html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: transparent;
        }}
        .row {{ display: flex; align-items: center; gap: 10px; }}
        button {{
            width: 100%;
            height: 42px;
            border: 1px solid #dce6f0;
            border-radius: 9px;
            background: #ffffff;
            color: #1f4e79;
            font-size: 14px;
            font-weight: 650;
            cursor: pointer;
        }}
        button:hover {{ background: #f4f8fc; }}
        #status {{
            display: none;
            font-size: 12px;
            color: #287454;
            white-space: nowrap;
        }}
    </style>
    </head>
    <body>
        <div class="row">
            <button id="copyBtn">复制纯文本简历</button>
            <span id="status">已复制</span>
        </div>
        <script>
            const resumeText = {js_text};
            const btn = document.getElementById('copyBtn');
            const status = document.getElementById('status');

            async function copyText() {{
                try {{
                    if (navigator.clipboard && window.isSecureContext) {{
                        await navigator.clipboard.writeText(resumeText);
                    }} else {{
                        const area = document.createElement('textarea');
                        area.value = resumeText;
                        area.style.position = 'fixed';
                        area.style.opacity = '0';
                        document.body.appendChild(area);
                        area.focus();
                        area.select();
                        const ok = document.execCommand('copy');
                        document.body.removeChild(area);
                        if (!ok) throw new Error('copy failed');
                    }}
                    status.textContent = '已复制';
                    status.style.color = '#287454';
                    status.style.display = 'inline';
                }} catch (err) {{
                    status.textContent = '复制失败，可使用下载';
                    status.style.color = '#a23d37';
                    status.style.display = 'inline';
                }}
            }}

            btn.addEventListener('click', copyText);
        </script>
    </body>
    </html>
    """

    components.html(
        copy_component,
        height=48,
        scrolling=False,
    )


def render_developer_details():
    """开发调试信息默认隐藏，不占用普通用户的主流程。"""
    with st.expander("开发者详情（调试信息）", expanded=False):
        st.caption("以下内容仅用于检查结构化链路，普通使用无需查看。")

        debug_tabs = st.tabs(
            [
                "事实提取",
                "JD 提取",
                "岗位匹配 JSON",
                "优化 JSON",
                "审核 JSON",
            ]
        )

        with debug_tabs[0]:
            st.code(
                str(st.session_state.get("resume_facts", "")),
                language=None,
                wrap_lines=True,
            )

        with debug_tabs[1]:
            st.code(
                str(st.session_state.get("jd_requirements", "")),
                language=None,
                wrap_lines=True,
            )

        with debug_tabs[2]:
            st.json(st.session_state.get("jd_mapping", {}))

        with debug_tabs[3]:
            st.json(st.session_state.get("optimized_result", {}))

        with debug_tabs[4]:
            st.json(st.session_state.get("verified_result", {}))


# ============================================================
# 6. 页面顶部
# ============================================================

render_page_title(
    "AI Career Assistant",
    "上传简历并输入目标 JD，获得基于真实经历的岗位匹配与优化简历优化建议。",
)


# ============================================================
# 7. 输入表单
# ============================================================

with st.form("resume_analysis_form"):
    left_col, right_col = st.columns(2)

    with left_col:
        render_html('<div class="field-label">① 上传简历</div>')

        uploaded_resume = st.file_uploader(
            "上传 PDF 格式简历",
            type=["pdf"],
            key="resume_uploader",
            help="当前支持可复制文字的 PDF；扫描版 PDF 暂不支持 OCR。",
        )

        render_html(
            '<div class="privacy-note">当前版本仅支持可提取文本的 PDF；扫描件可能无法识别。</div>'
        )

    with right_col:
        render_html('<div class="field-label">② 输入目标岗位 JD</div>')

        jd_text = st.text_area(
            "粘贴或输入岗位描述",
            height=250,
            key="jd_input",
            placeholder="""例如：

岗位：AI产品经理实习生

岗位要求：
1. 了解LLM、RAG等AI技术
2. 具备Python基础
3. 具备产品思维
4. 有AI项目实践经验优先
""",
        )

    analyze_button = st.form_submit_button(
        "开始分析",
        use_container_width=True,
    )


# ============================================================
# 8. 读取 PDF
# ============================================================

resume_text = None

if uploaded_resume is not None:
    try:
        resume_text = read_pdf(uploaded_resume)

        if resume_text:
            st.session_state["resume_text"] = resume_text
        else:
            st.session_state.pop("resume_text", None)

        with st.expander("检查简历文本提取结果", expanded=False):
            if resume_text:
                st.text(resume_text)
            else:
                st.warning(
                    "没有从该 PDF 中提取到文字。它可能是扫描版 / 图片版 PDF，"
                    "当前版本暂不支持 OCR。"
                )

    except Exception as error:
        st.session_state.pop("resume_text", None)
        st.error("PDF 读取失败，请确认文件未损坏、未加密，并重新上传。")
        st.session_state["last_error"] = str(error)


# ============================================================
# 9. 执行分析
# ============================================================

if analyze_button:
    if uploaded_resume is None:
        st.warning("请先上传 PDF 简历。")
        st.stop()

    if not resume_text:
        st.warning(
            "当前 PDF 没有可读取的文本。请上传可复制文字的 PDF 简历；"
            "扫描版 PDF 暂不支持。"
        )
        st.stop()

    if not jd_text.strip():
        st.warning("请输入目标岗位 JD。")
        st.stop()

    with st.spinner("正在分析简历与目标岗位，请稍候..."):
        try:
            (
                resume_facts,
                jd_requirements,
                jd_mapping,
                optimized_result,
                verified_result,
            ) = run_case(
                resume_text,
                jd_text,
            )

            validate_analysis_result(
                jd_mapping,
                optimized_result,
                verified_result,
            )

        except Exception as error:
            st.session_state["last_error"] = str(error)
            st.error(friendly_error_message(error))
            st.caption("未保存本次异常结果，可直接重新点击“开始分析”。")
            st.stop()

    st.session_state["resume_facts"] = resume_facts
    st.session_state["jd_requirements"] = jd_requirements
    st.session_state["jd_mapping"] = jd_mapping
    st.session_state["optimized_result"] = optimized_result
    st.session_state["verified_result"] = verified_result
    st.session_state["resume_text"] = resume_text
    st.session_state.pop("last_error", None)


# ============================================================
# 10. 展示结果
# ============================================================

if "verified_result" in st.session_state:
    render_html(
        """
        <div class="status-strip">
            <span class="status-dot"></span>
            <span>分析完成 · 结果已完成事实核验</span>
        </div>
        """
    )

    jd_mapping = st.session_state["jd_mapping"]
    optimized_result = st.session_state["optimized_result"]
    verified_result = st.session_state["verified_result"]

    safe_resume_text = safe_resume_to_text(verified_result)

    satisfied, partial, missing = count_match_levels(jd_mapping)
    total = satisfied + partial + missing

    match_score = (
        int((satisfied + 0.5 * partial) / total * 100)
        if total > 0
        else 0
    )

    render_section_title("岗位匹配概览")

    if match_score >= 80:
        match_text = "高度匹配"
    elif match_score >= 60:
        match_text = "中度匹配"
    else:
        match_text = "匹配较弱"

    render_html(
        f"""
        <div class="match-banner">
            岗位匹配度：{match_score}% · {esc(match_text)}
        </div>
        <div class="progress-track">
            <div class="progress-fill" style="width:{match_score}%"></div>
        </div>
        """
    )

    tab1, tab2, tab3 = st.tabs(
        [
            "岗位匹配",
            "修改建议",
            "优化版简历",
        ]
    )

    # --------------------------------------------------------
    # Tab 1：岗位匹配
    # --------------------------------------------------------
    with tab1:
        render_section_title("你的经历与岗位要求")

        if total > 0:
            if missing == 0 and partial == 0:
                render_html(
                    '<div class="callout green">当前简历中的事实能够覆盖这份 JD 的主要要求。</div>'
                )
            elif missing == 0:
                render_html(
                    '<div class="callout blue">大部分岗位要求已有事实支撑，部分能力仍可进一步补充。</div>'
                )
            else:
                render_html(
                    f'<div class="callout blue">当前仍有 {missing} 项岗位要求未在简历中充分体现。</div>'
                )

        render_job_matches(jd_mapping)

    # --------------------------------------------------------
    # Tab 2：修改建议
    # --------------------------------------------------------
    with tab2:
        render_section_title("针对这份 JD 的修改建议")
        render_suggestions(optimized_result)
        render_follow_up(optimized_result)

    # --------------------------------------------------------
    # Tab 3：优化版简历
    # --------------------------------------------------------
    with tab3:
        render_section_title("优化版简历")

        render_html(
            '<div class="callout green">以下表述经过事实核验，优先避免虚构经历和过度包装。</div>'
        )

        render_safe_resume(verified_result)

        copy_col, download_col = st.columns(2)

        with copy_col:
            render_copy_button(safe_resume_text)

        with download_col:
            st.download_button(
                label="下载纯文本简历",
                data=safe_resume_text,
                file_name="optimized_resume.txt",
                mime="text/plain;charset=utf-8",
                use_container_width=True,
            )

        render_html(
            '<div class="download-note">复制和下载内容均为纯文本，不包含 Markdown、mailto 链接或页面锚点。</div>'
        )
        render_html(
            '<div class="download-note">提交前仍建议结合本人真实经历做最后确认。</div>'
        )

        with st.expander("查看可复制纯文本（备用）", expanded=False):
            st.caption("若浏览器阻止剪贴板权限，可点击下方文本框右上角复制按钮。")
            st.code(
                safe_resume_text,
                language=None,
                wrap_lines=True,
            )

    # --------------------------------------------------------
    # 开发者详情：默认隐藏，不再作为主 Tab
    # --------------------------------------------------------
    render_html('<div style="height:10px"></div>')
    render_developer_details()

    if st.session_state.get("last_error"):
        with st.expander("最近一次错误的技术详情", expanded=False):
            st.code(
                st.session_state["last_error"],
                language=None,
                wrap_lines=True,
            )
