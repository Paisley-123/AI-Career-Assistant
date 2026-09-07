from dotenv import load_dotenv
import json
import os
import re

import chromadb
from openai import OpenAI
from sentence_transformers import SentenceTransformer


# ============================================================
# 1. DeepSeek API
# ============================================================

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    raise ValueError("未读取到 DEEPSEEK_API_KEY，请检查 .env 文件")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)


# ============================================================
# 2. 基础工具
# ============================================================


def read_txt(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def split_text(text, chunk_size=100, overlap=20):
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])

        if end == len(text):
            break

        start = end - overlap

    return chunks


def clean_model_output(text):
    """清理无意义符号与过量空行，但保留 Markdown 层级。"""
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 删除单独成行的 Markdown 分隔线。
    text = re.sub(r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$\n?", "", text)

    # 去除行尾空格。
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    # 连续 3 个及以上换行压缩为 2 个，保留正常段落层级。
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ============================================================
# 3. RAG 简历优化知识库
# ============================================================

guide_text = read_txt("data/examples/resume_guide.txt")
guide_chunks = split_text(
    guide_text,
    chunk_size=100,
    overlap=20,
)

model = SentenceTransformer(
    "BAAI/bge-small-zh-v1.5"
)

guide_embeddings = model.encode(
    guide_chunks
)

chroma_client = chromadb.Client()

collection = chroma_client.get_or_create_collection(
    name="career_knowledge"
)

collection.upsert(
    ids=[f"guide_{i}" for i in range(len(guide_chunks))],
    documents=guide_chunks,
    embeddings=guide_embeddings.tolist(),
)


def retrieve_knowledge(jd_text):
    query = f"""
如何在完全保持候选人事实边界的前提下，根据以下岗位JD调整简历的信息顺序、表达重点和措辞？

【目标岗位JD】
{jd_text}
"""

    query_embedding = model.encode([query])

    results = collection.query(
        query_embeddings=query_embedding.tolist(),
        n_results=min(3, len(guide_chunks)),
    )

    return "\n\n".join(
        results["documents"][0]
    )


# ============================================================
# 4. 第一次调用：提取候选人事实
# ============================================================


def extract_facts(resume_text):
    fact_prompt = f"""
你是一名极其严格的简历信息抽取助手。

请只根据候选人简历，提取原文明确存在的求职事实。

【候选人简历】
{resume_text}

优先按原简历已有栏目输出，例如：
教育背景：
- ...
技能：
- ...
项目经历：
- ...
校园经历：
- ...
自我评价：
- ...
联系方式：
- ...

如果原简历没有某个栏目，不要自行创建；如果有其他明确栏目，可以保留原栏目名称。

严格要求：
1. 只允许提取原文明确出现的信息，不得推测、补充、润色或扩展。
2. 必须完整保留会影响事实强度、程度、责任范围或完成程度的限定词，如“基础、初步、简单、部分、参与、协助、熟悉、了解、学习、实现过、完成过、搭建过”等。
3. 不得自行添加“独立完成、自主搭建、负责、主导、设计、提升、掌握、熟练、深入、完整、全链路”等原文没有的信息。
4. 不得推测项目名称、项目背景、项目目的、用户、数据来源、技术框架、技术细节、项目成果、业务价值。
5. 不得增加原文不存在的量化指标。
6. 不得把原文中未明确属于同一项目、同一经历或同一时间段的信息自行合并。
7. 不得跨字段组合事实。例如技能栏有“RAG”，项目栏有“文档切分、Embedding、向量检索、大模型生成”，不能生成“RAG（文档切分、Embedding、向量检索、大模型生成）”。
8. 不得把技能清单中的某项技能自动认定为某个项目中使用的技术。例如“Python”和“实现基础RAG流程”不能推断为“使用Python实现RAG流程”。
9. 不得根据常识建立原文没有明确写出的技术关系、项目关系或因果关系。
10. 手机、邮箱等联系方式保持原始纯文本，不要转换成Markdown链接。
11. 输出保持简洁，使用普通栏目标题和“-”列表，不使用分隔线、表格、emoji或多余空行。
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "user",
                "content": fact_prompt,
            }
        ],
        temperature=0,
    )

    return clean_model_output(
        response.choices[0].message.content
    )


# ============================================================
# 5. 第二次调用：提取 JD 明确要求
# ============================================================


def extract_jd_requirements(jd_text):
    prompt = f"""
你是一名严格的岗位JD信息抽取助手。

请只提取以下JD中明确写出的岗位要求。

【目标岗位JD】
{jd_text}

输出格式：
岗位名称：
- ...
核心要求：
- ...
加分项：
- ...

严格要求：
1. 只能使用JD原文明确出现的信息。
2. 不得根据岗位名称自行补充行业常见要求。
3. 不得自行补充JD没有写出的PRD、用户调研、原型设计、数据分析、A/B测试、用户增长、竞品分析等能力。
4. 可以合并明显重复的要求，但不得增加含义。
5. 不得自行判断岗位要求之间的优先级。
6. 必须保留原JD中的程度词，如“了解、熟悉、掌握、优先、基础”。
7. 如果没有明确加分项，写“未提供”。
8. 输出保持简洁，不使用分隔线、表格、emoji或多余空行。
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0,
    )

    return clean_model_output(
        response.choices[0].message.content
    )


