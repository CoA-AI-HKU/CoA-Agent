"""
dashboard.py - Privacy-First Caregiver Dashboard
Shows insights and trends without exposing conversation content
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os

# Add .nanobot to path
sys.path.insert(0, str(Path.home() / ".nanobot"))

from metrics import MetricsCollector
from insights import InsightGenerator
try:
    from user.user_registry import get_registered_patient_accounts
except ImportError:  # pragma: no cover - package import path.
    from src.user.user_registry import get_registered_patient_accounts

# ============================================================
# Page Config
# ============================================================
st.set_page_config(
    page_title="小安 - 照顧者儀表板",
    page_icon="📊",
    layout="wide"
)

# ============================================================
# Initialize
# ============================================================
@st.cache_resource
def get_collector():
    return MetricsCollector()

@st.cache_resource
def get_insights():
    return InsightGenerator()

collector = get_collector()
insights = get_insights()

# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.image("https://placehold.co/60x60/4A90D9/white?text=小安", width=60)
    st.title("👤 患者選擇")
    
    registered_accounts = get_registered_patient_accounts()
    if registered_accounts:
        account_labels = {
            account["user_id"]: f'{account["display_name"]} ({account["user_id"]})'
            for account in registered_accounts
        }
        selected_user = st.selectbox(
            "選擇患者",
            list(account_labels),
            format_func=account_labels.__getitem__,
        )
    else:
        st.info("📭 暫無已登記的使用者帳戶。")
        selected_user = None
    
    st.divider()
    
    st.subheader("📅 時間範圍")
    days = st.selectbox("顯示天數", [7, 14, 30, 60], index=0)
    
    st.divider()
    
    st.caption("🔒 私隱保護：不顯示對話內容")
    st.caption(f"📊 最後更新: {datetime.now().strftime('%H:%M')}")

# ============================================================
# Main Dashboard
# ============================================================
st.title("📊 小安 - 照顧者洞察儀表板")

if not selected_user:
    st.info("👆 請從左側選擇患者")
    st.stop()

# ============================================================
# Load Data
# ============================================================
metrics = collector.get_user_metrics(selected_user, days=days)
alerts = insights.get_alerts(selected_user, days=3)
summary = insights.get_summary(selected_user)

# ============================================================
# Row 1: Key Metrics (4 cards)
# ============================================================
col1, col2, col3, col4 = st.columns(4)

with col1:
    mood = metrics.get("avg_mood")
    mood_display = f"⭐ {mood:.1f}" if mood else "N/A"
    mood_color = "green" if mood and mood >= 4 else "orange" if mood and mood >= 3 else "red"
    st.metric("❤️ 情緒狀態", mood_display, delta=summary.get("mood_status", ""))

with col2:
    cognitive = metrics.get("avg_cognitive")
    cognitive_display = f"🎯 {cognitive:.1f}" if cognitive else "N/A"
    st.metric("🧠 認知表現", cognitive_display, delta=summary.get("cognitive_status", ""))

with col3:
    interactions = metrics.get("total_interactions", 0)
    st.metric("💬 互動次數", interactions, delta=f"{interactions} 次")

with col4:
    adherence = metrics.get("medication_adherence")
    adherence_display = f"{int(adherence*100)}%" if adherence else "N/A"
    st.metric("💊 用藥依從", adherence_display, delta=summary.get("medication_status", ""))

# ============================================================
# Row 2: Mood Trend Chart
# ============================================================
st.subheader("📈 情緒趨勢")

mood_history = metrics.get("mood_history", [])
if mood_history:
    df_mood = pd.DataFrame(mood_history)
    df_mood["timestamp"] = pd.to_datetime(df_mood["timestamp"])
    df_mood = df_mood.sort_values("timestamp")
    
    fig = px.line(
        df_mood,
        x="timestamp",
        y="score",
        title="情緒評分變化 (1-5)",
        labels={"score": "情緒評分", "timestamp": "日期"},
        markers=True,
        range_y=[0.5, 5.5]
    )
    fig.update_traces(line_color="#4A90D9", marker_color="#4A90D9")
    fig.update_layout(height=250)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("📭 尚未收集情緒數據。每日問候可記錄情緒評分。")

# ============================================================
# Row 3: Two Columns - Cognitive & Engagement
# ============================================================
col1, col2 = st.columns(2)

with col1:
    st.subheader("🧠 認知訓練表現")
    
    cognitive_history = metrics.get("cognitive_history", [])
    if cognitive_history:
        df_cog = pd.DataFrame(cognitive_history)
        df_cog["timestamp"] = pd.to_datetime(df_cog["timestamp"])
        df_cog = df_cog.sort_values("timestamp")
        
        fig = px.bar(
            df_cog,
            x="timestamp",
            y="score",
            color="exercise_type",
            title="認知練習成績",
            labels={"score": "得分", "timestamp": "日期", "exercise_type": "練習類型"},
            range_y=[0, 5]
        )
        fig.update_layout(height=250)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📭 尚未有認知訓練數據")

with col2:
    st.subheader("📊 互動分析")
    
    intent_counts = metrics.get("intent_counts", {})
    if intent_counts:
        df_intent = pd.DataFrame({
            "Intent": list(intent_counts.keys()),
            "Count": list(intent_counts.values())
        })
        
        fig = px.pie(
            df_intent,
            values="Count",
            names="Intent",
            title="對話類型分佈",
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig.update_layout(height=250)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📭 暫無對話數據")

# ============================================================
# Row 4: Alerts & Recommendations
# ============================================================
st.subheader("⚠️ 提醒與建議")

if alerts:
    for alert in alerts:
        level = alert.get("level", "info")
        icon = alert.get("icon", "ℹ️")
        message = alert.get("message", "")
        
        if level == "urgent":
            st.error(f"{icon} {message}")
        elif level == "warning":
            st.warning(f"{icon} {message}")
        elif level == "success":
            st.success(f"{icon} {message}")
        else:
            st.info(f"{icon} {message}")
else:
    st.success("✅ 一切良好！繼續保持！")

# ============================================================
# Row 5: Patient Profile
# ============================================================
with st.expander("👤 患者檔案", expanded=False):
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**基本資料**")
        st.write(f"  • 姓名: {selected_user}")
        st.write(f"  • 最近互動: {len(metrics.get('mood_history', []))} 天有記錄")
        st.write(f"  • 總對話數: {metrics.get('total_interactions', 0)}")
    
    with col2:
        st.write("**健康摘要**")
        if summary.get("avg_mood"):
            st.write(f"  • 情緒狀態: {summary.get('mood_status', 'N/A')}")
        if summary.get("avg_cognitive"):
            st.write(f"  • 認知狀態: {summary.get('cognitive_status', 'N/A')}")
        if summary.get("medication_adherence"):
            st.write(f"  • 用藥狀態: {summary.get('medication_status', 'N/A')}")

# ============================================================
# Footer
# ============================================================
st.divider()
st.caption("🔒 所有數據本地儲存 · 不與第三方分享 · 照顧者專用")

# Auto-refresh
if st.button("🔄 重新整理數據"):
    st.rerun()
