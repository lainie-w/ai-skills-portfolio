# -*- coding: utf-8 -*-
"""术语层核心：读取术语数据 → 构建结构化词典 → 编号一致性校验。

分层定位
--------
本文件属于「术语层」，是 skill 的核心贡献，不依赖任何排版引擎。
它只关心「术语本身」：分组、编号、字段完整性、一致性。
输出是一份可以直接复用、检索、交给同事的词典数据结构。

对外接口
--------
    build_lexicon(terms)     -> dict     构建词典（内部会先校验）
    validate_lexicon(dict)   -> None     校验已有词典，不合规 raise

校验失败一律 raise LexiconError，不静默通过——编号错乱是这类文档
最隐蔽也最致命的错误，必须在生成阶段就拦住。
"""

from collections import Counter, OrderedDict

# 分组默认名：编号首字母 → 组名。按文章体裁自行改写。
DEFAULT_GROUP_NAMES = {
    "A": "技术基础",
    "B": "关键指标",
    "C": "监管与政策",
    "D": "临床与证据",
    "E": "产业与市场",
    "F": "企业与资产",
    "G": "判断与信号",
}

# 词条必须齐备的字段（缺一不可）
REQUIRED_FIELDS = ("中文名", "一句话定义", "是什么", "有什么作用", "机制原理")


class LexiconError(ValueError):
    """术语数据不合规。"""


def build_groups(terms, group_names=None):
    """按实际用到的编号首字母生成分组表，区间从数据算出来。

    刻意不硬编码区间（如写死 "A1–A8"）——增删术语后很容易忘记同步，
    这是踩过的坑：词典从 56 条精简到 43 条后，附录还写着旧区间。
    """
    names = dict(DEFAULT_GROUP_NAMES)
    names.update(group_names or {})
    cnt = Counter(t["编号"][0] for t in terms)
    groups = OrderedDict()
    for letter in sorted(cnt):
        n = cnt[letter]
        groups[letter] = f"{letter} 组 · {names.get(letter, letter + ' 组')}（{letter}1–{letter}{n}）"
    return groups


def validate_lexicon(lexicon):
    """校验词典：编号唯一、每组从 1 连续、三段详解齐备、别名非空。

    不合规直接 raise LexiconError。
    """
    terms = lexicon.get("术语")
    if not terms:
        raise LexiconError("词典里没有任何术语")

    # 1) 编号唯一
    ids = [t.get("编号", "") for t in terms]
    dup = [i for i, c in Counter(ids).items() if c > 1]
    if dup:
        raise LexiconError(f"编号重复：{dup}")

    # 2) 编号格式 & 每组从 1 连续、不跳号
    cnt = Counter()
    for i in ids:
        if len(i) < 2 or not i[0].isalpha() or not i[1:].isdigit():
            raise LexiconError(f"编号格式不对：{i!r}（应为「字母 + 数字」，如 A1）")
        cnt[i[0]] += 1
    for letter, n in sorted(cnt.items()):
        got = sorted(int(i[1:]) for i in ids if i[0] == letter)
        if got != list(range(1, n + 1)):
            raise LexiconError(f"{letter} 组编号不连续：{got}（应为 1–{n}）")

    # 3) 字段齐备
    for t in terms:
        for f in REQUIRED_FIELDS:
            if f in ("是什么", "有什么作用", "机制原理"):
                if not (t.get("详细解释") or {}).get(
                        {"是什么": "是什么（定义）",
                         "有什么作用": "用途（有什么作用）",
                         "机制原理": "机制原理（如何工作）"}[f]):
                    raise LexiconError(f"{t.get('编号')} 缺「{f}」")
            elif not t.get(f):
                raise LexiconError(f"{t.get('编号')} 缺字段「{f}」")

    # 4) 别名非空——正文靠别名定位「首次出现」，缺了术语就投不出去
    for t in terms:
        if not t.get("别名"):
            raise LexiconError(f"{t.get('编号')} 缺「别名」——正文将无法定位它的首次出现")

    # 5) 声明的总数与编号范围要和实际一致
    if lexicon.get("术语总数") not in (None, len(terms)):
        raise LexiconError(
            f"术语总数不符：声明 {lexicon['术语总数']}，实际 {len(terms)}")
    real_range = f"{terms[0]['编号']}–{terms[-1]['编号']}"
    if lexicon.get("编号范围") not in (None, real_range):
        raise LexiconError(
            f"编号范围不符：声明 {lexicon['编号范围']}，实际 {real_range}")


def build_lexicon(terms, group_names=None, meta=None):
    """把术语数据（dict 列表）编译成结构化词典。

    terms 里每条至少要有：编号 / 中文名 / 分类 / 别名 /
    一句话定义 / 是什么 / 有什么作用 / 机制原理。
    其余字段（英文名、原文出现位置）可选。
    """
    groups = build_groups(terms, group_names)

    items = []
    for t in terms:
        tid = t["编号"]
        items.append({
            "编号": tid,
            "中文名": t["中文名"],
            "英文名": t.get("英文名", ""),
            "分类": t.get("分类", ""),
            "组": groups[tid[0]],
            "别名": list(t["别名"]),
            "一句话定义": t["一句话定义"],
            "原文出现位置": t.get("原文出现位置", ""),
            "详细解释": {
                "是什么（定义）": t["是什么"],
                "用途（有什么作用）": t["有什么作用"],
                "机制原理（如何工作）": t["机制原理"],
            },
            "附录锚点": "附录 " + tid,
        })

    m = dict(meta or {})
    lexicon = {
        "标题": m.get("标题", "术语词典"),
        "副标题": m.get("副标题", ""),
        "术语总数": len(items),
        "编号范围": f"{items[0]['编号']}–{items[-1]['编号']}",
        "收词原则": m.get("收词原则", "只收需要解释的专业条目；常识性概念不列入。"),
        "分组": groups,
        "字段说明": {
            "编号": "按组内顺序连续编号，与正文附录、两栏术语栏严格一致",
            "分类": "展示为小标签",
            "一句话定义": "用于正文右侧术语栏",
            "别名": "正文里定位「首次出现」的说法，按优先级排列",
            "详细解释": "三段式：是什么 / 用途 / 机制原理",
        },
        "术语": items,
    }

    validate_lexicon(lexicon)
    return lexicon


# ------------------------------------------------------------------ 自检
if __name__ == "__main__":
    sample = [
        dict(编号="A1", 中文名="术语甲", 英文名="Alpha", 分类="技术",
             别名=["术语甲", "甲"], 一句话定义="甲的通俗解释。",
             是什么="甲的定义。", 有什么作用="甲的作用。", 机制原理="甲的机制。",
             原文出现位置="一、技术路线"),
        dict(编号="B1", 中文名="术语乙", 英文名="Beta", 分类="产业",
             别名=["术语乙"], 一句话定义="乙的通俗解释。",
             是什么="乙的定义。", 有什么作用="乙的作用。", 机制原理="乙的机制。",
             原文出现位置="二、产业链"),
    ]
    lex = build_lexicon(sample, meta={"标题": "自检用例"})
    print("构建成功：", lex["术语总数"], "条 |", lex["编号范围"])
    print("分组：", list(lex["分组"].values()))

    # 故意制造编号跳号，确认校验会拦住
    bad = [dict(sample[0]), dict(sample[1], 编号="B3")]
    try:
        build_lexicon(bad)
    except LexiconError as e:
        print("校验拦截成功：", e)
    else:
        raise SystemExit("!! 校验未能拦截错误编号，请检查 validate_lexicon")