# ============================================================
# 6. 第三次调用：事实-JD 映射
# ============================================================



def parse_json_object(raw_text, label="模型输出"):
    """将模型输出解析为 JSON 对象，并兼容偶发的 Markdown 代码块。"""
    if not raw_text:
        raise ValueError(f"{label}为空")

    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        first = text.find("{")
        last = text.rfind("}")

        if first == -1 or last == -1 or last <= first:
            raise ValueError(f"{label}不是合法JSON：{text[:500]}")

        candidate = text[first:last + 1]

        try:
            result = json.loads(candidate)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"{label}JSON解析失败：{e}\\n"
                f"模型原始输出：{text[:500]}"
            ) from e

    if not isinstance(result, dict):
        raise ValueError(f"{label}必须是JSON对象")

    return result


def map_facts_to_jd(
    resume_facts,
    jd_requirements,
):
    prompt = f"""
你是一名严格的岗位匹配分析助手。

这个模块只解决一个问题：
逐项判断JD要求在当前简历中是否存在直接、明确的事实支撑。

【候选人已确认事实】
{resume_facts}

【JD明确要求】
{jd_requirements}

匹配状态只能是以下三种：

已满足：
当前简历中的明确事实可以直接支撑该JD要求。

部分相关：
当前简历存在明确相关事实，但只能支撑其中一部分，
或事实强度不足以证明完整满足。

当前未体现：
当前简历中没有足够直接证据。

严格遵守以下事实边界：

1. 只分析JD明确写出的要求，不补充行业常见要求。
2. 每项JD最多选择2条最直接、最有价值的证据。
3. 有直接证据时，不得加入弱相关课程或背景来堆砌证据。
4. 必须保留事实中的程度限定。“基础RAG流程”只能按“基础RAG流程”理解。
5. 不得跨项目、跨经历或跨字段组合事实。
6. 不得根据技术常识补充不存在的技术关系、项目关系或实现关系。
7. 技能栏与项目经历不能自动融合成新的事实。
8. 对“Python基础”：
   - 优先使用技能栏明确列出的Python；
   - 可使用原文明确写明“使用Python……”的实践；
   - 两类证据都存在时，优先各引用1条；
   - 不得把RAG、Streamlit等经历自动当作Python证据。
9. 对“LLM、RAG等AI技术”：
   - 优先使用技能栏中的直接技术词；
   - 优先使用原文明确写出的LLM/RAG实践；
   - 机器学习、深度学习、自然语言处理等邻近课程不能单独用于证明“了解LLM、RAG”。
10. 对“AI产品分析能力”，优先使用原文明确的竞品分析、产品分析等事实，不扩展为系统方法论、行业洞察等未出现能力。
11. 对“AI项目实践经验”，可以引用明确的AI相关实践，但不得自行描述为“多个项目”“完整项目”。
12. 不得把并列技能改写成包含、从属或组合关系，例如不能把“LLM应用开发”和“RAG”写成“LLM应用开发（含RAG）”。
13. JD条目出现顺序不等于优先级。除非JD明确写出优先级，否则不得自行判断。
14. 原文未明确时，不得新增“各、多个、多项、多款、若干、全部、全面、独立、主导、负责、深入、熟练、精通、完整、全链路、显著、大幅、高效”等扩大事实的词。
15. explanation只解释为什么这些事实能够、部分能够或不能支撑当前JD要求，控制在1句话。
16. 不评价候选人的能力深度，不预测招聘者行为。

你必须只返回合法JSON。
禁止返回Markdown、代码块、标题、解释性前后缀或JSON之外的任何内容。

严格使用以下结构：

{{
  "matches": [
    {{
      "requirement": "JD原文要求",
      "status": "已满足",
      "evidence": [
        "直接证据1",
        "直接证据2"
      ],
      "explanation": "一句话说明"
    }}
  ]
}}

如果没有直接证据，evidence必须是空数组 []。

status只能是：
- 已满足
- 部分相关
- 当前未体现
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0,
    )

    result = parse_json_object(
        response.choices[0].message.content,
        label="岗位匹配结果",
    )

    matches = result.get("matches")
    if not isinstance(matches, list):
        raise ValueError("岗位匹配结果缺少 matches 数组")

    valid_status = {
        "已满足",
        "部分相关",
        "当前未体现",
    }

    cleaned_matches = []

    for index, item in enumerate(matches, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第{index}条岗位匹配结果不是JSON对象")

        requirement = str(item.get("requirement", "")).strip()
        status = str(item.get("status", "")).strip()
        evidence = item.get("evidence", [])
        explanation = str(item.get("explanation", "")).strip()

        if not requirement:
            raise ValueError(f"第{index}条岗位匹配结果缺少 requirement")

        if status not in valid_status:
            raise ValueError(f"第{index}条岗位匹配出现非法状态：{status}")

        if not isinstance(evidence, list):
            raise ValueError(f"第{index}条岗位匹配的 evidence 必须是数组")

        cleaned_evidence = []
        for evidence_item in evidence:
            evidence_text = str(evidence_item).strip()
            if evidence_text and evidence_text not in cleaned_evidence:
                cleaned_evidence.append(evidence_text)

        cleaned_evidence = cleaned_evidence[:2]

        if status == "当前未体现":
            cleaned_evidence = []

        cleaned_matches.append(
            {
                "requirement": requirement,
                "status": status,
                "evidence": cleaned_evidence,
                "explanation": explanation,
            }
        )

    return {"matches": cleaned_matches}


# ============================================================
# 7. 第四次调用：安全地针对 JD 优化简历
# ============================================================


def optimize_resume(
    resume_facts,
    jd_requirements,
    jd_mapping,
    context,
):
    """
    V0.7 Step 2：优化建议改为结构化 JSON。

    返回结构：
    {
        "suggestions": {
            "ordering": [{"suggestion": "...", "reason": "..."}],
            "wording": [{"original": "...", "optimized": "...", "reason": "..."}]
        },
        "follow_up": {
            "jd_related": ["..."],
            "general_advice": ["..."]
        },
        "resume_draft": "Markdown简历草稿"
    }
    """
    jd_mapping_json = json.dumps(
        jd_mapping,
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
你是一名AI求职顾问。

你的任务是：
在完全不增加事实的情况下，根据当前JD给出简洁、可执行的简历修改建议，并生成供事实审核模块检查的简历草稿。

【候选人已确认事实】
{resume_facts}

【JD明确要求】
{jd_requirements}

【事实-JD映射】
{jd_mapping_json}

【RAG参考资料】
{context}

事实安全是最高优先级。优化价值主要来自：
- 合理排序
- 信息组织
- 删除纯冗余
- 最小必要的完全等义精简

严格遵守以下规则。

一、排序建议
1. 最多3条，只在确有必要时提出。
2. 排序依据只能是“与当前JD的直接相关程度 + 事实本身的具体性和信息量”。
3. JD条目出现顺序不等于优先级，除非JD明确写出优先级，否则不得自行判断。
4. 优先调整技能内部顺序、项目/实践内部顺序；除非确有明显必要，不大幅移动教育背景、联系方式、校园经历、自我评价等整个栏目。
5. 每条建议必须有1到2句话原因。
6. 原因只能解释：
   - 对应哪项JD；
   - 为什么调整后信息更集中、更容易识别。
7. 原因不得预测招聘者行为，不得写“招聘者一定会”“可完成全部确认”等绝对化表述。
8. 不得通过排序建议新增技能关系、项目关系或事实优先级。

二、表达精简建议
1. 最多3条。
2. 必须遵循“最小编辑原则”：原句已经清楚时，不为了体现优化而强行改写。
3. 只能删除纯冗余、纯时态标记，或做完全等义的轻微整理。
4. 每条建议必须保留原表述和建议表述，并用1到2句话解释原因。
5. 原因只说明删改了什么、为什么更简洁，以及事实含义为何没有改变。
6. “实现过基础RAG流程，包括……”优先写成“实现基础RAG流程，包括……”，不得改成“覆盖……环节”“完整流程”“系统性流程”等可能增强范围的词。
7. “完成过AI产品竞品分析，并整理过功能优缺点”可以做最小精简，但不得加入“各产品”“多款产品”等范围信息。
8. 如果Python是JD明确要求，不得为了去重删除“使用Python调用DeepSeek API”中的Python。
9. 两个独立技能不得合并成“LLM应用开发（含RAG）”“LLM/RAG应用开发”等新的包含、从属或组合关系。

三、事实边界
1. 必须保留原始事实中已经存在的“基础、初步、简单、部分、参与、协助、熟悉、了解”等影响事实强度的限定词。
2. 禁止新增原始事实中不存在的任何限定词、程度词或评价词。即使新增词看起来更保守、属于“降级”而不是“升级”，也属于事实改写，禁止添加。
   例如原文是“实现过RAG知识库问答流程”，不得改成“实现基础RAG知识库问答流程”“初步实现RAG知识库问答流程”。
   只能在完全等义时删除纯完成时态的“过”，得到“实现RAG知识库问答流程”。
3. “过”如果只是完成时态，可以删除，但不能连带删除原文已有的“基础”“简单”等限定词。
4. 不得生成原始事实不存在的项目名称、项目标题、括号项目名或事实性标签。
5. 不得跨字段、跨经历拼接事实。
6. 不得根据技术常识补全技术归属。例如不能把“Python”和“基础RAG流程”组合成“使用Python实现RAG”。
7. 技能栏中的并列技能必须保持独立，不新增包含、从属、等同或组合关系。
8. 不得新增项目背景、目的、用户、痛点、应用场景、数据来源、分析维度、技术框架、技术细节、项目结果、业务价值、量化指标。
9. 原事实未明确时，不得新增“各、多个、多项、多款、若干、全部、全面、独立、负责、主导、设计、深入、熟练、掌握、完整、全链路、核心、深度、成功、提升、验证”等扩大事实的词。
10. 不得因为JD条目靠前，就把对应事实描述为更重要、更核心。
11. 教育背景、校园经历、自我评价、联系方式只允许保留、调整已有顺序或完全等义精简，不强行加入JD关键词。
12. 保留原简历已有栏目名称，不擅自把“项目经历”改成“项目与实践”，或反过来。
13. 手机、邮箱保持原始纯文本内容。

四、简历草稿
1. 必须真实落实上面提出的安全排序和表达建议；如果某项建议无法安全落实，就不要提出该建议。
2. 原句已经清楚时，优先保留原措辞。
3. 使用Markdown文本：每个栏目写成“### 栏目名”，栏目内每条信息以“- ”开头。
4. 技能一项一行、联系方式一项一行、项目/实践一条一行。
5. 每个修改后的条目末尾标注【事实依据：对应的原始事实原文】，仅供后续审核模块使用。

五、后续可补充
1. jd_related最多3条，只询问已经存在经历中尚未写清楚的真实上下文，例如：
   - 这项实践具体解决什么问题；
   - 分析或服务的对象是什么；
   - 本人实际负责哪一部分；
   - 是否存在真实结果或反馈。
2. 每条jd_related必须明确“当前不能直接写入简历，确认真实做过后再补充”。
3. 不得主动引入简历和JD都没出现的高级技术、调优方法、实验方案、分析框架或评测指标。
4. general_advice最多2条，只给长期方向性建议，不把它们描述成当前缺陷，也不与jd_related重复。

你必须只返回合法JSON。
禁止返回Markdown代码块、解释性前后缀或JSON之外的任何文字。

严格使用以下结构：

{{
  "suggestions": {{
    "ordering": [
      {{
        "suggestion": "具体排序建议",
        "reason": "1到2句话原因"
      }}
    ],
    "wording": [
      {{
        "original": "原表述",
        "optimized": "建议表述",
        "reason": "1到2句话原因"
      }}
    ]
  }},
  "follow_up": {{
    "jd_related": [
      "当前JD相关补充问题。当前不能直接写入简历，确认真实做过后再补充。"
    ],
    "general_advice": [
      "通用长期建议"
    ]
  }},
  "resume_draft": "### 栏目名\\n- 内容【事实依据：原始事实】"
}}
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0,
    )

    result = parse_json_object(
        response.choices[0].message.content,
        label="优化建议结果",
    )

    suggestions = result.get("suggestions")
    follow_up = result.get("follow_up")
    resume_draft = result.get("resume_draft")

    if not isinstance(suggestions, dict):
        raise ValueError("优化建议结果缺少 suggestions 对象")
    if not isinstance(follow_up, dict):
        raise ValueError("优化建议结果缺少 follow_up 对象")
    if not isinstance(resume_draft, str) or not resume_draft.strip():
        raise ValueError("优化建议结果缺少 resume_draft")

    ordering = suggestions.get("ordering", [])
    wording = suggestions.get("wording", [])
    jd_related = follow_up.get("jd_related", [])
    general_advice = follow_up.get("general_advice", [])

    if not isinstance(ordering, list):
        raise ValueError("suggestions.ordering 必须是数组")
    if not isinstance(wording, list):
        raise ValueError("suggestions.wording 必须是数组")
    if not isinstance(jd_related, list):
        raise ValueError("follow_up.jd_related 必须是数组")
    if not isinstance(general_advice, list):
        raise ValueError("follow_up.general_advice 必须是数组")

    cleaned_ordering = []
    for index, item in enumerate(ordering[:3], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第{index}条排序建议不是JSON对象")
        suggestion = str(item.get("suggestion", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not suggestion or not reason:
            raise ValueError(f"第{index}条排序建议缺少 suggestion 或 reason")
        cleaned_ordering.append({
            "suggestion": suggestion,
            "reason": reason,
        })

    cleaned_wording = []
    for index, item in enumerate(wording[:3], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第{index}条表达建议不是JSON对象")
        original = str(item.get("original", "")).strip()
        optimized = str(item.get("optimized", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not original or not optimized or not reason:
            raise ValueError(
                f"第{index}条表达建议缺少 original、optimized 或 reason"
            )
        cleaned_wording.append({
            "original": original,
            "optimized": optimized,
            "reason": reason,
        })

    cleaned_jd_related = []
    for item in jd_related[:3]:
        text = str(item).strip()
        if text and text not in cleaned_jd_related:
            cleaned_jd_related.append(text)

    cleaned_general_advice = []
    for item in general_advice[:2]:
        text = str(item).strip()
        if text and text not in cleaned_general_advice:
            cleaned_general_advice.append(text)

    return {
        "suggestions": {
            "ordering": cleaned_ordering,
            "wording": cleaned_wording,
        },
        "follow_up": {
            "jd_related": cleaned_jd_related,
            "general_advice": cleaned_general_advice,
        },
        "resume_draft": clean_model_output(resume_draft),
    }


# ============================================================
# 8. 第五次调用：事实审核 + 最终优化版结构化
# ============================================================


def _clean_resume_item(value):
    """只做格式清理，不改写事实内容。"""
    text = str(value or "").strip()
    text = re.sub(r"^[-*•]\s*", "", text).strip()
    text = re.sub(r"\s*【事实依据：.*?】\s*$", "", text).strip()

    # 兜底：模型若偶发把邮箱转成 Markdown mailto，恢复纯文本。
    mailto_match = re.fullmatch(
        r"\[([^\]]+)\]\(mailto\\?:?([^)]*)\)",
        text,
        flags=re.IGNORECASE,
    )
    if mailto_match:
        text = mailto_match.group(1).strip()

    return text


def verify_resume(
    resume_facts,
    optimized_result,
):
    """
    V0.7 Step 3：事实审核结果与最终优化版简历全部结构化。

    返回：
    {
        "audit": [
            {
                "content": "...",
                "evidence": "...",
                "status": "通过 / 不通过",
                "reason": "..."
            }
        ],
        "safe_resume": {
            "sections": [
                {"name": "教育背景", "items": ["...", "..."]}
            ]
        }
    }
    """
    optimized_result_json = json.dumps(
        optimized_result,
        ensure_ascii=False,
        indent=2,
    )

    verify_prompt = f"""
