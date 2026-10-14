# -*- coding: utf-8 -*-
"""术语锚点定位：按别名优先级找到术语在正文里「第一次出现」的位置，并生成标记。

分层定位
--------
本文件属于「术语层」，是 skill 的核心贡献。它不生成 HTML、不关心样式，
只负责一件事：**在正文里准确找到每个术语的首次出现位置**。

为什么单独抽出来
----------------
这是整个流程里最容易出错的一步，而且出错方式很隐蔽——
术语卡片挂到了无关段落旁，或者干脆投不出来，肉眼很难发现。

踩过的两个坑，本文件的实现就是针对它们写的：

  坑一：不要「边替换边搜索」
      如果术语甲的别名是术语乙别名的子串（例如「偶联」⊂「抗体偶联药物」），
      先替换的那个会把原文换成占位符，后者就再也找不到自己的文本了。
      → 正确做法：先在原文里定位全部锚点，再统一拼接。

  坑二：别名要按优先级匹配，且重叠时跳过
      同一段文字不能被两个术语同时占用，否则会产出嵌套的重复标记。
      → 按位置排序后贪心接受不重叠的锚点。

对外接口
--------
    locate_anchors(text, terms)      -> list[Anchor]   定位锚点
    apply_anchors(text, anchors, …)  -> str            统一拼接成标记后的文本
"""

from dataclasses import dataclass


@dataclass
class Anchor:
    """一个术语在正文中的首次出现位置。

    char_start / char_end 是**半开区间** [start, end)，
    可直接用于 text[start:end] 取到命中的那段原文。
    """
    term_id: str
    char_start: int
    char_end: int
    matched_alias: str


def locate_anchors(text, terms, consumed=None):
    """定位每个术语在 text 里的首次出现。

    terms     : 术语 dict 列表，每条需含「编号」与「别名」（别名按优先级排列）
    consumed  : 已处理过的术语编号集合，传 None 表示全部参与
    返回      : list[Anchor]，按在正文中出现的先后排序；
                别名未命中的术语不会出现在结果里（调用方可用编号差集找出）

    匹配规则
    --------
    1. 每个术语按「别名」列表顺序试，取**第一个能在文中找到的别名**
    2. 同一术语只产生一个锚点
    3. 锚点之间不允许重叠：按位置排序后，先到先得，冲突的跳过
       —— 这样「抗体偶联药物」会占住那段文字，「偶联」自动让位
    """
    consumed = consumed or set()
    found = []

    for t in terms:
        tid = t["编号"]
        if tid in consumed:
            continue
        for alias in t.get("别名") or []:
            pos = text.find(alias)
            if pos >= 0:
                found.append((pos, pos + len(alias), tid, alias))
                break

    # 按位置排序；位置相同时，别名更长的优先（更具体，信息量更大）
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    anchors, taken = [], []
    for start, end, tid, alias in found:
        if any(not (end <= s or start >= e) for s, e in taken):
            continue                      # 与已接受的锚点重叠 → 跳过
        taken.append((start, end))
        anchors.append(Anchor(term_id=tid, char_start=start,
                              char_end=end, matched_alias=alias))
    return anchors


def apply_anchors(text, anchors, wrap_anchor, wrap_plain=None):
    """把锚点铺回原文，**统一拼接**成最终文本。

    这是「先定位、后拼接」的第二步：第一步 locate_anchors 只算位置不动原文，
    这一步才真正生成结果，因此不存在前者覆盖后者的问题。

    wrap_anchor(text, anchor)  把命中的那段原文渲染成带标记的形式
    wrap_plain(text)           普通片段的渲染方式；传 None 表示原样保留

    anchors 必须互不重叠——locate_anchors 已经保证了这一点。
    """
    plain = wrap_plain or (lambda s: s)
    pieces, cursor = [], 0
    for a in sorted(anchors, key=lambda x: x.char_start):
        if a.char_start < cursor:
            raise ValueError(f"锚点重叠：{a.term_id} 起始 {a.char_start} < 游标 {cursor}")
        if a.char_start > cursor:
            pieces.append(plain(text[cursor:a.char_start]))
        pieces.append(wrap_anchor(text[a.char_start:a.char_end], a))
        cursor = a.char_end
    if cursor < len(text):
        pieces.append(plain(text[cursor:]))
    return "".join(pieces)


# ------------------------------------------------------------------ 自检
if __name__ == "__main__":
    # 故意构造「短别名是长别名子串」的场景：A2 的「偶联」就藏在
    # A1 的「抗体偶联药物」里面，验证后者不会把前者的文本吃掉。
    body = "抗体偶联药物是近年最热的形态。偶联环节对工艺要求极高。"
    terms = [
        dict(编号="A1", 别名=["抗体偶联药物", "ADC"]),   # 命中 [0,6)
        dict(编号="A2", 别名=["偶联"]),                  # 首次出现在 2，与 A1 重叠
        dict(编号="A3", 别名=["不存在的词"]),             # 应当找不到
    ]

    anchors = locate_anchors(body, terms)
    for a in anchors:
        print(f"  {a.term_id:4s} [{a.char_start:3d},{a.char_end:3d}) "
              f"命中 {a.matched_alias!r} → {body[a.char_start:a.char_end]!r}")

    ids = {a.term_id for a in anchors}
    print("未命中：", sorted({t['编号'] for t in terms} - ids))

    marked = apply_anchors(
        body, anchors,
        wrap_anchor=lambda s, a: f"【{a.term_id}:{s}】",
        wrap_plain=lambda s: s,
    )
    print("拼接结果：", marked)

    # 断言：A1 与 A2 不能同时占用同一段文字；A3 找不到就该没有锚点
    assert ids == {"A1"}, f"预期只命中 A1，实际 {ids}"
    assert "【A1:抗体偶联药物】" in marked, "A1 应完整覆盖「抗体偶联药物」"
    assert "【A2" not in marked, "A2 与 A1 重叠，应被跳过"
    print("重叠保护：通过（A2 因与 A1 重叠被跳过，未产出嵌套标记）")
