"""求人カードに出す「日南の統計ひとこと」。

出典：日南市ミニ統計 令和4年版〜令和8年版（日南市総合政策課）
（農林業センサス R2→R7、漁業センサス H30→R5）
"""
import random

SOURCE = "日南市ミニ統計（日南市総合政策課）"

FACTS: dict[str, list[str]] = {
    "farm": [
        "市内で農業に携わる人は、5年で28.5%減りました（1,945人→1,391人）。",
        "市内の農家は、5年で約4分の1減りました（1,324戸→987戸）。",
    ],
    "fish": [
        "漁業の経営体は142→151に増えたのに、働く人は538人→442人に減りました。",
        "1つの経営体で働く人は、3.79人から2.93人に減りました。",
    ],
    "other": [
        "日南市の人口は4年で約3,900人減りました（49,224人→45,282人）。",
    ],
}

CLOSING = "あなたの3時間が、産地を支えます。"


def hint_for(industry: str, seed: int | None = None) -> str:
    facts = FACTS.get(industry) or FACTS["other"]
    rng = random.Random(seed)
    return rng.choice(facts)