你是一名极其严格的简历事实审核员。

【候选人已确认事实】
{resume_facts}

【结构化优化结果】
{optimized_result_json}

你只审核结构化优化结果中的 resume_draft，
同时检查 suggestions 中的安全排序/表达建议是否在草稿中正确落实。

最终目标不是“尽量润色”，而是输出一份事实最安全、结构清楚的简历正文。

审核规则：
1. 原始事实中已经存在的影响事实强度的限定词必须保留，如“基础、初步、简单、部分、参与、协助、熟悉、了解”。
2. 任何原始事实中不存在的限定词、程度词或评价词都不得新增，即使它让表述看起来更保守、属于降级，也必须判为“不通过”并恢复原始事实。
   例如原文“实现过RAG知识库问答流程”不能改成“实现基础RAG知识库问答流程”；“基础”虽是降级词，但仍是新增事实判断。
3. 仅作为完成时态的“过”可在完全不改变含义时删除。
4. 等义改写遵循最小编辑原则：原事实已经清楚时优先保留原措辞。
5. 如果改写使用“覆盖、完整性、系统性、全流程”等词，使范围或能力看起来更强，即使技术内容没有新增，也应判为不安全并恢复更接近原事实的表达。
6. 禁止新增项目名称、经历标题、括号项目名或事实性标签。
7. 禁止跨字段、跨经历融合事实；禁止利用技术常识补全实现关系。
8. “Python”“RAG”“Streamlit”等独立事实不能自动建立技术归属关系。
9. 不得把并列技能改成包含、从属、等同或组合关系，如“LLM应用开发（含RAG）”“LLM/RAG应用开发”。
10. 原事实未明确时，不得新增“各、多个、多项、多款、若干、全部、全面、独立、负责、主导、深入、熟练、精通、完整、全链路、显著、大幅、高效”等词。
11. 多条AI相关实践可以作为AI实践证据，但优化版不得凭空总结为“多个项目”或新增项目边界。
12. 教育背景、校园经历、自我评价、联系方式逐条保持原事实，不为了贴JD强行补关键词。
13. 手机、邮箱保持原始纯文本内容，不生成Markdown链接。
14. 不得为了所谓“精简”删除仍具有独立证据价值的技术词。例如JD要求Python时，“使用Python调用DeepSeek API”中的Python应保留。
15. suggestions.ordering 中合理且安全的排序建议必须在最终安全版落实；如果建议本身违反事实边界，则不执行。
16. suggestions.wording 中的表达建议只有在完全等义时才能执行；否则恢复对应原始事实。
17. 保留原简历已有栏目名称，不擅自改名。
18. 技能一项一条、联系方式一项一条、项目/实践一条一条；不得把多条事实塞进一个数组元素。
19. 草稿中的某条优化表述审核失败时，恢复对应的安全原始事实，而不是删除整个经历。
20. 信息完整性是硬约束：必须逐项对照【候选人已确认事实】，最终 safe_resume 中应保留其中每个独立、非重复的真实求职事实。不得因为某条事实与当前JD相关性较弱、看起来“不重要”或没有单独栏目就自行省略。专业/教育信息尤其不得丢失。若草稿漏掉某条已确认事实，审核器必须在最终安全版中恢复。
21. 最终优化版只保留简历正文，不保留【事实依据】、审核说明等中间信息。
22. safe_resume.sections 按最终简历实际展示顺序返回；每个栏目只出现一次。

