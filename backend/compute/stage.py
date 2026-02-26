from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import MarketStage, MetricValue, Score


STAGE_NAMES = {
    1: "深熊去杠杆",
    2: "筑底与换手",
    3: "复苏与吸筹",
    4: "上升趋势早期",
    5: "加速上涨与泡沫化",
    6: "高位派发与结构脆弱",
    7: "见顶回落与再去杠杆",
}


def _clip(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))


def _classify_stage(capital: float, risk: float, trend: Optional[float]) -> tuple[int, float, dict]:
    trend_v = trend or 0.0

    if capital < 25 and risk >= 70:
        stage_id = 1
        rule = "capital_low_and_risk_high"
    elif capital < 40 and risk >= 45:
        stage_id = 2
        rule = "early_base_building"
    elif 40 <= capital < 55 and risk < 60 and trend_v >= -5:
        stage_id = 3
        rule = "recovery_accumulation"
    elif 55 <= capital < 70 and risk < 55 and trend_v > 0:
        stage_id = 4
        rule = "early_uptrend"
    elif capital >= 70 and risk < 45 and trend_v > 5:
        stage_id = 5
        rule = "bubble_acceleration"
    elif capital >= 60 and risk >= 55:
        stage_id = 6
        rule = "distribution_fragile"
    else:
        stage_id = 7
        rule = "rollover_deleveraging"

    confidence = _clip(0.5 + abs(capital - risk) / 200, 0.5, 0.95)
    evidence = {
        "rule": rule,
        "capital_inflow_score": capital,
        "structure_risk_score": risk,
        "trend_proxy": trend_v,
    }
    return stage_id, confidence, evidence


def _public_explanation(stage_id: int) -> str:
    text = {
        1: "资金弱且风险高，市场仍在去杠杆阶段。",
        2: "风险下降但资金不足，市场在底部换手。",
        3: "资金与趋势改善，市场进入复苏吸筹。",
        4: "资金持续回流且风险可控，上升趋势开始形成。",
        5: "资金过热、走势加速，需警惕泡沫化。",
        6: "资金仍高但结构风险抬升，偏高位派发。",
        7: "趋势走弱并伴随风险回升，进入回落再去杠杆。",
    }
    return text[stage_id]


def _professional_explanation(stage_id: int, evidence: dict) -> str:
    return (
        f"阶段由规则 {evidence['rule']} 触发，"
        f"capital={evidence['capital_inflow_score']:.2f}, "
        f"risk={evidence['structure_risk_score']:.2f}, "
        f"trend={evidence['trend_proxy']:.2f}."
    )


def _upsert_market_stage(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = insert(MarketStage).values(rows)
    upsert = stmt.on_conflict_do_update(
        index_elements=["ts"],
        set_={
            "stage_id": stmt.excluded.stage_id,
            "stage_name": stmt.excluded.stage_name,
            "confidence": stmt.excluded.confidence,
            "explanation_public": stmt.excluded.explanation_public,
            "explanation_pro": stmt.excluded.explanation_pro,
            "evidence": stmt.excluded.evidence,
        },
    )
    result = db.execute(upsert)
    return int(result.rowcount or 0)


def compute_market_stage(
    db: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> int:
    cap_stmt = select(Score).where(Score.score_id == "capital_inflow_score")
    risk_stmt = select(Score).where(Score.score_id == "structure_risk_score")

    filters = []
    if start:
        filters.append(Score.ts >= start)
    if end:
        filters.append(Score.ts <= end)

    if filters:
        cap_stmt = cap_stmt.where(and_(*filters))
        risk_stmt = risk_stmt.where(and_(*filters))

    cap_rows = {row.ts: float(row.value) for row in db.execute(cap_stmt).scalars().all()}
    risk_rows = {row.ts: float(row.value) for row in db.execute(risk_stmt).scalars().all()}

    trend_stmt = select(MetricValue).where(MetricValue.metric_id == "spot_volume_trend")
    if start:
        trend_stmt = trend_stmt.where(MetricValue.ts >= start)
    if end:
        trend_stmt = trend_stmt.where(MetricValue.ts <= end)
    trend_rows = {row.ts: float(row.value) for row in db.execute(trend_stmt).scalars().all()}

    rows: list[dict] = []
    for ts in sorted(set(cap_rows.keys()) & set(risk_rows.keys())):
        stage_id, confidence, evidence = _classify_stage(
            capital=cap_rows[ts],
            risk=risk_rows[ts],
            trend=trend_rows.get(ts),
        )
        rows.append(
            {
                "ts": ts,
                "stage_id": stage_id,
                "stage_name": STAGE_NAMES[stage_id],
                "confidence": confidence,
                "explanation_public": _public_explanation(stage_id),
                "explanation_pro": _professional_explanation(stage_id, evidence),
                "evidence": evidence,
            }
        )

    return _upsert_market_stage(db=db, rows=rows)
