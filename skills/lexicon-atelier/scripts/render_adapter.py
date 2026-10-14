# -*- coding: utf-8 -*-
"""适配层：把术语层的数据翻译成排版引擎（gzh-design）能接受的输入。

⚠️ 本文件是「适配层」，不是「排版层」。

  - **排版实际由 gzh-design 完成**：公众号 HTML 生成、平台合规校验、
    复制到公众号的交互，全部由那个开源 skill 负责。
  - **本文件只做数据格式转换**：不生成 HTML、不写样式、不碰颜色字号。
    它把 lexicon_core 的词典 + anchor_matcher 的锚点，重新打包成
    排版引擎要的形状，然后交出去。
  - **要换排版引擎，只改本文件**。lexicon_core 与 anchor_matcher 一行都不用动
    —— 这正是分层的意义：核心贡献自己写，非核心的排版复用成熟工具，
    中间用一层薄适配隔开。

为什么要适配而不是直接对接
--------------------------
术语层的产物是「术语语义」（编号、分组、别名、定义、出现位置），
排版层的输入是「版面元素」（卡片、栏位、徽标）。两者的关心点不同，
直接耦合会让任何一边的改动都传染到另一边。
"""

# 排版引擎需要的卡片字段（gzh-design 的术语栏条目就吃这几个）
CARD_FIELDS = ("id", "zh", "en", "category", "one_line", "appendix_ref", "anchor")


def _to_card(term, anchor_by_id):
    """单条术语 → TermCard。"""
    a = anchor_by_id.get(term["编号"])
    return {
        "id": term["编号"],
        "zh": term["中文名"],
        "en": term.get("英文名", ""),
        "category": term.get("分类", ""),
        "one_line": term.get("一句话定义", ""),
        "appendix_ref": term.get("附录锚点", "附录 " + term["编号"]),
        # 锚点可能为空——别名没在正文里命中。排版层据此决定是否投放卡片。
        "anchor": ({"char_start": a.char_start,
                    "char_end": a.char_end,
                    "alias": a.matched_alias} if a else None),
    }


def to_gzh_input(lexicon, anchors):
    """把词典 + 锚点翻译成排版引擎的输入。

    lexicon : lexicon_core.build_lexicon() 的产物
    anchors : anchor_matcher.locate_anchors() 的产物

    返回：
        {
          "meta":  {标题 / 副标题 / 术语总数 / 编号范围 / 分组},
          "cards": [TermCard, ...],     全部术语（含未命中的，anchor 为 None）
          "placed": [TermCard, ...],    仅命中锚点的，按在正文中出现先后排序
        }

    为什么同时给 cards 和 placed：
      - 排版层要按「出现先后」投放右栏素材，用 placed；
      - 但附录要列全部术语（包括没在正文出现的），用 cards。
    """
    anchor_by_id = {a.term_id: a for a in anchors}
    cards = [_to_card(t, anchor_by_id) for t in lexicon.get("术语", [])]
    placed = sorted((c for c in cards if c["anchor"]),
                    key=lambda c: c["anchor"]["char_start"])
    return {
        "meta": {
            "标题": lexicon.get("标题", ""),
            "副标题": lexicon.get("副标题", ""),
            "术语总数": lexicon.get("术语总数", len(cards)),
            "编号范围": lexicon.get("编号范围", ""),
            "分组": lexicon.get("分组", {}),
        },
        "cards": cards,
        "placed": placed,
    }


# ------------------------------------------------------------------ 自检
if __name__ == "__main__":
    import sys

    # 本文件在 scripts/ 下，同目录的兄弟模块直接可导入
    from lexicon_core import build_lexicon
    from anchor_matcher import locate_anchors

    terms = [
        dict(编号="A1", 中文名="抗体偶联药物", 英文名="Antibody-Drug Conjugate, ADC",
             分类="技术", 别名=["抗体偶联药物", "ADC"],
             一句话定义="把抗体与毒素拼在一起的药物形态。",
             是什么="定义。", 有什么作用="作用。", 机制原理="机制。"),
        dict(编号="A2", 中文名="偶联", 英文名="Conjugation", 分类="技术",
             别名=["偶联"], 一句话定义="把毒素接到抗体上的工艺环节。",
             是什么="定义。", 有什么作用="作用。", 机制原理="机制。"),
    ]
    body = "ADC 是近年最热的形态。偶联环节对工艺要求极高。"

    lex = build_lexicon(terms)
    anc = locate_anchors(body, terms)
    out = to_gzh_input(lex, anc)

    print("meta:", out["meta"]["术语总数"], "条 |", out["meta"]["编号范围"])
    for c in out["cards"]:
        loc = c["anchor"]
        print(f"  {c['id']:3s} {c['zh']:8s} 锚点 "
              + (f"[{loc['char_start']},{loc['char_end']}) 别名 {loc['alias']!r}"
                 if loc else "未命中"))
    print("placed 顺序:", [c["id"] for c in out["placed"]])
    assert list(out["cards"][0].keys()) == list(CARD_FIELDS), "TermCard 字段不符"
    print("TermCard 字段：符合约定")