audit 中逐条记录对 resume_draft 的事实审核：
- content：被审核的草稿表述；
- evidence：对应的候选人原始事实；
- status：只能是“通过”或“不通过”；
- reason：简短说明原因。

safe_resume 中只放最终可展示的简历正文。
不要在 safe_resume 中放 Markdown 标题、项目符号、事实依据或审核说明。

你必须只返回合法JSON。
禁止返回Markdown代码块、解释性前后缀或JSON之外的任何文字。

严格使用以下结构：

{{
  "audit": [
    {{
      "content": "草稿表述",
      "evidence": "对应原始事实",
      "status": "通过",
      "reason": "简短原因"
    }}
  ],
  "safe_resume": {{
    "sections": [
      {{
        "name": "原简历栏目名",
        "items": [
          "最终优化表述1",
          "最终优化表述2"
        ]
      }}
    ]
  }}
}}
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "user",
                "content": verify_prompt,
            }
        ],
        temperature=0,
    )

    result = parse_json_object(
        response.choices[0].message.content,
        label="事实审核结果",
    )

    audit = result.get("audit", [])
    safe_resume = result.get("safe_resume")

    if not isinstance(audit, list):
        raise ValueError("事实审核结果中的 audit 必须是数组")
    if not isinstance(safe_resume, dict):
        raise ValueError("事实审核结果缺少 safe_resume 对象")

    sections = safe_resume.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("safe_resume.sections 必须是非空数组")

    cleaned_audit = []
    for index, item in enumerate(audit, start=1):
        if not isinstance(item, dict):
            continue

        content = str(item.get("content", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        status = str(item.get("status", "")).strip()
        reason = str(item.get("reason", "")).strip()

        if status not in {"通过", "不通过"}:
            raise ValueError(
                f"第{index}条事实审核出现非法状态：{status}"
            )

        if not content:
            continue

        cleaned_audit.append(
            {
                "content": content,
                "evidence": evidence,
                "status": status,
                "reason": reason,
            }
        )

    cleaned_sections = []
    seen_sections = set()

    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise ValueError(f"第{index}个优化版栏目不是JSON对象")

        name = str(section.get("name", "")).strip()
        items = section.get("items", [])

        if not name:
            raise ValueError(f"第{index}个优化版栏目缺少 name")
        if name in seen_sections:
            raise ValueError(f"优化版简历出现重复栏目：{name}")
        if not isinstance(items, list):
            raise ValueError(f"优化版栏目 {name} 的 items 必须是数组")

        cleaned_items = []
        for value in items:
            item_text = _clean_resume_item(value)
            if item_text and item_text not in cleaned_items:
                cleaned_items.append(item_text)

        if not cleaned_items:
            continue

        cleaned_sections.append(
            {
                "name": name,
                "items": cleaned_items,
            }
        )
        seen_sections.add(name)

    if not cleaned_sections:
        raise ValueError("事实审核后未生成可用的优化版简历栏目")

    return {
        "audit": cleaned_audit,
        "safe_resume": {
            "sections": cleaned_sections,
        },
    }


# ============================================================
# 9. 单个 Case 完整运行
# ============================================================


def run_case(
    resume_text,
    jd_text,
):
    resume_facts = extract_facts(resume_text)
    jd_requirements = extract_jd_requirements(jd_text)
    jd_mapping = map_facts_to_jd(
        resume_facts,
        jd_requirements,
    )
    context = retrieve_knowledge(jd_text)
    optimized_result = optimize_resume(
        resume_facts,
        jd_requirements,
        jd_mapping,
        context,
    )
    verified_result = verify_resume(
        resume_facts,
        optimized_result,
    )

    return (
        resume_facts,
        jd_requirements,
        jd_mapping,
        optimized_result,
        verified_result,
    )


# ============================================================
# 10. Evaluation
# ============================================================


def evaluate_result(
    expected,
    resume_text,
    jd_text,
    resume_facts,
    jd_mapping,
    optimized_result,
    verified_result,
):
    jd_mapping_json = json.dumps(
        jd_mapping,
        ensure_ascii=False,
        indent=2,
    )
    optimized_result_json = json.dumps(
        optimized_result,
        ensure_ascii=False,
        indent=2,
    )
    verified_result_json = json.dumps(
        verified_result,
        ensure_ascii=False,
        indent=2,
    )

    evaluate_prompt = f"""
你是一名独立的AI产品评测员。

不能因为事实审核模块声称“通过”就默认最终结果正确。必须从零开始，对照原始简历检查最终输出。

【原始简历】
{resume_text}

【候选人事实抽取】
{resume_facts}

【目标岗位JD】
{jd_text}

【测试预期规则】
{expected}

【事实-JD映射】
{jd_mapping_json}

【结构化优化结果】
{optimized_result_json}

【结构化事实审核结果】
{verified_result_json}

评测指标：

1. 事实一致性
重点检查：
- 是否删除原文已有的“基础、初步、简单、参与、协助”等重要限定词；
- 是否新增原文不存在的限定词、程度词或评价词；即使新增的是“基础、初步、简单”等降级/保守词，也属于新增事实判断，不能因为更保守就放行；
- 是否新增项目名、项目边界、技术归属；
- 是否跨字段或跨经历组合事实；
- 是否把并列技能合并成包含/从属关系；
- 是否使用“各、多个、多项、完整、独立、负责、深入、熟练”等词扩大原事实；
- 是否用“覆盖、完整性、系统性”等词造成隐性范围增强。
存在上述问题不得给5分。

2. 幻觉控制
独立检查审核器是否错误放行：
- 新增项目标题；
- 任何原文不存在的限定词、程度词或评价词，包括看似更保守的“基础、初步、简单”等降级词；
- 程度、范围、数量或责任升级；
- 技术常识推断；
- 跨字段、跨经历融合；
- “多个项目”等未经事实支持的项目边界；
- “LLM应用开发（含RAG）”等新增技能关系。
审核器错误放行时不能给5分。

3. 信息完整性
必须逐项对照【原始简历】和【候选人事实抽取】检查最终优化版。
除纯重复信息外，原始简历中每个独立、真实的求职事实都应被保留，尤其是专业/教育背景、技能、项目/实践、校园经历、自我评价和联系方式。
不得自行判断某条事实“与JD不够相关”“看起来不重要”而允许删除；专业信息缺失也属于信息遗漏。
只要存在独立真实事实遗漏，信息完整性不得给5分；若遗漏教育/专业、技能或项目/实践等核心信息，应明确指出。

4. JD利用程度
检查：
- JD要求提取是否准确；
- 是否加入JD没写出的要求；
- 岗位匹配是否使用最直接证据；
- Python是否优先使用“技能声明 + 明确Python实践”；
- 是否避免用邻近课程硬撑LLM/RAG；
- 是否避免把JD条目顺序误当成优先级；
- 是否避免把AI相关实践无依据总结成“多个项目”。

5. 优化价值
允许来自：
- 合理排序；
- 信息组织；
- 删除纯冗余；
- 最小必要的完全等义精简；
- 将与JD直接相关的已有事实前置。

特别检查：
A. suggestions.ordering 与 suggestions.wording 是否均为结构化数据，字段完整。
B. 每条修改建议是否有1到2句话解释原因。
C. 原因是否只解释JD对应关系、信息清晰度和等义精简，不预测招聘者行为、不虚构优先级。
D. 修改建议是否真正落实到 resume_draft 和最终优化版；若未落实是否存在合理安全原因。
D. 是否为了“优化感”把原本清楚的“包括”改成“覆盖”，或使用“完整性认知”等增强性解释。
E. 后续可补充是否只围绕已有经历的真实上下文，没有主动引入Embedding模型比较、切分粒度、检索策略等资料未出现的高级方法。
F. 通用建议是否最多2条、方向性明确，并明确不是当前JD要求。
G. 岗位匹配是否短、通顺、能让用户快速知道“这条JD有没有证据”。
H. 最终 safe_resume 是否为结构化 sections/items；技能、联系方式、项目/实践分别独立成条，且不存在重复栏目。

额外评分纪律：
- 不得因为新增词“更保守”“属于降级”就把它视为安全；原文没有就是新增。
- 不得因为遗漏事实“对当前JD影响不大”“本案例聚焦其他部分”就忽略；只要是独立真实求职事实，遗漏就必须扣分。
- 评测目标是发现真实问题，不追求所有Case满分。

评分标准：
5 = 优秀，未发现明显问题
4 = 整体较好，有轻微问题
3 = 基本可用，但有明显改进空间
2 = 问题较严重
1 = 基本不可用

严格按以下格式输出一次：
事实一致性：X/5
幻觉控制：X/5
信息完整性：X/5
JD利用程度：X/5
优化价值：X/5
发现的问题：
- ...
总体评价：
...

不使用Markdown标题符号#、分隔线、表格、emoji或多余空行。
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "user",
                "content": evaluate_prompt,
            }
        ],
        temperature=0,
    )

    return clean_model_output(
        response.choices[0].message.content
    )


# ============================================================
# 11. 批量运行 6 组测试
# ============================================================

if __name__ == "__main__":
    for i in range(1, 7):
        case_name = f"case_{i:02d}"
        case_path = f"tests/{case_name}"

        print(f"\n{'=' * 60}")
        print(f"正在测试：{case_name}")
        print("=" * 60)

        resume_text = read_txt(
            f"{case_path}/resume.txt"
        )

        jd_text = read_txt(
            f"{case_path}/jd.txt"
        )

        expected = read_txt(
            f"{case_path}/expected.txt"
        )

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

        evaluation = evaluate_result(
            expected,
            resume_text,
            jd_text,
            resume_facts,
            jd_mapping,
            optimized_result,
            verified_result,
        )

        print("\n=== Evaluation ===")
        print(evaluation)

        result_path = f"{case_path}/result.txt"

        with open(
            result_path,
            "w",
            encoding="utf-8",
        ) as f:
            f.write("===== 简历事实提取 =====\n\n")
            f.write(resume_facts)

            f.write("\n\n===== JD要求提取 =====\n\n")
            f.write(jd_requirements)

            f.write("\n\n===== 事实-JD映射 =====\n\n")
            f.write(
                json.dumps(
                    jd_mapping,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            f.write("\n\n===== 结构化优化结果 =====\n\n")
            f.write(
                json.dumps(
                    optimized_result,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            f.write("\n\n===== 结构化事实核验结果 =====\n\n")
            f.write(
                json.dumps(
                    verified_result,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            f.write("\n\n===== Evaluation =====\n\n")
            f.write(evaluation)

    print("\n" + "=" * 60)
    print("6组测试全部完成")
    print("=" * 60)
