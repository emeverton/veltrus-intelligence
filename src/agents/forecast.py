import asyncio
import logging
from typing import Optional

from sqlalchemy import text as sql_text

from src.database import AsyncSessionFactory

logger = logging.getLogger(__name__)


async def _load_revenue_data(channel: Optional[str] = None):
    """Carrega dados históricos de conversões agrupados por dia."""
    import pandas as pd

    async with AsyncSessionFactory() as session:
        query = """
            SELECT
                DATE_TRUNC('day', conv.occurred_at)::date AS ds,
                SUM(conv.revenue)                         AS y
            FROM attribution_conversions conv
        """
        if channel:
            query += """
            JOIN attribution_results ar
              ON ar.conversion_id = conv.id
             AND ar.model = 'linear'
             AND ar.channel = :channel
            """
        query += """
            GROUP BY 1
            ORDER BY 1
        """
        params = {"channel": channel} if channel else {}
        result = await session.execute(sql_text(query), params)
        rows = result.fetchall()

    if not rows:
        return pd.DataFrame(columns=["ds", "y"])

    df = pd.DataFrame(rows, columns=["ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = df["y"].astype(float)
    return df


def _run_prophet(df, days: int) -> list[dict]:
    """Ajusta Prophet e retorna forecast. Síncrono."""
    import pandas as pd
    from prophet import Prophet

    if len(df) < 2:
        return []

    model = Prophet(
        yearly_seasonality=False,
        weekly_seasonality=(len(df) >= 14),
        daily_seasonality=False,
        uncertainty_samples=0,
    )
    model.fit(df)
    future = model.make_future_dataframe(periods=days)
    forecast = model.predict(future)

    last_date = df["ds"].max()
    future_only = forecast[forecast["ds"] > last_date][["ds", "yhat", "yhat_lower", "yhat_upper"]]

    results = []
    for _, row in future_only.iterrows():
        entry = {
            "date": row["ds"].strftime("%Y-%m-%d"),
            "forecast": round(max(0.0, float(row["yhat"])), 2),
        }
        if pd.notna(row["yhat_lower"]):
            entry["lower"] = round(max(0.0, float(row["yhat_lower"])), 2)
        if pd.notna(row["yhat_upper"]):
            entry["upper"] = round(max(0.0, float(row["yhat_upper"])), 2)
        results.append(entry)
    return results


async def forecast_revenue_async(days: int = 30, channel: Optional[str] = None) -> dict:
    """Wrapper async: carrega dados e roda Prophet em thread pool."""
    df = await _load_revenue_data(channel)

    if df.empty or len(df) < 2:
        return {
            "status": "insufficient_data",
            "message": "Sem dados históricos suficientes para forecast (mínimo 2 dias).",
            "data_points": len(df),
        }

    logger.info(
        "Running Prophet forecast: %s data points, %s days ahead, channel=%s",
        len(df),
        days,
        channel,
    )
    forecast = await asyncio.to_thread(_run_prophet, df, days)

    if not forecast:
        return {
            "status": "insufficient_data",
            "message": "Sem dados históricos suficientes para forecast.",
            "data_points": len(df),
        }

    return {
        "status": "ok",
        "days_ahead": days,
        "channel": channel,
        "data_points": len(df),
        "forecast": forecast,
    }
