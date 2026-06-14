# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import time
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from commodore_agent import CommodoreAgent  # noqa: F401
    BACKEND_ONLINE = True
except ImportError:
    BACKEND_ONLINE = False


st.set_page_config(
    page_title="NSR-Aegis | Passadiço Digital",
    page_icon="NSR",
    layout="wide",
    initial_sidebar_state="collapsed",
)


SCENARIOS: Dict[str, Dict[str, object]] = {
    "Navegação padrão": {
        "brief": "Trânsito assistido entre Rotterdam e Yokohama.",
        "gps": "VALIDADO",
        "gps_detail": "GPS, DGPS e INS congruentes",
        "gps_tone": "ok",
        "geopolitical": 36,
        "cyber": 18,
        "ice_m": 1.15,
        "wind_kt": 24,
        "sea_state": 4,
        "visibility_nm": 8.5,
        "speed_penalty": 0.0,
        "wrp_delta": "+12%",
        "primary_alert": "Sem alerta NAVAREA crítico.",
        "ais": "AIS classe A transmitindo em modo contínuo.",
    },
    "Bloqueio militar (Suez)": {
        "brief": "Interdição parcial do corredor Suez / Mar Vermelho.",
        "gps": "VALIDADO",
        "gps_detail": "Integridade de sinal preservada",
        "gps_tone": "warn",
        "geopolitical": 88,
        "cyber": 28,
        "ice_m": 1.10,
        "wind_kt": 27,
        "sea_state": 5,
        "visibility_nm": 7.0,
        "speed_penalty": 0.25,
        "wrp_delta": "+45%",
        "primary_alert": "Risco de guerra elevado no corredor Suez.",
        "ais": "AIS restrito a transmissão essencial em zona sensível.",
    },
    "Tempestade ártica extrema": {
        "brief": "Baixa polar, gelo espesso e visibilidade reduzida.",
        "gps": "DEGRADADO",
        "gps_detail": "DGPS intermitente; INS em ponderação maior",
        "gps_tone": "warn",
        "geopolitical": 44,
        "cyber": 24,
        "ice_m": 2.80,
        "wind_kt": 54,
        "sea_state": 8,
        "visibility_nm": 2.1,
        "speed_penalty": 1.65,
        "wrp_delta": "+18%",
        "primary_alert": "Risco estrutural por gelo e mar grosso.",
        "ais": "AIS transmitindo; aviso de baixa visibilidade ativo.",
    },
    "Ataque GPS spoofing": {
        "brief": "Divergência entre GNSS, radar costeiro e navegação inercial.",
        "gps": "SUSPEITO",
        "gps_detail": "Fix GNSS rejeitado; INS + radar em prioridade",
        "gps_tone": "crit",
        "geopolitical": 62,
        "cyber": 91,
        "ice_m": 1.20,
        "wind_kt": 31,
        "sea_state": 5,
        "visibility_nm": 6.4,
        "speed_penalty": 0.9,
        "wrp_delta": "+31%",
        "primary_alert": "Possível spoofing GNSS no setor leste.",
        "ais": "AIS validado contra radar e dados inerciais.",
    },
}


ROUTES: List[Dict[str, object]] = [
    {
        "id": "nsr",
        "name": "Rota Norte (NSR)",
        "distance_nm": 7000,
        "cruise_kn": 10.2,
        "war_risk": 0.010,
        "ice_risk": 0.040,
        "ice_exposure": 1.0,
        "fuel_base_tpd": 34,
        "waypoints": [(4.5, 51.9), (25.0, 70.0), (60.0, 74.5), (115.0, 73.0), (170.0, 63.0), (139.6, 35.4)],
    },
    {
        "id": "suez",
        "name": "Suez / Mar Vermelho",
        "distance_nm": 11200,
        "cruise_kn": 14.0,
        "war_risk": 0.050,
        "ice_risk": 0.000,
        "ice_exposure": 0.0,
        "fuel_base_tpd": 40,
        "waypoints": [(4.5, 51.9), (-5.4, 36.0), (32.5, 30.0), (43.2, 12.8), (80.0, 7.0), (103.8, 1.3), (139.6, 35.4)],
    },
    {
        "id": "cape",
        "name": "Cabo da Boa Esperança",
        "distance_nm": 14500,
        "cruise_kn": 14.0,
        "war_risk": 0.005,
        "ice_risk": 0.000,
        "ice_exposure": 0.0,
        "fuel_base_tpd": 42,
        "waypoints": [(4.5, 51.9), (-8.0, 18.0), (18.4, -34.4), (60.0, -25.0), (103.8, 1.3), (139.6, 35.4)],
    },
]


