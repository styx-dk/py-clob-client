import os
import math
from collections import Counter
from datetime import datetime, timezone

from dotenv import load_dotenv

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OpenOrderParams, TradeParams, BalanceAllowanceParams
from py_clob_client.constants import POLYGON

HOST = os.getenv("CLOB_HOST", "https://clob.polymarket.com")
CHAIN_ID = int(os.getenv("CHAIN_ID", str(POLYGON)))
PRIVATE_KEY = os.getenv("PK")
FUNDER = os.getenv("FUNDER")
SIGNATURE_TYPE = int(os.getenv("SIGNATURE_TYPE", "2"))


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def _parse_time(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _format_dt(value):
    dt = _parse_time(value)
    if not dt:
        return "-"
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def make_client():
    if not PRIVATE_KEY:
        raise RuntimeError("Missing PK in environment")

    load_dotenv()

    l1 = ClobClient(
        host=HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        signature_type=SIGNATURE_TYPE,
        funder=FUNDER,
    )

    api_key = os.getenv("CLOB_API_KEY")
    api_secret = os.getenv("CLOB_API_SECRET")
    api_passphrase = os.getenv("CLOB_API_PASSPHRASE")

    if api_key and api_secret and api_passphrase:
        creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
    else:
        creds = l1.create_or_derive_api_creds()

    return ClobClient(
        host=HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        creds=creds,
        signature_type=SIGNATURE_TYPE,
        funder=FUNDER,
    )


def fetch_all(client):
    orders = client.get_orders(OpenOrderParams())
    trades = client.get_trades(TradeParams())
    balance = client.get_balance_allowance(
        BalanceAllowanceParams(asset_type="COLLATERAL", signature_type=SIGNATURE_TYPE)
    )
    notifications = client.get_notifications()
    return orders, trades, balance, notifications


def build_dashboard(orders, trades, balance, notifications):
    buy_orders = [o for o in orders if str(o.get("side", "")).upper() == "BUY"]
    sell_orders = [o for o in orders if str(o.get("side", "")).upper() == "SELL"]

    total_buy_size = sum(_safe_float(o.get("original_size") or o.get("size")) for o in buy_orders)
    total_sell_size = sum(_safe_float(o.get("original_size") or o.get("size")) for o in sell_orders)

    filled_trades = [t for t in trades if _safe_float(t.get("size")) > 0]
    total_volume = sum(_safe_float(t.get("size")) * _safe_float(t.get("price")) for t in filled_trades)
    total_size = sum(_safe_float(t.get("size")) for t in filled_trades)
    avg_price = (total_volume / total_size) if total_size else 0.0

    markets = Counter(str(t.get("market") or t.get("condition_id") or "unknown") for t in filled_trades)
    top_markets = markets.most_common(8)

    recent_orders = sorted(
        orders,
        key=lambda o: (_parse_time(o.get("created_at") or o.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )[:10]

    recent_trades = sorted(
        filled_trades,
        key=lambda t: (_parse_time(t.get("timestamp") or t.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )[:10]

    balance_value = balance.get("balance") if isinstance(balance, dict) else None
    allowance_value = balance.get("allowance") if isinstance(balance, dict) else None

    notification_items = notifications if isinstance(notifications, list) else notifications.get("data", []) if isinstance(notifications, dict) else []
    notification_items = notification_items[:8]

    bars = "".join(
        f'<div class="bar-row"><div class="bar-label">{m[:20]}</div><div class="bar-track"><div class="bar-fill" style="width:{max(8, math.ceil((c / top_markets[0][1]) * 100)) if top_markets else 8}%"></div></div><div class="bar-value">{c}</div></div>'
        for m, c in top_markets
    ) or '<p class="muted">No trades yet.</p>'

    order_rows = "".join(
        f"<tr><td>{o.get('market','-')}</td><td>{o.get('side','-')}</td><td>{o.get('price','-')}</td><td>{o.get('size') or o.get('original_size') or '-'}</td><td>{o.get('status','-')}</td><td>{_format_dt(o.get('created_at') or o.get('timestamp'))}</td></tr>"
        for o in recent_orders
    ) or '<tr><td colspan="6" class="muted">No open orders</td></tr>'

    trade_rows = "".join(
        f"<tr><td>{t.get('market') or t.get('condition_id') or '-'}</td><td>{t.get('side','-')}</td><td>{t.get('price','-')}</td><td>{t.get('size','-')}</td><td>{_format_dt(t.get('timestamp') or t.get('created_at'))}</td></tr>"
        for t in recent_trades
    ) or '<tr><td colspan="5" class="muted">No trades found</td></tr>'

    notif_rows = "".join(
        f"<li><span>{n.get('message') or n.get('title') or str(n)}</span><small>{_format_dt(n.get('timestamp') or n.get('created_at'))}</small></li>"
        for n in notification_items
    ) or '<li><span class="muted">No notifications</span></li>'

    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Polymarket Trading Dashboard</title>
  <style>
    :root {{
      --bg:#0b1020; --panel:#121933; --panel-2:#182142; --text:#eef2ff; --muted:#99a3c4;
      --accent:#5eead4; --accent-2:#60a5fa; --green:#22c55e; --red:#ef4444; --border:#28345f;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter,system-ui,sans-serif; background:linear-gradient(180deg,#0a0f1d,#111933); color:var(--text); }}
    .wrap {{ max-width:1280px; margin:0 auto; padding:32px 20px 60px; }}
    .hero {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:24px; flex-wrap:wrap; }}
    .hero h1 {{ margin:0; font-size:34px; }}
    .hero p {{ margin:8px 0 0; color:var(--muted); }}
    .stamp {{ color:var(--muted); font-size:14px; background:rgba(255,255,255,.04); border:1px solid var(--border); padding:10px 14px; border-radius:12px; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; margin-bottom:16px; }}
    .card {{ background:rgba(18,25,51,.92); border:1px solid var(--border); border-radius:18px; padding:18px; box-shadow:0 8px 30px rgba(0,0,0,.25); }}
    .metric-label {{ color:var(--muted); font-size:13px; margin-bottom:8px; }}
    .metric-value {{ font-size:30px; font-weight:700; }}
    .split {{ display:grid; grid-template-columns:1.15fr .85fr; gap:16px; margin-top:16px; }}
    .table-wrap {{ overflow:auto; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ text-align:left; padding:12px 10px; border-bottom:1px solid rgba(255,255,255,.07); font-size:14px; }}
    th {{ color:#b8c2e0; font-weight:600; }}
    .section-title {{ margin:0 0 14px; font-size:18px; }}
    .bar-row {{ display:grid; grid-template-columns:160px 1fr 40px; gap:10px; align-items:center; margin-bottom:10px; }}
    .bar-label,.bar-value {{ font-size:13px; color:#dbe5ff; }}
    .bar-track {{ height:10px; background:#0f1530; border-radius:999px; overflow:hidden; border:1px solid rgba(255,255,255,.05); }}
    .bar-fill {{ height:100%; border-radius:999px; background:linear-gradient(90deg,var(--accent),var(--accent-2)); }}
    ul.notice-list {{ list-style:none; padding:0; margin:0; display:grid; gap:10px; }}
    .notice-list li {{ display:flex; justify-content:space-between; gap:12px; padding:12px; border:1px solid rgba(255,255,255,.06); border-radius:12px; background:rgba(255,255,255,.02); }}
    .notice-list small,.muted {{ color:var(--muted); }}
    .pill {{ display:inline-block; padding:6px 10px; border-radius:999px; background:rgba(94,234,212,.12); color:var(--accent); font-size:12px; border:1px solid rgba(94,234,212,.22); }}
    @media (max-width: 1024px) {{ .grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .split {{ grid-template-columns:1fr; }} }}
    @media (max-width: 640px) {{ .grid {{ grid-template-columns:1fr; }} .hero h1 {{ font-size:28px; }} .bar-row {{ grid-template-columns:110px 1fr 32px; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div>
        <span class="pill">Live account snapshot</span>
        <h1>Polymarket Trading Dashboard</h1>
        <p>Generated from your authenticated account data using py-clob-client.</p>
      </div>
      <div class="stamp">Updated: {generated_at}</div>
    </div>

    <section class="grid">
      <div class="card"><div class="metric-label">Open orders</div><div class="metric-value">{len(orders)}</div></div>
      <div class="card"><div class="metric-label">Buy exposure</div><div class="metric-value">{total_buy_size:.2f}</div></div>
      <div class="card"><div class="metric-label">Sell exposure</div><div class="metric-value">{total_sell_size:.2f}</div></div>
      <div class="card"><div class="metric-label">Avg trade price</div><div class="metric-value">{avg_price:.4f}</div></div>
    </section>

    <section class="grid">
      <div class="card"><div class="metric-label">Trade count</div><div class="metric-value">{len(filled_trades)}</div></div>
      <div class="card"><div class="metric-label">Trade notional</div><div class="metric-value">{total_volume:.2f}</div></div>
      <div class="card"><div class="metric-label">Collateral balance</div><div class="metric-value">{_safe_float(balance_value):.2f}</div></div>
      <div class="card"><div class="metric-label">Allowance</div><div class="metric-value">{_safe_float(allowance_value):.2f}</div></div>
    </section>

    <section class="split">
      <div class="card">
        <h2 class="section-title">Recent open orders</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Market</th><th>Side</th><th>Price</th><th>Size</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>{order_rows}</tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <h2 class="section-title">Top traded markets</h2>
        {bars}
      </div>
    </section>

    <section class="split">
      <div class="card">
        <h2 class="section-title">Recent trades</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Market</th><th>Side</th><th>Price</th><th>Size</th><th>Time</th></tr></thead>
            <tbody>{trade_rows}</tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <h2 class="section-title">Notifications</h2>
        <ul class="notice-list">{notif_rows}</ul>
      </div>
    </section>
  </div>
</body>
</html>'''


def main():
    load_dotenv()
    client = make_client()
    orders, trades, balance, notifications = fetch_all(client)
    html = build_dashboard(orders, trades, balance, notifications)

    output_path = os.getenv("DASHBOARD_OUTPUT", "dashboard.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard written to {output_path}")


if __name__ == "__main__":
    main()
