"""
dashboard.py — Australian Jobs Market Health Dashboard
Streamlit app reading from seek_data.db
"""

import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
import os

DB_PATH = "seek_data.db"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AU Jobs Market Pulse",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;700;800&display=swap');

  html, body, [class*="css"] {
    font-family: 'Syne', sans-serif;
    background: #0a0a0f;
    color: #e8e4d9;
  }

  .main { background: #0a0a0f; }

  .metric-card {
    background: #12121a;
    border: 1px solid #2a2a3a;
    border-radius: 4px;
    padding: 24px 20px;
    position: relative;
    overflow: hidden;
  }
  .metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #c8a84b, #e8c96d);
  }
  .metric-label {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #666;
    margin-bottom: 8px;
  }
  .metric-value {
    font-size: 36px;
    font-weight: 800;
    color: #e8e4d9;
    line-height: 1;
  }
  .metric-delta {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    margin-top: 6px;
  }
  .delta-up   { color: #4caf82; }
  .delta-down { color: #e05252; }
  .delta-flat { color: #666; }

  h1 { font-size: 48px !important; font-weight: 800 !important; letter-spacing: -1px; }
  h2 { font-size: 22px !important; font-weight: 700 !important; color: #c8a84b !important; letter-spacing: 0.05em; text-transform: uppercase; }
  h3 { font-size: 14px !important; font-weight: 400 !important; font-family: 'DM Mono', monospace !important; color: #666 !important; letter-spacing: 0.1em; }

  .stPlotlyChart { border: 1px solid #1e1e2a; border-radius: 4px; }
  footer { visibility: hidden; }
  #MainMenu { visibility: hidden; }

  .status-ok   { color: #4caf82; font-family: 'DM Mono', monospace; font-size: 12px; }
  .status-warn { color: #c8a84b; font-family: 'DM Mono', monospace; font-size: 12px; }
  .status-err  { color: #e05252; font-family: 'DM Mono', monospace; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

CHART_THEME = dict(
    paper_bgcolor="#0a0a0f",
    plot_bgcolor="#0a0a0f",
    font=dict(family="DM Mono", color="#888", size=11),
    xaxis=dict(gridcolor="#1e1e2a", linecolor="#2a2a3a", tickcolor="#444"),
    yaxis=dict(gridcolor="#1e1e2a", linecolor="#2a2a3a", tickcolor="#444"),
)
GOLD   = "#c8a84b"
GREEN  = "#4caf82"
RED    = "#e05252"
BLUE   = "#5b8af0"
PURPLE = "#9b6dff"

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data():
    if not os.path.exists(DB_PATH):
        return None, None, None

    con = sqlite3.connect(DB_PATH)

    snapshots = pd.read_sql("""
        SELECT snapshot_date, total_listings
        FROM snapshots
        ORDER BY snapshot_date
    """, con)

    listings = pd.read_sql("""
        SELECT snapshot_date, state, category, work_type,
               salary_min, salary_max, days_on_market, job_id
        FROM listings
        ORDER BY snapshot_date DESC
    """, con)

    weekly = pd.read_sql("""
        SELECT
            snapshot_date,
            COUNT(*)               AS total,
            COUNT(DISTINCT state)  AS states_active,
            AVG(days_on_market)    AS avg_dom,
            AVG(salary_min)        AS avg_sal_min,
            COUNT(DISTINCT category) AS categories
        FROM listings
        GROUP BY snapshot_date
        ORDER BY snapshot_date
    """, con)

    con.close()
    return snapshots, listings, weekly


def delta_html(current, previous, unit="", invert=False):
    if previous is None or previous == 0:
        return '<span class="delta-flat">— no prior data</span>'
    diff = current - previous
    pct  = (diff / previous) * 100
    if diff > 0:
        cls   = "delta-down" if invert else "delta-up"
        arrow = "▲"
    elif diff < 0:
        cls   = "delta-up" if invert else "delta-down"
        arrow = "▼"
    else:
        cls   = "delta-flat"
        arrow = "→"
    return f'<span class="{cls}">{arrow} {abs(pct):.1f}% vs last week</span>'


def metric_card(label, value, delta_html_str="", value_prefix=""):
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">{label}</div>
      <div class="metric-value">{value_prefix}{value}</div>
      <div class="metric-delta">{delta_html_str}</div>
    </div>
    """, unsafe_allow_html=True)


# ── App ───────────────────────────────────────────────────────────────────────
def main():
    # Header
    st.markdown("""
    <h1>AU Jobs Market<br><span style="color:#c8a84b">Pulse</span></h1>
    <h3>// SEEK DATA — WEEKLY SNAPSHOT TRACKER</h3>
    <br>
    """, unsafe_allow_html=True)

    snapshots, listings, weekly = load_data()

    # ── No data state ──
    if snapshots is None or snapshots.empty:
        st.markdown("""
        <div class="metric-card" style="text-align:center; padding: 60px;">
          <div style="font-size:48px; margin-bottom:16px;">📡</div>
          <div class="metric-value" style="font-size:24px; margin-bottom:12px;">No data yet</div>
          <div style="color:#666; font-family:'DM Mono',monospace; font-size:13px;">
            Run <code style="color:#c8a84b">python seeker.py</code> to pull your first weekly snapshot.<br><br>
            Data will appear here automatically after your first scrape.
          </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Latest snapshot ──
    latest = weekly.iloc[-1]
    prev   = weekly.iloc[-2] if len(weekly) > 1 else None

    last_date = latest["snapshot_date"]
    st.markdown(f'<p class="status-ok">● Last updated: {last_date} &nbsp;|&nbsp; {len(weekly)} weekly snapshots</p>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── KPI Row ──
    st.markdown("## Key Indicators")
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        total      = int(latest["total"])
        prev_total = int(prev["total"]) if prev is not None else None
        metric_card(
            "Active Listings",
            f"{total:,}",
            delta_html(total, prev_total)
        )

    with c2:
        dom      = latest["avg_dom"]
        prev_dom = prev["avg_dom"] if prev is not None else None
        metric_card(
            "Avg Days on Market",
            f"{dom:.1f}" if dom else "—",
            delta_html(dom or 0, prev_dom, invert=True) if dom else ""
        )

    with c3:
        sal      = latest["avg_sal_min"]
        prev_sal = prev["avg_sal_min"] if prev is not None else None
        metric_card(
            "Avg Salary Floor",
            f"{sal:,.0f}" if sal else "—",
            delta_html(sal or 0, prev_sal) if sal else "",
            value_prefix="$"
        )

    with c4:
        cats      = int(latest["categories"])
        prev_cats = int(prev["categories"]) if prev is not None else None
        metric_card(
            "Active Categories",
            f"{cats}",
            delta_html(cats, prev_cats)
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Listings trend ──
    st.markdown("## Weekly Listings Volume")

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=weekly["snapshot_date"],
        y=weekly["total"],
        mode="lines+markers",
        name="Total Listings",
        line=dict(color=GOLD, width=2),
        marker=dict(color=GOLD, size=7, symbol="circle"),
        fill="tozeroy",
        fillcolor="rgba(200, 168, 75, 0.06)"
    ))
    fig_trend.update_layout(
        **CHART_THEME,
        height=300,
        margin=dict(l=0, r=0, t=20, b=0),
        showlegend=False,
        hovermode="x unified"
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── State + Category breakdown ──
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("## By State")
        latest_listings = listings[listings["snapshot_date"] == last_date]
        state_counts = (
            latest_listings["state"]
            .value_counts()
            .reset_index()
        )
        state_counts.columns = ["state", "count"]
        state_counts = state_counts[state_counts["state"] != "Unknown"]

        if not state_counts.empty:
            fig_state = px.bar(
                state_counts.sort_values("count"),
                x="count", y="state",
                orientation="h",
                color="count",
                color_continuous_scale=[[0, "#1e2a1e"], [1, GREEN]],
            )
            fig_state.update_layout(
                **CHART_THEME,
                height=320,
                margin=dict(l=0, r=0, t=10, b=0),
                coloraxis_showscale=False,
                showlegend=False,
            )
            st.plotly_chart(fig_state, use_container_width=True)
        else:
            st.info("State data not yet available.")

    with col_right:
        st.markdown("## Top Categories")
        cat_counts = (
            latest_listings["category"]
            .value_counts()
            .head(12)
            .reset_index()
        )
        cat_counts.columns = ["category", "count"]
        cat_counts = cat_counts[cat_counts["category"] != ""]

        if not cat_counts.empty:
            fig_cat = px.bar(
                cat_counts.sort_values("count"),
                x="count", y="category",
                orientation="h",
                color="count",
                color_continuous_scale=[[0, "#1a1a2e"], [1, BLUE]],
            )
            fig_cat.update_layout(
                **CHART_THEME,
                height=320,
                margin=dict(l=0, r=0, t=10, b=0),
                coloraxis_showscale=False,
                showlegend=False,
            )
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("Category data not yet available.")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Days on market trend ──
    st.markdown("## Days on Market Trend")
    st.markdown("##### ↑ rising = employers struggling to fill roles &nbsp;|&nbsp; ↓ falling = fast hiring market")

    fig_dom = go.Figure()
    fig_dom.add_trace(go.Scatter(
        x=weekly["snapshot_date"],
        y=weekly["avg_dom"],
        mode="lines+markers",
        name="Avg Days on Market",
        line=dict(color=PURPLE, width=2),
        marker=dict(color=PURPLE, size=7),
        fill="tozeroy",
        fillcolor="rgba(155, 109, 255, 0.06)"
    ))
    fig_dom.update_layout(
        **CHART_THEME,
        height=260,
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
        hovermode="x unified"
    )
    st.plotly_chart(fig_dom, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Work type breakdown ──
    st.markdown("## Work Type Mix")
    wt_counts = (
        latest_listings["work_type"]
        .value_counts()
        .reset_index()
    )
    wt_counts.columns = ["work_type", "count"]
    wt_counts = wt_counts[wt_counts["work_type"] != ""]

    if not wt_counts.empty:
        fig_wt = px.pie(
            wt_counts,
            values="count",
            names="work_type",
            hole=0.6,
            color_discrete_sequence=[GOLD, GREEN, BLUE, PURPLE, RED]
        )
        fig_wt.update_layout(
            **CHART_THEME,
            height=280,
            margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", y=-0.1, font=dict(size=11))
        )
        st.plotly_chart(fig_wt, use_container_width=True)

    # ── Footer ──
    st.markdown("<br><br>")
    st.markdown(f"""
    <p style="font-family:'DM Mono',monospace; font-size:11px; color:#333; text-align:center;">
      AU JOBS MARKET PULSE &nbsp;·&nbsp; DATA SOURCE: SEEK AU VIA APIFY &nbsp;·&nbsp; {date.today()}
    </p>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