def inject_css() -> None:
    st.markdown(
        """
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Inter:wght@400;500;700;900&display=swap" rel="stylesheet">

        <style>
        :root {
            --bg: #080a08;
            --panel: #0e110e;
            --panel-2: #151815;
            --line: #272d27;
            --line-bright: #3a4238;
            --text: #d9e8d2;
            --muted: #7a9472;
            --muted-2: #5a6e55;
            --green: #2ec76a;
            --green-dim: rgba(46,199,106,.18);
            --teal: #1fc4b5;
            --teal-dim: rgba(31,196,181,.12);
            --amber: #e0a030;
            --amber-dim: rgba(224,160,48,.18);
            --red: #e04444;
            --red-dim: rgba(224,68,68,.18);
            --blue: #4a8fd4;
            --blue-dim: rgba(74,143,212,.15);
            --mono: "JetBrains Mono", Consolas, monospace;
            --sans: "Inter", "Segoe UI", Arial, sans-serif;
        }

        /* ─── Base ─────────────────────────────────────────────── */
        .stApp {
            background:
                repeating-linear-gradient(
                    0deg,
                    transparent,
                    transparent 3px,
                    rgba(0,0,0,.06) 3px,
                    rgba(0,0,0,.06) 4px
                ),
                linear-gradient(90deg, rgba(46,199,106,.028) 1px, transparent 1px),
                linear-gradient(180deg, rgba(46,199,106,.022) 1px, transparent 1px),
                var(--bg);
            background-size: auto, 40px 40px, 40px 40px;
            color: var(--text);
            font-family: var(--sans);
        }

        .block-container {
            max-width: 1480px;
            padding-top: 0;
            padding-bottom: 3.25rem;
        }

        header[data-testid="stHeader"],
        div[data-testid="stToolbar"],
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"],
        .stDeployButton,
        [data-testid="stAppDeployButton"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
        }

        section[data-testid="stSidebar"] {
            display: none !important;
        }

        h1, h2, h3, h4 {
            color: var(--text) !important;
        }

        /* ─── Cover / opening page ─────────────────────────────── */
        .hero-cover {
            min-height: calc(100vh - 104px);
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: clamp(86px, 13vh, 152px) 0 clamp(72px, 10vh, 128px);
            position: relative;
        }

        .hero-cover::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                radial-gradient(circle at 22% 24%, rgba(46,199,106,.10), transparent 30%),
                radial-gradient(circle at 82% 72%, rgba(74,143,212,.08), transparent 28%);
            pointer-events: none;
        }

        .hero-inner {
            position: relative;
            z-index: 1;
        }

        .hero-kicker {
            font-family: var(--mono);
            color: var(--teal);
            font-size: .72rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .16em;
            margin-bottom: 14px;
        }

        .hero-title {
            font-family: var(--mono);
            font-size: clamp(6rem, 13vw, 13rem);
            line-height: .82;
            font-weight: 800;
            color: var(--text);
            letter-spacing: -.07em;
            margin: 0;
            text-shadow: 0 0 42px rgba(46,199,106,.20);
        }

        .hero-copy {
            max-width: 1020px;
            margin-top: 34px;
            color: #a8bea2;
            font-family: var(--sans);
            font-size: clamp(1.08rem, 1.55vw, 1.42rem);
            line-height: 1.8;
        }

        .hero-rule {
            width: min(520px, 42vw);
            height: 1px;
            background: linear-gradient(90deg, var(--green), transparent);
            margin-top: 34px;
        }

        .hero-meta {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 34px;
            max-width: 1120px;
        }

        .hero-meta-cell {
            border-top: 2px solid var(--line-bright);
            padding-top: 12px;
        }

        .hero-meta-label {
            font-family: var(--mono);
            font-size: .65rem;
            color: var(--muted-2);
            text-transform: uppercase;
            letter-spacing: .12em;
            margin-bottom: 7px;
        }

        .hero-meta-value {
            font-family: var(--mono);
            color: var(--text);
            font-size: 1rem;
            font-weight: 800;
        }

        .pillar-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin-top: 26px;
        }

        .pillar-card {
            border: 1px solid var(--line);
            border-radius: 4px;
            background: rgba(14,17,14,.72);
            padding: 16px;
            min-height: 156px;
        }

        .pillar-index {
            font-family: var(--mono);
            color: var(--green);
            font-size: .68rem;
            font-weight: 800;
            margin-bottom: 14px;
        }

        .pillar-title {
            font-family: var(--mono);
            color: var(--text);
            font-size: .88rem;
            font-weight: 800;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: .08em;
        }

        .pillar-copy {
            color: var(--muted);
            font-size: .86rem;
            line-height: 1.5;
        }

        .dashboard-spacer { height: 22px; }

        /* ─── Header ──────────────────────────────────────────── */
        .app-header {
            border: 1px solid var(--line-bright);
            border-top: 3px solid var(--green);
            border-radius: 4px;
            padding: 18px 22px 16px;
            background: linear-gradient(135deg, rgba(14,17,14,.98), rgba(8,10,8,.98));
            margin-bottom: 14px;
            position: relative;
            overflow: hidden;
        }

        .app-header::before {
            content: "";
            position: absolute;
            inset: 0;
            background: radial-gradient(ellipse 60% 100% at 0% 50%, rgba(46,199,106,.06), transparent);
            pointer-events: none;
        }

        .header-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.5fr) minmax(300px, .8fr);
            gap: 22px;
            align-items: end;
        }

        .eyebrow {
            font-family: var(--mono);
            color: var(--green);
            font-size: .70rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .12em;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .eyebrow::before {
            content: "";
            display: inline-block;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--green);
            box-shadow: 0 0 6px var(--green);
            animation: pulse-dot 2s ease-in-out infinite;
        }

        @keyframes pulse-dot {
            0%, 100% { opacity: 1; box-shadow: 0 0 6px var(--green); }
            50% { opacity: .4; box-shadow: 0 0 2px var(--green); }
        }

        .title {
            font-family: var(--mono);
            font-size: clamp(2.2rem, 4vw, 3.6rem);
            line-height: .92;
            font-weight: 800;
            margin: 0;
            letter-spacing: -.03em;
            color: var(--text) !important;
            text-shadow: 0 0 30px rgba(46,199,106,.25);
        }

        .subtitle {
            font-family: var(--sans);
            color: var(--muted);
            font-size: .92rem;
            max-width: 860px;
            margin-top: 12px;
            line-height: 1.55;
        }

        .subtitle strong { color: var(--text); }

        /* ─── Header meta grid ────────────────────────────────── */
        .header-meta {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 7px;
        }

        .meta-cell {
            border: 1px solid var(--line);
            border-radius: 4px;
            padding: 10px 13px;
            background: rgba(8,10,8,.85);
        }

        .meta-label {
            font-family: var(--mono);
            color: var(--muted-2);
            font-size: .64rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .1em;
            line-height: 1;
        }

        .meta-value {
            font-family: var(--mono);
            color: var(--text);
            font-size: .95rem;
            font-weight: 700;
            margin-top: 6px;
        }

        /* ─── KPI cards ───────────────────────────────────────── */
        .metric-card {
            border: 1px solid var(--line);
            border-radius: 4px;
            padding: 14px 15px;
            background: var(--panel);
            min-height: 112px;
            border-left: 3px solid transparent;
            position: relative;
            overflow: hidden;
        }

        .metric-card::after {
            content: "";
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(46,199,106,.4), transparent);
        }

        .metric-card.ok   { border-left-color: var(--green); background: linear-gradient(135deg, rgba(46,199,106,.06) 0%, var(--panel) 60%); }
        .metric-card.warn { border-left-color: var(--amber); background: linear-gradient(135deg, rgba(224,160,48,.06) 0%, var(--panel) 60%); }
        .metric-card.crit { border-left-color: var(--red);   background: linear-gradient(135deg, rgba(224,68,68,.09) 0%, var(--panel) 60%); }
        .metric-card.neutral { border-left-color: var(--blue); background: linear-gradient(135deg, rgba(74,143,212,.06) 0%, var(--panel) 60%); }

        .metric-label {
            font-family: var(--mono);
            color: var(--muted-2);
            font-size: .65rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .1em;
            line-height: 1;
        }

        .metric-value {
            font-family: var(--mono);
            color: var(--text);
            font-size: 1.4rem;
            font-weight: 800;
            line-height: 1.05;
            margin-top: 9px;
            overflow-wrap: anywhere;
        }

        .metric-caption {
            font-family: var(--sans);
            color: var(--muted);
            font-size: .75rem;
            line-height: 1.3;
            margin-top: 7px;
        }

        /* ─── Section labels ──────────────────────────────────── */
        .section-label {
            font-family: var(--mono);
            color: var(--teal);
            font-size: .70rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .12em;
            margin: 6px 0 10px;
            padding-bottom: 6px;
            border-bottom: 1px solid var(--line);
        }

        /* ─── Decision / panel notes ──────────────────────────── */
        .decision {
            border: 1px solid var(--line);
            border-left: 3px solid var(--green);
            border-radius: 4px;
            background: var(--panel);
            padding: 13px 15px;
            margin-bottom: 11px;
        }

        .decision.warn { border-left-color: var(--amber); }
        .decision.crit {
            border-left-color: var(--red);
            animation: crit-pulse 3s ease-in-out infinite;
        }

        @keyframes crit-pulse {
            0%, 100% { box-shadow: 0 0 0 0 transparent; }
            50% { box-shadow: 0 0 12px 1px rgba(224,68,68,.2); }
        }

        .decision-title {
            font-family: var(--mono);
            color: var(--text);
            font-size: .92rem;
            font-weight: 700;
            margin-bottom: 6px;
        }

        .decision-copy {
            font-family: var(--sans);
            color: var(--muted);
            font-size: .86rem;
            line-height: 1.5;
        }

        /* ─── Log lines ───────────────────────────────────────── */
        .log-line {
            border-left: 2px solid var(--line-bright);
            padding: 6px 11px;
            margin: 5px 0;
            background: rgba(8,10,8,.7);
            color: var(--muted);
            font-family: var(--mono);
            font-size: .78rem;
            line-height: 1.45;
            border-radius: 0 3px 3px 0;
        }

        .log-line.ok   { border-left-color: var(--green); color: #b4e8c4; }
        .log-line.warn { border-left-color: var(--amber); color: #f2dfa8; }
        .log-line.crit { border-left-color: var(--red);   color: #f5b8b8; }

        /* ─── Timeline (Audit) ────────────────────────────────── */
        .timeline { position: relative; padding-left: 28px; }
        .timeline::before {
            content: "";
            position: absolute;
            left: 8px; top: 0; bottom: 0;
            width: 1px;
            background: var(--line-bright);
        }
        .tl-item { position: relative; margin-bottom: 14px; }
        .tl-dot {
            position: absolute;
            left: -24px;
            top: 4px;
            width: 9px; height: 9px;
            border-radius: 50%;
            background: var(--green);
            box-shadow: 0 0 6px rgba(46,199,106,.5);
        }
        .tl-dot.warn { background: var(--amber); box-shadow: 0 0 6px rgba(224,160,48,.5); }
        .tl-dot.crit { background: var(--red);   box-shadow: 0 0 6px rgba(224,68,68,.5); }
        .tl-step {
            font-family: var(--mono);
            font-size: .65rem;
            font-weight: 700;
            color: var(--muted-2);
            text-transform: uppercase;
            letter-spacing: .1em;
            margin-bottom: 2px;
        }
        .tl-text {
            font-family: var(--sans);
            font-size: .84rem;
            color: var(--muted);
            line-height: 1.45;
        }
        .tl-text strong { color: var(--text); }

        /* ─── Mission clock strip ─────────────────────────────── */
        .clock-strip {
            display: flex;
            align-items: center;
            gap: 24px;
            padding: 7px 14px;
            background: rgba(0,0,0,.55);
            border: 1px solid var(--line);
            border-radius: 4px;
            font-family: var(--mono);
            font-size: .72rem;
            color: var(--muted);
            margin-bottom: 12px;
            flex-wrap: wrap;
        }
        .clock-item { display: flex; align-items: center; gap: 6px; }
        .clock-key {
            color: var(--muted-2);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .09em;
        }
        .clock-val { color: var(--text); font-weight: 700; }
        .clock-sep { color: var(--line-bright); }

        /* ─── Threat gauge (sidebar) ──────────────────────────── */
        .threat-bar-wrap {
            margin: 4px 0 14px;
            font-family: var(--mono);
        }
        .threat-label {
            font-size: .65rem; color: var(--muted-2); text-transform: uppercase;
            letter-spacing: .1em; margin-bottom: 5px;
        }
        .threat-bar-outer {
            height: 8px; border-radius: 2px;
            background: rgba(255,255,255,.07);
            overflow: hidden;
        }
        .threat-bar-inner {
            height: 100%; border-radius: 2px;
            transition: width .4s ease;
        }

        /* ─── Tabs ────────────────────────────────────────────── */
        .stTabs [data-baseweb="tab-list"] {
            gap: 3px;
            border-bottom: 1px solid var(--line-bright);
            padding-bottom: 0;
            overflow-x: auto;
            overflow-y: hidden;
            flex-wrap: nowrap;
        }

        .stTabs [data-baseweb="tab-panel"] {
            padding-top: 1.35rem;
        }

        .stTabs [data-baseweb="tab"] {
            background: #0b0d0b;
            border: 1px solid var(--line);
            border-bottom: 0;
            border-radius: 4px 4px 0 0;
            padding: 9px 18px;
            color: var(--muted);
            font-family: var(--mono);
            font-size: .74rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .08em;
            flex-shrink: 0;
        }

        .stTabs [aria-selected="true"] {
            background: var(--panel-2);
            color: var(--green) !important;
            border-color: var(--line-bright);
        }

        /* ─── Buttons ─────────────────────────────────────────── */
        .stButton > button {
            border-radius: 3px;
            border: 1px solid #5a7a50;
            background: rgba(46,199,106,.12);
            color: var(--green);
            font-family: var(--mono);
            font-size: .75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .08em;
            min-height: 40px;
            width: 100%;
            transition: all .15s ease;
        }

        .stButton > button:hover {
            border-color: var(--green);
            background: rgba(46,199,106,.22);
            color: #a8f5c4;
        }

        /* ─── DataFrames ──────────────────────────────────────── */
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 4px;
            overflow: hidden;
        }

        .table-shell {
            border: 1px solid var(--line);
            border-radius: 4px;
            overflow: auto;
            background: #070907;
            margin: 8px 0 20px;
        }

        table.dark-table {
            width: 100%;
            border-collapse: collapse;
            font-family: var(--sans);
            font-size: .86rem;
            color: var(--text);
        }

        table.dark-table thead th {
            position: sticky;
            top: 0;
            z-index: 2;
            background: #11150f;
            color: #9fb897;
            font-family: var(--mono);
            font-size: .66rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .08em;
            padding: 12px 13px;
            border-bottom: 1px solid var(--line-bright);
            text-align: left;
            white-space: nowrap;
        }

        table.dark-table tbody td {
            background: #080b08;
            color: #d9e8d2;
            padding: 12px 13px;
            border-bottom: 1px solid rgba(58,66,56,.55);
            vertical-align: top;
        }

        table.dark-table tbody tr:nth-child(even) td {
            background: #0d100c;
        }

        table.dark-table tbody tr:hover td {
            background: rgba(46,199,106,.07);
        }

        /* ─── Metrics ─────────────────────────────────────────── */
        [data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 4px;
            padding: 12px 14px;
        }

        [data-testid="stMetricLabel"] { font-family: var(--mono); font-size: .7rem; }
        [data-testid="stMetricValue"] { font-family: var(--mono); }

        footer, #MainMenu { visibility: hidden; }

        /* ─── Selectbox / Sliders ─────────────────────────────── */
        .stSelectbox > label, .stSlider > label, .stCheckbox > label {
            font-family: var(--mono);
            font-size: .72rem;
            color: var(--muted) !important;
            text-transform: uppercase;
            letter-spacing: .07em;
        }

        /* ─── Sidebar title ───────────────────────────────────── */
        .sidebar-brand {
            font-family: var(--mono);
            font-size: 1.35rem;
            font-weight: 800;
            color: var(--green);
            letter-spacing: -.02em;
            text-shadow: 0 0 20px rgba(46,199,106,.4);
            padding: 4px 0 2px;
        }
        .sidebar-sub {
            font-family: var(--mono);
            font-size: .64rem;
            color: var(--muted-2);
            text-transform: uppercase;
            letter-spacing: .12em;
            margin-bottom: 12px;
        }

        @media (max-width: 900px) {
            .header-grid { grid-template-columns: 1fr; }
            .header-meta { grid-template-columns: 1fr; }
            .clock-strip { gap: 12px; }
            .hero-meta, .pillar-grid { grid-template-columns: 1fr; }
            .hero-title { font-size: clamp(3.4rem, 18vw, 5rem); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ─── Utility helpers ─────────────────────────────────────────────────────────

def risk_tone(value: float) -> str:
    if value >= 78:
        return "crit"
    if value >= 55:
        return "warn"
    return "ok"


def money_m(value: float) -> str:
    return f"US$ {value / 1_000_000:.2f}M"


def metric_card(label: str, value: str, caption: str, tone: str = "neutral") -> None:
    st.markdown(
        f"""
        <div class="metric-card {tone}">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-caption">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def panel_note(title: str, copy: str, tone: str = "ok") -> None:
    st.markdown(
        f"""
        <div class="decision {tone}">
            <div class="decision-title">{title}</div>
            <div class="decision-copy">{copy}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def log_line(text: str, tone: str = "neutral") -> None:
    st.markdown(f'<div class="log-line {tone}">{text}</div>', unsafe_allow_html=True)


def dark_table(df: pd.DataFrame, height: int | None = None) -> None:
    style = f' style="max-height:{height}px;"' if height else ""
    html_table = df.to_html(index=False, border=0, classes="dark-table", escape=True)
    st.markdown(f'<div class="table-shell"{style}>{html_table}</div>', unsafe_allow_html=True)


def threat_bar(label: str, value: float) -> None:
    """Thin progress bar for sidebar threat indicators."""
    if value >= 78:
        color = "#e04444"
    elif value >= 55:
        color = "#e0a030"
    else:
        color = "#2ec76a"
    st.markdown(
        f"""
        <div class="threat-bar-wrap">
            <div class="threat-label">{label} — <strong style="color:{color}">{value:.0f}/100</strong></div>
            <div class="threat-bar-outer">
                <div class="threat-bar-inner" style="width:{value}%;background:{color};"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def timeline_item(step: str, text: str, tone: str = "ok") -> None:
    st.markdown(
        f"""
        <div class="tl-item">
            <div class="tl-dot {tone}"></div>
            <div class="tl-step">{step}</div>
            <div class="tl-text">{text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def chart_layout(fig: go.Figure, height: int, showlegend: bool = False) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0b0d0b",
        font=dict(family="JetBrains Mono, Consolas, monospace", color="#7a9472", size=11),
        margin=dict(l=18, r=18, t=28, b=18),
        showlegend=showlegend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.22,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(0,0,0,0)",
            font=dict(color="#7a9472", size=10),
        ),
    )
    return fig


# ─── Route calculation ───────────────────────────────────────────────────────

def calculate_routes(
    scenario_name: str,
    rpm_target: int,
    fuel_price: float,
    ship_value: float,
    conservative_veto: bool,
) -> pd.DataFrame:
    cfg = SCENARIOS[scenario_name]
    rows = []
    rpm_adjustment = (rpm_target - 85) * 0.025
    veto_limit = 66 if conservative_veto else 56

    for route in ROUTES:
        speed = float(route["cruise_kn"]) + rpm_adjustment - float(cfg["speed_penalty"])
        war_risk = float(route["war_risk"])
        ice_risk = float(route["ice_risk"])
        cyber_penalty = 0.0

        if route["id"] == "suez" and scenario_name == "Bloqueio militar (Suez)":
            war_risk += 0.065
            speed -= 0.7
        if route["id"] == "nsr" and scenario_name == "Tempestade ártica extrema":
            ice_risk += 0.055
            speed -= 1.4
        if scenario_name == "Ataque GPS spoofing":
            cyber_penalty = 14.0
            speed -= 0.45

        speed = max(6.2, speed)
        days = float(route["distance_nm"]) / (speed * 24.0)
        daily_fuel = float(route["fuel_base_tpd"]) * ((speed / float(route["cruise_kn"])) ** 3)
        fuel_cost = daily_fuel * days * fuel_price
        operating_cost = days * 45_000
        risk_cost = 20_000 + ship_value * (war_risk + ice_risk)
        total_cost = fuel_cost + operating_cost + risk_cost

        ice_load = float(route["ice_exposure"]) * float(cfg["ice_m"]) * 18.5
        sea_load = max(0.0, float(cfg["sea_state"]) - 4.0) * 4.4
        geopolitical_load = float(cfg["geopolitical"]) * (0.25 if route["id"] == "suez" else 0.10)
        safety = 100.0 - ice_load - sea_load - geopolitical_load - cyber_penalty
        safety = float(np.clip(safety, 18, 99))

        if safety < veto_limit:
            status = "Vetada"
        elif safety < veto_limit + 12:
            status = "Restrita"
        else:
            status = "Liberada"

        score = (total_cost / 1_000_000) + (100 - safety) * 0.075 + days * 0.012
        if status == "Vetada":
            score += 100

        rows.append({
            "id": route["id"],
            "Rota": route["name"],
            "Distância (NM)": int(route["distance_nm"]),
            "Velocidade (kn)": speed,
            "Dias": days,
            "TVC": total_cost,
            "Prêmio de risco": risk_cost,
            "Índice de segurança": safety,
            "Status": status,
            "Score": score,
        })

    df = pd.DataFrame(rows)
    return df.sort_values(["Score", "TVC"], ascending=True).reset_index(drop=True)


# ─── Charts ──────────────────────────────────────────────────────────────────

def build_geo_chart(best_route_id: str) -> go.Figure:
    colors = {"nsr": "#2ec76a", "suez": "#e0a030", "cape": "#4a8fd4"}
    fig = go.Figure()

    for route in ROUTES:
        lons = [point[0] for point in route["waypoints"]]
        lats = [point[1] for point in route["waypoints"]]
        selected = route["id"] == best_route_id
        fig.add_trace(
            go.Scattergeo(
                lon=lons, lat=lats,
                mode="lines",
                name=str(route["name"]),
                line=dict(color=colors[str(route["id"])], width=4 if selected else 1.5,
                          dash="solid" if selected else "dot"),
                opacity=1.0 if selected else 0.38,
            )
        )

    fleet = pd.DataFrame({
        "name": ["NSR-Aegis", "Ice Escort 04", "VLCC contact", "Security patrol"],
        "lon": [25.0, 58.0, 84.0, 43.2],
        "lat": [70.5, 73.6, 10.0, 13.0],
        "color": ["#d9e8d2", "#2ec76a", "#e0a030", "#e04444"],
        "size": [13, 10, 9, 9],
    })
    fig.add_trace(
        go.Scattergeo(
            lon=fleet["lon"], lat=fleet["lat"],
            text=fleet["name"],
            mode="markers+text",
            textposition="top center",
            name="Contatos",
            marker=dict(size=fleet["size"], color=fleet["color"], line=dict(width=1, color="#080a08")),
            textfont=dict(color="#d9e8d2", size=10, family="JetBrains Mono"),
        )
    )

    fig.update_geos(
        projection_type="natural earth",
        bgcolor="#080a08",
        showland=True, landcolor="#1a1d19",
        showocean=True, oceancolor="#080d0c",
        showcountries=True, countrycolor="#2e3629",
        coastlinecolor="#3d4438",
        showframe=False,
        lataxis_showgrid=True, lonaxis_showgrid=True,
        lataxis_gridcolor="rgba(46,199,106,.08)",
        lonaxis_gridcolor="rgba(46,199,106,.08)",
    )
    chart_layout(fig, height=460, showlegend=True)
    fig.update_layout(
        paper_bgcolor="#080a08",
        plot_bgcolor="#080a08",
        geo=dict(bgcolor="#080a08"),
        margin=dict(l=0, r=0, t=8, b=4),
    )
    return fig


def build_cost_chart(route_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    bar_colors = []
    for status in route_df["Status"]:
        if status == "Vetada":
            bar_colors.append("#e04444")
        elif status == "Restrita":
            bar_colors.append("#e0a030")
        else:
            bar_colors.append("#2ec76a")

    fig.add_trace(
        go.Bar(
            y=route_df["Rota"],
            x=route_df["TVC"] / 1_000_000,
            orientation="h",
            marker_color=bar_colors,
            marker_line=dict(width=0),
            text=[money_m(v) for v in route_df["TVC"]],
            textfont=dict(family="JetBrains Mono", size=11),
            textposition="auto",
            hovertemplate="%{y}<br>TVC: US$ %{x:.2f}M<extra></extra>",
        )
    )
    fig.update_xaxes(title="Custo total de viagem (US$ M)", gridcolor="rgba(46,199,106,.08)",
                     color="#7a9472", title_font=dict(size=11))
    fig.update_yaxes(title="", autorange="reversed", gridcolor="rgba(0,0,0,0)", color="#7a9472")
    return chart_layout(fig, height=240)


def build_radar_chart(scenario_name: str) -> go.Figure:
    targets = pd.DataFrame({
        "r": [0.0, 3.8, 6.6, 8.2, 2.4],
        "theta": [0, 42, 118, 224, 315],
        "name": ["Próprio navio", "Iceberg A", "Cargueiro VLCC", "Frente meteorológica", "Contato sem AIS"],
        "color": ["#d9e8d2", "#2ec76a", "#7a9472", "#4a8fd4", "#e0a030"],
        "size": [15, 11, 10, 9, 13],
    })

    if scenario_name in {"Ataque GPS spoofing", "Bloqueio militar (Suez)"}:
        targets.loc[4, "color"] = "#e04444"
        targets.loc[4, "r"] = 1.9

    fig = go.Figure()

    # Sweep line effect (simulated radar sweep)
    theta_sweep = list(range(0, 360, 2))
    r_sweep = [10.5] * len(theta_sweep)
    sweep_opacity = [max(0, 0.35 - abs(i - 90) / 90 * 0.35) for i in theta_sweep]

    fig.add_trace(
        go.Scatterpolar(
            r=targets["r"],
            theta=targets["theta"],
            mode="markers+text",
            text=targets["name"],
            textposition=["bottom center", "top right", "top left", "bottom left", "bottom right"],
            marker=dict(
                color=list(targets["color"]),
                size=list(targets["size"]),
                line=dict(color="#080a08", width=1.5),
            ),
            hovertemplate="%{text}<br>Distância: %{r:.1f} NM<br>Marcação: %{theta}°<extra></extra>",
            showlegend=False,
            textfont=dict(family="JetBrains Mono", size=9, color="#7a9472"),
        )
    )
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                range=[0, 10],
                gridcolor="rgba(46,199,106,.15)",
                tickfont=dict(color="#7a9472", family="JetBrains Mono", size=9),
                linecolor="rgba(46,199,106,.2)",
            ),
            angularaxis=dict(
                rotation=90,
                direction="clockwise",
                gridcolor="rgba(46,199,106,.12)",
                tickfont=dict(color="#7a9472", family="JetBrains Mono", size=9),
                linecolor="rgba(46,199,106,.2)",
            ),
            bgcolor="#070a07",
        )
    )
    return chart_layout(fig, height=390)


def build_engine_chart(rpm_target: int) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=rpm_target,
            number={"font": {"color": "#d9e8d2", "size": 36, "family": "JetBrains Mono"}, "suffix": " rpm"},
            title={"text": "MOTOR PRINCIPAL", "font": {"color": "#7a9472", "size": 11, "family": "JetBrains Mono"}},
            gauge={
                "axis": {"range": [0, 120], "tickcolor": "#7a9472", "tickwidth": 1,
                         "tickfont": dict(family="JetBrains Mono", size=9)},
                "bar": {"color": "#2ec76a", "thickness": 0.22},
                "bgcolor": "#080a08",
                "borderwidth": 1,
                "bordercolor": "#272d27",
                "steps": [
                    {"range": [0, 55],   "color": "#0e120e"},
                    {"range": [55, 95],  "color": "#112211"},
                    {"range": [95, 120], "color": "#251208"},
                ],
                "threshold": {"line": {"color": "#e04444", "width": 3}, "thickness": 0.8, "value": 106},
            },
        )
    )
    return chart_layout(fig, height=230)


def build_fatigue_chart(scenario_name: str) -> go.Figure:
    cfg = SCENARIOS[scenario_name]
    rng = np.random.default_rng(42 + int(float(cfg["sea_state"]) * 10))
    timestamps = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=72, freq="min")
    mean_load = 1.15 + float(cfg["sea_state"]) * 0.16 + float(cfg["ice_m"]) * 0.20
    impacts = rng.normal(mean_load, 0.22 + float(cfg["sea_state"]) * 0.035, len(timestamps))
    impacts = np.clip(impacts, 0.55, None)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=timestamps, y=impacts,
            mode="lines",
            line=dict(color="#4a8fd4", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(74,143,212,.12)",
            name="Carga dinâmica",
        )
    )
    # Running mean
    window = 10
    rolling_mean = np.convolve(impacts, np.ones(window) / window, mode="valid")
    fig.add_trace(
        go.Scatter(
            x=timestamps[window - 1:], y=rolling_mean,
            mode="lines",
            line=dict(color="#2ec76a", width=1.5, dash="dash"),
            name="Média móvel",
        )
    )
    fig.add_hline(y=3.5, line_dash="dot", line_color="#e04444", line_width=1.5,
                  annotation_text="LIMITE PC4", annotation_font=dict(family="JetBrains Mono", size=9, color="#e04444"))
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(title="g equiv.", gridcolor="rgba(46,199,106,.08)", color="#7a9472",
                     title_font=dict(size=10))
    return chart_layout(fig, height=270, showlegend=True)


def build_stability_chart(pitch: float, roll: float) -> go.Figure:
    x = np.linspace(-1, 1, 80)
    y = math.tan(math.radians(roll)) * x
    color = "#e04444" if abs(roll) > 10 else "#2ec76a"
    fig = go.Figure()
    # Safe envelope
    theta_env = np.linspace(0, 2 * np.pi, 200)
    fig.add_trace(go.Scatter(
        x=np.cos(theta_env) * 0.9, y=np.sin(theta_env) * 0.45,
        mode="lines", line=dict(color="#272d27", width=1, dash="dot"),
        showlegend=False, hoverinfo="skip"
    ))
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines",
                              line=dict(color=color, width=5), name="Banda"))
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers",
                              marker=dict(size=14, color="#d9e8d2", line=dict(color=color, width=2)),
                              name="Centro de gravidade"))
    fig.update_xaxes(range=[-1, 1], showticklabels=False, zeroline=True,
                     zerolinecolor="#272d27", gridcolor="rgba(46,199,106,.05)")
    fig.update_yaxes(range=[-.6, .6], showticklabels=False, zeroline=True,
                     zerolinecolor="#272d27", gridcolor="rgba(46,199,106,.05)")
    fig.add_annotation(x=-0.94, y=0.5, text=f"Pitch {pitch:+.1f}°",
                       showarrow=False, font=dict(color="#7a9472", family="JetBrains Mono", size=9))
    fig.add_annotation(x=0.94, y=0.5, text=f"Band {roll:+.1f}°",
                       showarrow=False, font=dict(color=color, family="JetBrains Mono", size=9),
                       xanchor="right")
    return chart_layout(fig, height=215)


def build_ukc_chart(ukc_m: float) -> go.Figure:
    """Under-Keel Clearance time series."""
    rng = np.random.default_rng(77)
    t = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=48, freq="min")
    base = rng.normal(ukc_m, 1.2, len(t))
    base = np.clip(base, 5, 80)

    fig = go.Figure()
    alarm_color = "#e04444" if ukc_m < 12 else "#e0a030" if ukc_m < 18 else "#2ec76a"
    fig.add_trace(go.Scatter(
        x=t, y=base, mode="lines",
        line=dict(color=alarm_color, width=1.5),
        fill="tozeroy", fillcolor=f"rgba{tuple(int(alarm_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (.10,)}",
        name="UKC",
    ))
    fig.add_hline(y=8, line_dash="dot", line_color="#e04444", line_width=1.5,
                  annotation_text="MÍNIMO 8m", annotation_font=dict(family="JetBrains Mono", size=9, color="#e04444"))
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(title="UKC (m)", gridcolor="rgba(46,199,106,.08)", color="#7a9472",
                     title_font=dict(size=10))
    return chart_layout(fig, height=195)


def build_fuel_efficiency_chart(route_df: pd.DataFrame) -> go.Figure:
    """Fuel consumption vs speed curve for each route."""
    fig = go.Figure()
    colors = {"nsr": "#2ec76a", "suez": "#e0a030", "cape": "#4a8fd4"}
    speed_range = np.linspace(6, 18, 80)

    for route in ROUTES:
        base_tpd = float(route["fuel_base_tpd"])
        cruise = float(route["cruise_kn"])
        color = colors[str(route["id"])]
        consumption = base_tpd * ((speed_range / cruise) ** 3)
        fig.add_trace(go.Scatter(
            x=speed_range, y=consumption,
            mode="lines",
            name=str(route["name"]),
            line=dict(color=color, width=2),
        ))

    # Mark current operating speed for each route
    for _, row in route_df.iterrows():
        route_obj = next((r for r in ROUTES if r["id"] == row["id"]), None)
        if route_obj:
            base_tpd = float(route_obj["fuel_base_tpd"])
            cruise = float(route_obj["cruise_kn"])
            current_speed = float(row["Velocidade (kn)"])
            current_consumption = base_tpd * ((current_speed / cruise) ** 3)
            color = colors[str(row["id"])]
            fig.add_trace(go.Scatter(
                x=[current_speed], y=[current_consumption],
                mode="markers",
                name=f"{row['Rota']} — atual",
                marker=dict(size=10, color=color, line=dict(color="#d9e8d2", width=1.5)),
                showlegend=False,
                hovertemplate=f"<b>{row['Rota']}</b><br>Velocidade: %{{x:.1f}} kn<br>Consumo: %{{y:.1f}} t/dia<extra></extra>",
            ))

    fig.update_xaxes(title="Velocidade (nós)", gridcolor="rgba(46,199,106,.08)", color="#7a9472",
                     title_font=dict(size=11))
    fig.update_yaxes(title="Consumo VLSFO (t/dia)", gridcolor="rgba(46,199,106,.08)", color="#7a9472",
                     title_font=dict(size=11))
    return chart_layout(fig, height=310, showlegend=True)


def build_cost_breakdown_chart(route_df: pd.DataFrame, fuel_price: float, ship_value: float) -> go.Figure:
    """Stacked bar: fuel vs OPEX vs risk premium per route."""
    fig = go.Figure()
    routes_names = list(route_df["Rota"])

    # Reconstruct components
    fuel_costs, opex_costs, risk_costs = [], [], []
    for _, row in route_df.iterrows():
        route_obj = next((r for r in ROUTES if r["id"] == row["id"]), None)
        if route_obj:
            days = float(row["Dias"])
            speed = float(row["Velocidade (kn)"])
            cruise = float(route_obj["cruise_kn"])
            base_tpd = float(route_obj["fuel_base_tpd"])
            daily_fuel = base_tpd * ((speed / cruise) ** 3)
            fuel_costs.append(daily_fuel * days * fuel_price / 1e6)
            opex_costs.append(days * 45_000 / 1e6)
            risk_costs.append(float(row["Prêmio de risco"]) / 1e6)

    fig.add_trace(go.Bar(y=routes_names, x=fuel_costs, name="Combustível",
                          orientation="h", marker_color="#4a8fd4"))
    fig.add_trace(go.Bar(y=routes_names, x=opex_costs, name="OPEX (charter)",
                          orientation="h", marker_color="#7a9472"))
    fig.add_trace(go.Bar(y=routes_names, x=risk_costs, name="Prêmio de risco",
                          orientation="h", marker_color="#e0a030"))

    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Custo (US$ M)", gridcolor="rgba(46,199,106,.08)", color="#7a9472",
                     title_font=dict(size=11))
    fig.update_yaxes(autorange="reversed", color="#7a9472")
    return chart_layout(fig, height=240, showlegend=True)


def build_co2_chart(route_df: pd.DataFrame) -> go.Figure:
    """CO2 equivalent emissions per route (IMO 2023 CII context)."""
    fig = go.Figure()
    co2_factor = 3.206  # tons CO2 per ton VLSFO
    co2_data = []
    for _, row in route_df.iterrows():
        route_obj = next((r for r in ROUTES if r["id"] == row["id"]), None)
        if route_obj:
            days = float(row["Dias"])
            speed = float(row["Velocidade (kn)"])
            cruise = float(route_obj["cruise_kn"])
            base_tpd = float(route_obj["fuel_base_tpd"])
            daily_fuel = base_tpd * ((speed / cruise) ** 3)
            total_fuel = daily_fuel * days
            co2_data.append(total_fuel * co2_factor)

    bar_colors = ["#2ec76a" if s != "Vetada" else "#e04444" for s in route_df["Status"]]
    fig.add_trace(go.Bar(
        y=list(route_df["Rota"]), x=co2_data,
        orientation="h",
        marker_color=bar_colors,
        text=[f"{v:.0f} t" for v in co2_data],
        textfont=dict(family="JetBrains Mono", size=10),
        textposition="auto",
        hovertemplate="%{y}<br>CO₂: %{x:.0f} t<extra></extra>",
    ))
    fig.update_xaxes(title="Emissões CO₂ (t) — fator IMO 3.206", gridcolor="rgba(46,199,106,.08)",
                     color="#7a9472", title_font=dict(size=10))
    fig.update_yaxes(autorange="reversed", color="#7a9472")
    return chart_layout(fig, height=230)


# ─── App bootstrap ────────────────────────────────────────────────────────────

inject_css()

# ─── App state / configuration defaults ──────────────────────────────────────

defaults = {
    "scenario_name": "Navegação padrão",
    "rpm_target": 85,
    "rudder_angle": 0,
    "fuel_price": 650,
    "ship_value_m": 50,
    "conservative_veto": True,
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

scenario_name = st.session_state["scenario_name"]
rpm_target = int(st.session_state["rpm_target"])
rudder_angle = int(st.session_state["rudder_angle"])
fuel_price = float(st.session_state["fuel_price"])
ship_value = float(st.session_state["ship_value_m"]) * 1_000_000
conservative_veto = bool(st.session_state["conservative_veto"])
backend_state = "ONLINE" if BACKEND_ONLINE else "CONTINGÊNCIA"


# ─── Compute ─────────────────────────────────────────────────────────────────

cfg = SCENARIOS[scenario_name]
route_df = calculate_routes(scenario_name, rpm_target, fuel_price, ship_value, conservative_veto)
best_route = route_df.iloc[0]
best_route_id = str(best_route["id"])

speed_knots = max(3.5, rpm_target * 0.215 - float(cfg["speed_penalty"]))
heading = 45.0 + rudder_angle * 0.35 + math.sin(time.time() / 8.0) * 0.6
cpa_nm = 0.42 if scenario_name in {"Ataque GPS spoofing", "Bloqueio militar (Suez)"} else 1.8
tcpa_min = 11 if cpa_nm < 1 else 36
ukc_m = 45.2 - max(0, float(cfg["sea_state"]) - 4) * 0.8
mission_risk = max(float(cfg["geopolitical"]), float(cfg["cyber"]), 100 - float(best_route["Índice de segurança"]))

utc_now = datetime.now(timezone.utc)
best_route_obj = next(route for route in ROUTES if route["id"] == best_route_id)
best_speed = float(best_route["Velocidade (kn)"])
base_fuel_tpd = float(best_route_obj["fuel_base_tpd"])
cruise_speed = float(best_route_obj["cruise_kn"])
daily_fuel_tons = base_fuel_tpd * ((best_speed / cruise_speed) ** 3)
bunker_tph = daily_fuel_tons / 24.0
eta_utc = utc_now + timedelta(days=float(best_route["Dias"]))
biofouling_index = 11.0 if best_route_id == "nsr" else 18.0 if best_route_id == "suez" else 24.0
biofouling_index += 3.0 if float(cfg["sea_state"]) >= 7 else 0.0
drag_penalty_pct = biofouling_index * 0.42
engine_efficiency = float(np.clip(94.0 - abs(rpm_target - 82) * 0.16 - drag_penalty_pct * 0.12, 72, 97))
crew_fatigue = float(np.clip(28 + float(cfg["sea_state"]) * 6 + (12 if scenario_name == "Ataque GPS spoofing" else 0), 18, 96))
rest_compliance = "Crítico" if crew_fatigue >= 72 else "Atenção" if crew_fatigue >= 55 else "Conforme"
provisions_days = max(9, int(36 - float(best_route["Dias"]) * 0.28))
fresh_water_days = max(7, int(24 - float(cfg["sea_state"]) * 0.7))
anchorage_wait_h = 54 if scenario_name == "Bloqueio militar (Suez)" else 22 if best_route_id == "cape" else 14
crane_productivity = 27 if anchorage_wait_h > 40 else 34 if best_route_id == "nsr" else 31
pilot_eta = eta_utc + timedelta(hours=2 if anchorage_wait_h < 24 else 8)
tide_window = eta_utc + timedelta(hours=5)
tug_count = 3 if best_route_id in {"suez", "cape"} else 2
security_zone = (
    "Mar Vermelho: ameaça elevada" if best_route_id == "suez" or scenario_name == "Bloqueio militar (Suez)"
    else "Golfo da Guiné distante da rota" if best_route_id == "cape"
    else "Ártico: baixa pirataria, alta dependência SAR"
)

# ─── Opening cover ───────────────────────────────────────────────────────────

st.markdown(
    f"""
    <section class="hero-cover">
        <div class="hero-inner">
            <div class="hero-kicker">Northern Sea Route Autonomous Evaluation and Geopolitical Intelligence System</div>
            <h1 class="hero-title">NSR-AEGIS</h1>
            <div class="hero-copy">
                O NSR-Aegis é um gêmeo digital de apoio à decisão marítima para travessias complexas:
                combina navegação ECDIS/ARPA, integridade de sensores, risco geopolítico, economia de bunker,
                operação portuária, condição da tripulação e segurança externa em uma única leitura de comando.
                A proposta não é substituir o comandante, mas entregar uma cabine analítica capaz de explicar
                por que uma rota deve ser executada, restringida ou vetada.
            </div>
            <div class="hero-rule"></div>
        </div>
    </section>
    """,
    unsafe_allow_html=True,
)

# ─── Tabs ────────────────────────────────────────────────────────────────────

tab_config, tab_command, tab_bridge, tab_engineering, tab_economics, tab_commander, tab_audit = st.tabs(
    ["Configuração", "Comando ECDIS", "Passadiço tático", "Engenharia", "Economia", "Comandante", "Auditoria IA"]
)

with tab_config:
    cfg_left, cfg_mid, cfg_right = st.columns([1, 1, 1], gap="large")

    with cfg_left:
        st.markdown('<div class="section-label">Cenário operacional</div>', unsafe_allow_html=True)
        st.selectbox("Cenário", list(SCENARIOS.keys()), key="scenario_name", label_visibility="collapsed")
        cfg_live = SCENARIOS[st.session_state["scenario_name"]]
        panel_note(
            "Condição global",
            f"{cfg_live['brief']} GPS/DGPS: <strong>{cfg_live['gps']}</strong>. NAVAREA: {cfg_live['primary_alert']}",
            str(cfg_live["gps_tone"]),
        )
        threat_bar("Risco geopolítico", float(cfg_live["geopolitical"]))
        threat_bar("Risco cibernético", float(cfg_live["cyber"]))
        threat_bar("Estado do mar", float(cfg_live["sea_state"]) * 12.5)

    with cfg_mid:
        st.markdown('<div class="section-label">Propulsão e manobra</div>', unsafe_allow_html=True)
        st.slider("RPM do motor principal", 0, 120, key="rpm_target", step=1)
        st.slider("Ângulo do leme (graus)", -35, 35, key="rudder_angle", step=1)
        panel_note(
            "Controle de bordo",
            "Os controles aqui alimentam o gêmeo digital. Altere os valores e o Streamlit recalcula rota, risco, consumo e ETA automaticamente.",
            "ok",
        )

    with cfg_right:
        st.markdown('<div class="section-label">Economia e política de veto</div>', unsafe_allow_html=True)
        st.slider("VLSFO simulado (US$/t)", 480, 920, key="fuel_price", step=10)
        st.slider("Valor segurado do casco (US$ M)", 20, 120, key="ship_value_m", step=5)
        st.checkbox("Critério de veto conservador (ISI ≥ 66)", key="conservative_veto")
        cfg_status = pd.DataFrame({
            "Sistema": ["Backend multiagente", "Relógio UTC", "Modo de veto"],
            "Estado": [
                backend_state,
                datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "Conservador" if st.session_state["conservative_veto"] else "Operacional",
            ],
        })
        dark_table(cfg_status, height=180)

# ── Tab 1: Command / ECDIS ────────────────────────────────────────────────────
with tab_command:
    st.markdown(
        f"""
        <div class="clock-strip">
            <div class="clock-item"><span class="clock-key">UTC</span><span class="clock-val">{utc_now.strftime("%Y-%m-%d %H:%M:%S")}</span></div>
            <span class="clock-sep">|</span>
            <div class="clock-item"><span class="clock-key">Rumo</span><span class="clock-val">{heading:.1f}°</span></div>
            <span class="clock-sep">|</span>
            <div class="clock-item"><span class="clock-key">SOG</span><span class="clock-val">{speed_knots:.1f} kn</span></div>
            <span class="clock-sep">|</span>
            <div class="clock-item"><span class="clock-key">Leme</span><span class="clock-val">{rudder_angle:+d}°</span></div>
            <span class="clock-sep">|</span>
            <div class="clock-item"><span class="clock-key">GPS</span><span class="clock-val">{cfg["gps"]}</span></div>
            <span class="clock-sep">|</span>
            <div class="clock-item"><span class="clock-key">UKC</span><span class="clock-val">{ukc_m:.1f} m</span></div>
            <span class="clock-sep">|</span>
            <div class="clock-item"><span class="clock-key">NAVAREA</span><span class="clock-val">{cfg["primary_alert"]}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    k1, k2, k3 = st.columns(3, gap="large")
    with k1:
        metric_card("GPS / DGPS", str(cfg["gps"]), str(cfg["gps_detail"]), str(cfg["gps_tone"]))
    with k2:
        metric_card("Risco geopolítico", f"{cfg['geopolitical']:.0f}/100", f"WRP {cfg['wrp_delta']}", risk_tone(float(cfg["geopolitical"])))
    with k3:
        metric_card("Velocidade SOG", f"{speed_knots:.1f} kn", f"Rumo giro {heading:.1f}°", "neutral")
    st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
    k4, k5, k6 = st.columns(3, gap="large")
    with k4:
        metric_card("ARPA CPA/TCPA", f"{cpa_nm:.2f} NM", f"TCPA {tcpa_min} min", "crit" if cpa_nm < 0.8 else "ok")
    with k5:
        metric_card("UKC ecobatímetro", f"{ukc_m:.1f} m", "Margem sob a quilha", "warn" if ukc_m < 12 else "ok")
    with k6:
        metric_card("Risco da missão", f"{mission_risk:.0f}/100", f"Veto {'conservador' if conservative_veto else 'operacional'}", risk_tone(mission_risk))

    st.markdown('<div class="dashboard-spacer"></div>', unsafe_allow_html=True)

    left, right = st.columns([1.55, 1], gap="large")
    with left:
        st.markdown('<div class="section-label">ECDIS global — rotas candidatas</div>', unsafe_allow_html=True)
        st.plotly_chart(build_geo_chart(best_route_id), width="stretch")

    with right:
        decision_tone = "crit" if best_route["Status"] == "Vetada" else "warn" if best_route["Status"] == "Restrita" else "ok"
        panel_note(
            f"Veredito Comodoro IA: {best_route['Rota']}",
            f"Rota selecionada após veto físico, análise de custo e índice de segurança integrado (ISI). "
            f"ISI final: <strong>{float(best_route['Índice de segurança']):.1f}/100</strong>. "
            f"TVC projetado: <strong>{money_m(float(best_route['TVC']))}</strong>. "
            f"Duração: <strong>{float(best_route['Dias']):.1f} dias</strong>.",
            decision_tone,
        )
        st.markdown('<div class="section-label">Custo total comparado (US$ M)</div>', unsafe_allow_html=True)
        st.plotly_chart(build_cost_chart(route_df), width="stretch")

    st.markdown('<div class="section-label">Matriz de decisão integrada</div>', unsafe_allow_html=True)
    table_df = route_df.copy()
    table_df["Velocidade (kn)"] = table_df["Velocidade (kn)"].map(lambda x: f"{x:.1f}")
    table_df["Dias"] = table_df["Dias"].map(lambda x: f"{x:.1f}")
    table_df["TVC"] = table_df["TVC"].map(money_m)
    table_df["Prêmio de risco"] = table_df["Prêmio de risco"].map(money_m)
    table_df["Índice de segurança"] = table_df["Índice de segurança"].map(lambda x: f"{x:.1f}/100")
    dark_table(
        table_df[["Rota", "Distância (NM)", "Velocidade (kn)", "Dias", "TVC", "Prêmio de risco", "Índice de segurança", "Status"]],
        height=240,
    )

# ── Tab 2: Bridge ─────────────────────────────────────────────────────────────
with tab_bridge:
    radar_col, control_col, comms_col = st.columns([1.35, 1, 1], gap="large")

    with radar_col:
        st.markdown('<div class="section-label">Radar banda-X / ARPA — display PPI</div>', unsafe_allow_html=True)
        st.plotly_chart(build_radar_chart(scenario_name), width="stretch")
        panel_note(
            "Regra COLREG aplicada",
            f"Contato sem AIS tratado como alvo de manobra restrita. CPA calculado: <strong>{cpa_nm:.2f} NM</strong> em <strong>{tcpa_min} min</strong>. "
            f"{'AÇÃO: Reduzir velocidade e alterar rumo a boreste imediatamente.' if cpa_nm < 0.8 else 'Situação monitorada — sem manobra imediata requerida.'}",
            "crit" if cpa_nm < 0.8 else "ok",
        )

    with control_col:
        st.markdown('<div class="section-label">Propulsão & piloto automático</div>', unsafe_allow_html=True)
        st.plotly_chart(build_engine_chart(rpm_target), width="stretch")
        panel_note(
            "Controlador de rumo (GNSS/INS)",
            f"Setpoint 045.0°. Rumo atual <strong>{heading:.1f}°</strong>. Leme <strong>{rudder_angle:+d}°</strong>. "
            f"{'Desvio elevado — verificar atuador.' if abs(rudder_angle) > 20 else 'Atuador dentro de envelope operacional.'}",
            "ok" if abs(rudder_angle) <= 20 else "warn",
        )
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            if st.button("Silenciar alarme"):
                st.toast("Alarme reconhecido no console do OOW.")
        with c2:
            if st.button("VHF canal 16"):
                st.toast("Canal VHF 16 aberto — escuta prioritária ativa.")

    with comms_col:
        st.markdown('<div class="section-label">GMDSS · AIS · NAVAREA</div>', unsafe_allow_html=True)
        log_line(f"[AIS] {cfg['ais']}", "ok")
        log_line("[GMDSS] Inmarsat-C — sem DSC de socorro na NAVAREA I.", "ok")
        log_line(f"[NAVAREA] {cfg['primary_alert']}", risk_tone(float(cfg["geopolitical"])))
        log_line(f"[CYBER] Integridade de navegação: {cfg['cyber']:.0f}/100", risk_tone(float(cfg["cyber"])))
        log_line(f"[GPS] Estado: {cfg['gps']} — {cfg['gps_detail']}", str(cfg["gps_tone"]))
        if scenario_name == "Ataque GPS spoofing":
            log_line("[FUSION] GNSS excluído do filtro de Kalman. INS + radar em autoridade total.", "crit")

        st.markdown('<div class="section-label" style="margin-top:10px;">Estado ambiental</div>', unsafe_allow_html=True)
        env_df = pd.DataFrame({
            "Sensor": ["Anemômetro", "Barômetro", "Visibilidade", "Gelo radar", "Estado do mar"],
            "Leitura": [
                f"{cfg['wind_kt']} kt",
                "1008 hPa" if float(cfg["sea_state"]) < 7 else "987 hPa",
                f"{cfg['visibility_nm']} NM",
                f"{cfg['ice_m']:.2f} m",
                f"Estado {cfg['sea_state']}",
            ],
            "Confiança": ["96 %", "93 %", "89 %", "91 %", "94 %"],
        })
        dark_table(env_df, height=240)

# ── Tab 3: Engineering ────────────────────────────────────────────────────────
with tab_engineering:
    stability_col, fatigue_col, systems_col = st.columns([1, 1.25, 1], gap="large")
    pitch = 1.2 if scenario_name != "Tempestade ártica extrema" else 5.8
    roll = -0.7 if scenario_name != "Tempestade ártica extrema" else -12.4

    with stability_col:
        st.markdown('<div class="section-label">Estabilidade · trim · banda</div>', unsafe_allow_html=True)
        st.plotly_chart(build_stability_chart(pitch, roll), width="stretch")
        panel_note(
            "Envelope de estabilidade dinâmica",
            f"Pitch <strong>{pitch:.1f}°</strong>. Banda <strong>{roll:.1f}°</strong>. "
            f"{'ALERTA: banda excede 10°. Transferir lastro imediatamente.' if abs(roll) > 10 else 'Lastro automático mantendo GM positivo — envelope OK.'}",
            "crit" if abs(roll) > 10 else "ok",
        )
        st.markdown('<div class="section-label" style="margin-top:8px;">Ecobatímetro / UKC</div>', unsafe_allow_html=True)
        st.plotly_chart(build_ukc_chart(ukc_m), width="stretch")

    with fatigue_col:
        st.markdown('<div class="section-label">Fadiga do casco ice-class PC4 — últimas 72 min</div>', unsafe_allow_html=True)
        st.plotly_chart(build_fatigue_chart(scenario_name), width="stretch")
        hull_load = 100 - float(best_route["Índice de segurança"])
        panel_note(
            "Margem estrutural PC4",
            f"Carga equivalente estimada em <strong>{hull_load:.1f}%</strong> do envelope composto. "
            f"Limite operacional reduzido quando gelo > 1.5 m e estado do mar > 6 convergem. "
            f"Monitoramento contínuo via acelerômetros de casco e strain gauges da cuaderna-mestra.",
            "warn" if hull_load > 34 else "ok",
        )
        col_a, col_b = st.columns(2, gap="medium")
        with col_a:
            st.metric("UKC atual", f"{ukc_m:.1f} m", "alarme 8.0 m")
        with col_b:
            st.metric("Espessura do gelo", f"{cfg['ice_m']:.2f} m", f"Estado mar {cfg['sea_state']}")

    with systems_col:
        st.markdown('<div class="section-label">Compartimentos críticos</div>', unsafe_allow_html=True)
        systems_df = pd.DataFrame({
            "Zona": ["Proa", "Máquinas", "Tanques", "Popa", "Data rack"],
            "Estado": ["Estanque", "Normal", "Normal", "Estanque", "Redundante"],
            "Bomba": ["Auto", "Standby", "Standby", "Auto", "N/A"],
            "Risco": [
                "Baixo", "Baixo", "Médio", "Baixo",
                "Médio" if scenario_name == "Ataque GPS spoofing" else "Baixo",
            ],
        })
        dark_table(systems_df, height=240)
        panel_note(
            "Energia & redundância",
            "Barramento principal em carga nominal. UPS de navegação com autonomia de <strong>42 min</strong>. "
            "Giro, INS e radar em alimentação segregada. Gerador de emergência testado a cada 7 dias.",
            "ok",
        )
        st.markdown('<div class="section-label" style="margin-top:4px;">Temperatura e vibração</div>', unsafe_allow_html=True)
        eng_df = pd.DataFrame({
            "Sistema": ["Motor principal", "Turbo compressor", "Eixo de hélice", "Chumaceira de proa"],
            "Temp (°C)": [88, 420, 62, 44],
            "Vibração (mm/s)": [2.1, 5.4, 1.8, 0.9],
        })
        dark_table(eng_df, height=220)

# ── Tab 4: Economics & Efficiency ─────────────────────────────────────────────
with tab_economics:
    eco_left, eco_right = st.columns([1.2, 1], gap="large")

    with eco_left:
        st.markdown('<div class="section-label">Curva de eficiência — consumo vs velocidade (VLSFO)</div>', unsafe_allow_html=True)
        st.plotly_chart(build_fuel_efficiency_chart(route_df), width="stretch")
        panel_note(
            "Princípio de Admiralidade: consumo cúbico com a velocidade",
            "A relação consumo ∝ V³ implica que uma redução de 10% na velocidade reduz o consumo em ~27%. "
            "O ponto marcado indica a operação atual para cada rota. "
            f"VLSFO simulado: <strong>US$ {fuel_price}/t</strong>.",
            "ok",
        )

    with eco_right:
        st.markdown('<div class="section-label">Decomposição do custo por componente</div>', unsafe_allow_html=True)
        st.plotly_chart(build_cost_breakdown_chart(route_df, fuel_price, ship_value), width="stretch")
        st.markdown('<div class="section-label">Emissões CO₂ por rota (IMO CII 2023)</div>', unsafe_allow_html=True)
        st.plotly_chart(build_co2_chart(route_df), width="stretch")

    st.markdown('<div class="section-label">Sensibilidade econômica</div>', unsafe_allow_html=True)
    # Sensitivity: show how TVC changes with fuel price for best route
    eco_detail = route_df.copy()
    eco_detail["Custo combustível (US$ M)"] = eco_detail.apply(
        lambda r: (
            float(next(ro["fuel_base_tpd"] for ro in ROUTES if ro["id"] == r["id"]))
            * ((float(r["Velocidade (kn)"]) / float(next(ro["cruise_kn"] for ro in ROUTES if ro["id"] == r["id"]))) ** 3)
            * float(r["Dias"])
            * fuel_price / 1e6
        ), axis=1
    )
    eco_detail["OPEX (US$ M)"] = eco_detail["Dias"].apply(lambda d: d * 45_000 / 1e6)
    eco_detail["Risco (US$ M)"] = eco_detail["Prêmio de risco"].apply(lambda v: v / 1e6)
    eco_detail["TVC (US$ M)"] = eco_detail["TVC"].apply(lambda v: v / 1e6)
    disp = eco_detail[["Rota", "Dias", "Custo combustível (US$ M)", "OPEX (US$ M)", "Risco (US$ M)", "TVC (US$ M)", "Status"]].copy()
    disp["Dias"] = disp["Dias"].map(lambda x: f"{x:.1f}")
    disp["Custo combustível (US$ M)"] = disp["Custo combustível (US$ M)"].map(lambda x: f"{x:.2f}")
    disp["OPEX (US$ M)"] = disp["OPEX (US$ M)"].map(lambda x: f"{x:.2f}")
    disp["Risco (US$ M)"] = disp["Risco (US$ M)"].map(lambda x: f"{x:.2f}")
    disp["TVC (US$ M)"] = disp["TVC (US$ M)"].map(lambda x: f"{x:.2f}")
    dark_table(disp, height=240)

# ── Tab 5: Commander strategy ─────────────────────────────────────────────────
with tab_commander:
    ctop1, ctop2 = st.columns(2, gap="large")
    with ctop1:
        metric_card("Bunker por hora", f"{bunker_tph:.2f} t/h", f"VLSFO US$ {fuel_price}/t", "warn" if bunker_tph > 1.9 else "ok")
    with ctop2:
        metric_card("Eficiência do motor", f"{engine_efficiency:.1f}%", "Carga, RPM e arrasto do casco", "ok" if engine_efficiency >= 88 else "warn")
    ctop3, ctop4 = st.columns(2, gap="large")
    with ctop3:
        metric_card("Fadiga da tripulação", f"{crew_fatigue:.0f}/100", f"STCW: {rest_compliance}", risk_tone(crew_fatigue))
    with ctop4:
        metric_card("Janela portuária", eta_utc.strftime("%d/%m %H:%M"), f"Fundeio: {anchorage_wait_h} h", "warn" if anchorage_wait_h > 36 else "ok")

    st.markdown('<div class="dashboard-spacer"></div>', unsafe_allow_html=True)

    perf_col, port_col = st.columns([1, 1], gap="large")
    with perf_col:
        st.markdown('<div class="section-label">Fatores econômicos e desempenho</div>', unsafe_allow_html=True)
        performance_df = pd.DataFrame({
            "Variável": [
                "Consumo de bunker",
                "Eco-speed recomendado",
                "Eficiência do motor",
                "Biofouling do casco",
                "Temperatura / pressão",
            ],
            "Leitura": [
                f"{daily_fuel_tons:.1f} t/dia ({bunker_tph:.2f} t/h)",
                f"{max(8.0, best_speed - 0.8):.1f} kn para reduzir consumo sem perder ETA",
                f"{engine_efficiency:.1f}% de eficiência composta",
                f"Índice {biofouling_index:.0f}/100; penalidade de arrasto {drag_penalty_pct:.1f}%",
                "Motor principal 88°C; turbo 420°C; vibração dentro da faixa",
            ],
            "Ação do comandante": [
                "Comparar economia de bunker contra multa por atraso.",
                "Autorizar redução se a janela de maré permitir.",
                "Solicitar relatório do Chefe de Máquinas a cada quarto.",
                "Programar limpeza de casco se penalidade superar 10%.",
                "Manter geradores em redundância até sair de área crítica.",
            ],
        })
        dark_table(performance_df, height=330)
        panel_note(
            "Leitura comercial",
            f"A velocidade atual de {best_speed:.1f} kn mantém ETA em {eta_utc.strftime('%d/%m %H:%M UTC')}. "
            f"Cada 0.5 kn acima da eco-speed aumenta o bunker de forma não linear; o comandante deve aceitar esse custo apenas se proteger a janela portuária.",
            "warn" if bunker_tph > 1.9 else "ok",
        )

    with port_col:
        st.markdown('<div class="section-label">Logística comercial e operação portuária</div>', unsafe_allow_html=True)
        port_df = pd.DataFrame({
            "Item": [
                "Berthing slot",
                "Congestionamento no fundeio",
                "Produtividade dos guindastes",
                "Prático",
                "Rebocadores",
                "Restrição de maré",
            ],
            "Estado projetado": [
                f"Janela primária em {eta_utc.strftime('%d/%m %H:%M UTC')}",
                f"{anchorage_wait_h} h de espera estimada",
                f"{crane_productivity} movimentos/h por equipamento",
                f"Embarque previsto {pilot_eta.strftime('%d/%m %H:%M UTC')}",
                f"{tug_count} unidades confirmadas; 1 em reserva",
                f"Maré favorável até {tide_window.strftime('%d/%m %H:%M UTC')}",
            ],
            "Risco": [
                "Médio" if anchorage_wait_h > 24 else "Baixo",
                "Alto" if anchorage_wait_h > 40 else "Médio",
                "Médio" if crane_productivity < 30 else "Baixo",
                "Baixo",
                "Baixo" if tug_count >= 2 else "Médio",
                "Médio",
            ],
        })
        dark_table(port_df, height=330)
        panel_note(
            "ETA operacional",
            "A decisão de velocidade não é apenas náutica: ela precisa casar ETA, maré, prático, rebocadores e slot de atracação. "
            "Chegar cedo demais queima bunker e fundeio; chegar tarde perde janela comercial.",
            "warn" if anchorage_wait_h > 36 else "ok",
        )

    human_col, security_col = st.columns([1, 1], gap="large")
    with human_col:
        st.markdown('<div class="section-label">Fatores humanos e bem-estar</div>', unsafe_allow_html=True)
        human_df = pd.DataFrame({
            "Dimensão": [
                "Fadiga e descanso",
                "Escala de quartos",
                "Rancho e moral",
                "Água potável",
                "Saúde / telemedicina",
                "Peças críticas",
            ],
            "Leitura": [
                f"Índice de fadiga {crew_fatigue:.0f}/100; conformidade {rest_compliance}",
                "OOW 4/8 com reforço em aproximação portuária",
                f"Suprimentos para {provisions_days} dias; qualidade do rancho estável",
                f"Autonomia estimada {fresh_water_days} dias; dessalinizador em standby",
                "Sem feridos; caso febril isolado em observação por 12 h",
                "Filtros, juntas e sensores críticos acima do mínimo",
            ],
            "Ação": [
                "Reordenar descanso se fadiga superar 55/100.",
                "Evitar troca de turno durante manobra de risco.",
                "Preservar moral em viagem longa; auditoria diária de cozinha.",
                "Racionamento preventivo se autonomia cair abaixo de 10 dias.",
                "Abrir telemedicina se febre persistir ou houver trauma.",
                "Bloquear rota remota se sobressalentes essenciais faltarem.",
            ],
        })
        dark_table(human_df, height=350)
        panel_note(
            "Risco humano",
            "O erro de navegação mais caro costuma nascer de fadiga, ruído operacional e comunicação ruim no passadiço. "
            "Por isso o painel trata descanso, saúde e moral como variáveis de segurança, não como notas administrativas.",
            risk_tone(crew_fatigue),
        )

    with security_col:
        st.markdown('<div class="section-label">Geopolítica, segurança externa e legislação</div>', unsafe_allow_html=True)
        security_df = pd.DataFrame({
            "Camada": [
                "Pirataria / conflito",
                "Inteligência marítima",
                "Plano de evasão",
                "Legislação ambiental",
                "Troca de combustível ECA",
                "Seguro e compliance",
            ],
            "Leitura": [
                security_zone,
                f"Risco geopolítico {cfg['geopolitical']:.0f}/100; WRP {cfg['wrp_delta']}",
                "Rotas de fuga e citadel brief revisados no último turno",
                "Checar MARPOL Anexo VI e regras locais do porto de destino",
                "MGO/baixo enxofre antes de entrar em zona ECA",
                f"Prêmio de risco da rota: {money_m(float(best_route['Prêmio de risco']))}",
            ],
            "Protocolo": [
                "Elevar vigilância se risco > 55 ou AIS hostil aparecer.",
                "Atualizar NAVAREA, UKMTO/MSCHOA ou equivalente regional.",
                "Treinar lockdown, blackout seletivo e comunicações satelitais.",
                "Registrar combustível, emissões e lastro antes da chegada.",
                "Planejar troca sem comprometer pressão e temperatura do motor.",
                "Documentar justificativa de rota para auditoria e seguradora.",
            ],
        })
        dark_table(security_df, height=350)
        panel_note(
            "Postura de segurança",
            "O comandante precisa enxergar ameaça externa como custo, rota e vida humana ao mesmo tempo. "
            "Quando conflito, pirataria ou legislação ambiental mudam, a rota deixa de ser só a menor distância.",
            risk_tone(float(cfg["geopolitical"])),
        )

# ── Tab 6: Audit ──────────────────────────────────────────────────────────────
with tab_audit:
    audit_col, doctrine_col = st.columns([1.15, 1], gap="large")

    with audit_col:
        st.markdown('<div class="section-label">Trilha de decisão — Comodoro IA (cadeia de raciocínio)</div>', unsafe_allow_html=True)
        st.markdown('<div class="timeline">', unsafe_allow_html=True)

        timeline_item(
            "Passo 01 — Inicialização",
            f"Agente Comodoro inicializado. Valor do casco: <strong>{money_m(ship_value)}</strong>. Classe de gelo: <strong>PC4</strong>. "
            f"Critério de veto ISI ≥ <strong>{'66' if conservative_veto else '56'}</strong>.",
            "ok",
        )
        timeline_item(
            "Passo 02 — Veto físico",
            "Agente de Navegação executou análise de fadiga estrutural para cada candidato. "
            "Rotas com stress_factor > 0.85 do limite PC4 são vetadas antes de qualquer análise econômica.",
            "ok" if best_route["Status"] != "Vetada" else "crit",
        )
        timeline_item(
            "Passo 03 — Análise econômica",
            f"Agente Econômico calculou TVC incluindo combustível (VLSFO US$ {fuel_price}/t), "
            f"OPEX (US$ 45.000/dia), prêmio de guerra e prêmio de gelo por rota.",
            "ok",
        )
        timeline_item(
            "Passo 04 — Integração de sensores",
            f"GPS/GNSS: <strong>{cfg['gps']}</strong> — {cfg['gps_detail']}. "
            f"Penalidade cibernética aplicada: {'Sim (−14 ISI)' if scenario_name == 'Ataque GPS spoofing' else 'Não'}.",
            str(cfg["gps_tone"]),
        )

        best_tone = "crit" if best_route["Status"] == "Vetada" else "warn" if best_route["Status"] == "Restrita" else "ok"
        timeline_item(
            "Passo 05 — Veredito final",
            f"Rota selecionada: <strong>{best_route['Rota']}</strong>. "
            f"Status: <strong>{best_route['Status']}</strong>. "
            f"TVC: <strong>{money_m(float(best_route['TVC']))}</strong>. "
            f"ISI: <strong>{float(best_route['Índice de segurança']):.1f}/100</strong>.",
            best_tone,
        )

        if best_route["Status"] == "Restrita":
            timeline_item(
                "Passo 06 — Revisão humana obrigatória",
                "Rota liberada com restrição operacional. Exige confirmação explícita do Comandante antes de execução autônoma.",
                "warn",
            )
        elif best_route["Status"] == "Vetada":
            timeline_item(
                "Passo 06 — Bloqueio de execução",
                "Nenhuma rota aprovada para execução autônoma. Aguardando ordem do Comandante ou mudança de condições.",
                "crit",
            )
        else:
            timeline_item(
                "Passo 06 — Execução autorizada",
                "Execução autônoma dentro do envelope aprovado. Sistema NSR-Aegis em controle de rota.",
                "ok",
            )

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="section-label" style="margin-top:14px;">Matriz de evidências</div>', unsafe_allow_html=True)
        evidence = pd.DataFrame({
            "Camada": ["Navegação", "Economia", "Segurança", "Engenharia"],
            "Evidência": [
                "ECDIS + radar + INS + DGPS",
                "TVC: combustível, OPEX, prêmio de risco",
                "CPA/TCPA, AIS, GMDSS, NAVAREA",
                "PC4, UKC, lastro, fadiga, temperatura",
            ],
            "Peso": ["35 %", "25 %", "25 %", "15 %"],
            "Agente": ["NavAgent", "EcoAgent", "NavAgent", "EcoAgent"],
        })
        dark_table(evidence, height=230)

    with doctrine_col:
        st.markdown('<div class="section-label">Critérios rígidos de aceitação (COLREG + ISM)</div>', unsafe_allow_html=True)
        acceptance = pd.DataFrame({
            "Critério": ["CPA mínimo", "UKC mínimo", "ISI mínimo", "GNSS confiável", "Banda máxima", "CII compliance"],
            "Limite": ["0.8 NM", "8.0 m", f"{'66' if conservative_veto else '56'}/100", "2 fontes independentes", "10°", "Emissões monitoradas"],
            "Estado": [
                "FALHA" if cpa_nm < 0.8 else "OK",
                "OK" if ukc_m >= 8 else "FALHA",
                "OK" if float(best_route["Índice de segurança"]) >= (66 if conservative_veto else 56) else "FALHA",
                "FALHA" if scenario_name == "Ataque GPS spoofing" else "OK",
                "FALHA" if abs(roll) > 10 else "OK",
                "ATIVO",
            ],
        })
        dark_table(acceptance, height=290)

        st.markdown('<div class="section-label" style="margin-top:10px;">Contingência de navegação</div>', unsafe_allow_html=True)
        if scenario_name == "Ataque GPS spoofing":
            panel_note(
                "Protocolo astronômico ativado",
                "Sextante digital e almanaque náutico usados como fix independente. "
                "Latitude via Polaris. Longitude via cronômetro (deriva < 0.4 s/dia) cruzado com radar costeiro.",
                "crit",
            )
            log_line("[SEXTANTE] Polaris observada — latitude estimada: 73° 14.2' N", "ok")
            log_line("[CRONÔMETRO] Deriva: 0.38 s/dia — longitude em validação cruzada", "warn")
            log_line("[RADAR] Ponto conspícuo identificado — fix confirmado com erro < 0.5 NM", "ok")
        else:
            panel_note(
                "Backup astronômico em prontidão",
                "Efemérides do dia carregadas. Horizonte artificial calibrado. "
                "Protocolo astronômico ativado automaticamente se GNSS, DGPS e INS divergirem.",
                "ok",
            )
            log_line("[ALMANAQUE] Efemérides atualizadas — cobertura 24h", "ok")
            log_line("[SEXTANTE] Calibração semanal dentro da tolerância ±0.1'", "ok")
            log_line("[INS] Deriva inercial < 0.5 NM/h — navegação autônoma viável por 18h", "ok")

st.markdown(
    "<div style='text-align:center;font-family:JetBrains Mono,monospace;font-size:.65rem;"
    "color:#3a4238;margin-top:28px;letter-spacing:.1em;'>"
    "NSR-AEGIS 2026 &nbsp;·&nbsp; SISTEMA DE SUPORTE À DECISÃO MARÍTIMA &nbsp;·&nbsp; "
    "POLAR CLASS PC4 &nbsp;·&nbsp; USO RESTRITO À TRIPULAÇÃO AUTORIZADA"
    "</div>",
    unsafe_allow_html=True,
)
