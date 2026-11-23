"""Gemini API で「写真＋音声 → 求人の下書き（JSON）」を作る。

AI は「下書き係」。ここで作った内容は、必ず生産者が確認してから公開する。
APIキーが無いときは、テスト用の仮AI（決まった下書きを返す）で動く。
"""
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from .config import Settings
from .schemas import JobDraft

log = logging.getLogger(__name__)

WEEKDAYS = "月火水木金土日"

SYSTEM_INSTRUCTION = """\
あなたは宮崎県日南市の農家・漁師が「短時間のお手伝い」を募集するときの、求人づくりの係です。
生産者は高齢の方が多く、日南弁（宮崎の方言）で話します。
写真と音声から、求人の項目を決められた形式で出力してください。

ルール:
- 音声で話された内容を一番大切にする。写真は作業内容・持ち物・注意点・重さの目安を考える手がかりにする。
- 日時・人数・時給は、話に出てこなければ null にする。勝手に推測しない。
- 「明日」「あさって」「今度の土曜」などは、今日の日付をもとに YYYY-MM-DD に直す。
- 時刻は24時間制 HH:MM。「朝8時」は 08:00、「夕方5時」は 17:00。
- 作業場所が船の上なら location_type を boat、畑・倉庫・岸壁など陸上なら land にする。
- 重さは、写真に写っている箱や道具から、1人が1回に持つ重さの目安を kg で答える。分からなければ null。
- 持ち物と注意点は、未経験の高校生が安全に作業できるように、具体的に短く書く。
- 個人名・電話番号・番地などの個人情報は出力しない。地区名までにする。
"""


class AIError(Exception):
    """AIで下書きを作れなかったとき。"""


@dataclass
class Media:
    data: bytes
    mime_type: str


def _today_text(today: date) -> str:
    return f"今日は {today.isoformat()}（{WEEKDAYS[today.weekday()]}曜日）です。"


def generate_draft(settings: Settings, image: Media | None, audio: Media | None, today: date) -> JobDraft:
    """写真と音声から、新しく下書きを作る。"""
    if settings.use_mock_ai:
        return _mock_first_draft(today)
    prompt = _today_text(today) + "\nこの写真と音声から、求人の下書きを作ってください。"
    return _call_gemini(settings, prompt, image, audio)


def refine_draft(settings: Settings, current: JobDraft, audio: Media, today: date) -> JobDraft:
    """足りない項目を聞き直したときの答え（音声）で、下書きを更新する。"""
    if settings.use_mock_ai:
        return _mock_refine(current)
    prompt = (
        _today_text(today)
        + "\n今の下書きは次のとおりです。\n"
        + current.model_dump_json()
        + "\n生産者が足りない項目について追加で話しました。音声の内容で下書きを更新してください。"
        "音声で触れられていない項目は、今の下書きの値をそのまま残してください。"
    )
    return _call_gemini(settings, prompt, None, audio)


def _call_gemini(settings: Settings, prompt: str, image: Media | None, audio: Media | None) -> JobDraft:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    contents: list = []
    if image:
        contents.append(types.Part.from_bytes(data=image.data, mime_type=image.mime_type))
    if audio:
        contents.append(types.Part.from_bytes(data=audio.data, mime_type=audio.mime_type))
    contents.append(prompt)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=JobDraft,  # この形のJSONで返すように指定する
        temperature=0.2,
    )

    # 1回目はいつものモデル、失敗したら予備のモデルでもう1回（混雑していることがあるため）
    models = [settings.gemini_model, settings.gemini_fallback_model or settings.gemini_model]
    last_error: Exception | None = None
    for attempt, model in enumerate(models, start=1):
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            # 返ってきたJSONを Pydantic で型チェックする（形が違えばここでエラー）
            return JobDraft.model_validate_json(response.text)
        except Exception as e:  # 通信エラー・混雑・形式エラーなど
            last_error = e
            log.warning("Gemini 呼び出し失敗（%d回目・%s）: %s", attempt, model, str(e)[:200])
    raise AIError("下書きを作れませんでした") from last_error


# ---------------- テスト用の仮AI ----------------
# APIキーが無くても画面の流れを確かめられるように、決まった下書きを返す。
# 1回目は「時給」が足りない下書き → 聞き直すと時給が埋まる。


def _mock_first_draft(today: date) -> JobDraft:
    return JobDraft(
        title="極早生ミカンの出荷補助",
        description="収穫したミカンの箱を、倉庫から軽トラックに積みます。",
        industry="farm",
        work_date=(today + timedelta(days=1)).isoformat(),
        start_time="08:00",
        end_time="11:00",
        headcount=2,
        hourly_wage=None,
        area="北郷",
        location_type="land",
        max_weight_kg=10,
        items=["軍手（すべり止め付き）", "帽子", "水筒", "汚れてもいい服"],
        cautions=["箱は2人1組で運ぶ", "腰を落として持ち上げる", "こまめに水分をとる"],
        beginner_ok=True,
    )


def _mock_refine(current: JobDraft) -> JobDraft:
    return current.model_copy(update={"hourly_wage": current.hourly_wage or 1100})
