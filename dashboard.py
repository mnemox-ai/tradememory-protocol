"""
TradeMemory Dashboard - "Watch Your Agent Evolve"
展示 agent 如何在一週內從錯誤中學習並自動調整策略

Version: 2.0 - Connected to Real MCP Server API
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
import os
import httpx
from pathlib import Path

# ================== 配置 ==================
st.set_page_config(
    page_title="TradeMemory - Watch Your Agent Evolve",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Configuration
API_BASE_URL = os.getenv("TRADEMEMORY_API_URL", "http://localhost:8000")
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "10.0"))
REFLECTIONS_DIR = Path(os.getenv("REFLECTIONS_DIR", "./reflections"))

# ================== 樣式 ==================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .insight-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 0.8rem;
        margin: 1rem 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .insight-title {
        font-size: 1.5rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    .before-after-container {
        display: flex;
        gap: 2rem;
        margin: 2rem 0;
    }
    .before-box {
        flex: 1;
        background-color: #ffe5e5;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #ff4444;
    }
    .after-box {
        flex: 1;
        background-color: #e5ffe5;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #44ff44;
    }
    .error-box {
        background-color: #ffe5e5;
        border: 2px solid #ff4444;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff4e5;
        border: 2px solid #ff9800;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ================== API Client Functions ==================

def check_api_health():
    """檢查 MCP Server 是否運行"""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{API_BASE_URL}/health")
            return response.status_code == 200
    except Exception:
        return False


def fetch_trade_history(days=7):
    """從 MCP Server 取得交易歷史"""
    try:
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.post(
                f"{API_BASE_URL}/trade/query_history",
                json={"limit": 1000}
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("success"):
                trades = data.get("trades", [])
                # 過濾最近 N 天的交易
                cutoff_date = datetime.now() - timedelta(days=days)
                recent_trades = [
                    t for t in trades 
                    if datetime.fromisoformat(t["timestamp"]) >= cutoff_date
                ]
                return recent_trades
            else:
                st.error(f"API Error: {data.get('error', 'Unknown error')}")
                return []
                
    except httpx.RequestError as e:
        st.error(f"❌ Cannot connect to MCP Server: {e}")
        return []
    except Exception as e:
        st.error(f"❌ Error fetching trade history: {e}")
        return []


def load_reflections(days=7):
    """讀取最近 N 天的 reflection 報告"""
    reflections = []
    
    if not REFLECTIONS_DIR.exists():
        return reflections
    
    for i in range(days):
        target_date = datetime.now() - timedelta(days=i)
        filename = f"reflection_{target_date.strftime('%Y-%m-%d')}.txt"
        filepath = REFLECTIONS_DIR / filename
        
        if filepath.exists():
            try:
                content = filepath.read_text(encoding='utf-8')
                reflections.append({
                    'date': target_date.strftime('%Y-%m-%d'),
                    'content': content,
                    'day_offset': i
                })
            except Exception as e:
                st.warning(f"Cannot read {filename}: {e}")
    
    return sorted(reflections, key=lambda x: x['date'])


def parse_reflection_insights(reflection_text):
    """從 reflection 文本中解析關鍵洞察"""
    insights = {
        'problem': '',
        'root_cause': '',
        'action': '',
        'result': '',
        'confidence': 0.0
    }
    
    # 簡單的文本解析（可以根據實際 reflection 格式調整）
    lines = reflection_text.split('\n')
    current_section = None
    
    for line in lines:
        line = line.strip()
        
        if 'MISTAKES:' in line or 'KEY OBSERVATIONS:' in line:
            current_section = 'problem'
        elif 'ROOT CAUSE' in line.upper():
            current_section = 'root_cause'
        elif 'ACTION' in line.upper() or 'TOMORROW:' in line:
            current_section = 'action'
        elif 'RESULT' in line.upper() or 'PERFORMANCE:' in line:
            current_section = 'result'
        elif current_section and line and not line.startswith('='):
            insights[current_section] += line + ' '
    
    # 清理多餘空格
    for key in insights:
        if isinstance(insights[key], str):
            insights[key] = insights[key].strip()
    
    return insights


def process_trades_to_daily(trades):
    """將交易列表處理成每日統計數據"""
    if not trades:
        return pd.DataFrame()
    
    # 轉換為 DataFrame
    df = pd.DataFrame(trades)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date
    
    # 計算每日統計
    daily_stats = []
    dates = sorted(df['date'].unique())
    
    for day_num, date in enumerate(dates, start=1):
        day_trades = df[df['date'] == date]
        
        # 基本統計
        total_trades = len(day_trades)
        wins = (day_trades['pnl'] > 0).sum()
        win_rate = wins / total_trades if total_trades > 0 else 0
        daily_pnl = day_trades['pnl'].sum() if 'pnl' in day_trades.columns else 0
        
        # Session 分析（如果有 market_context）
        asian_trades = []
        european_trades = []
        
        for _, trade in day_trades.iterrows():
            # 根據時間或 market_context 判斷 session
            hour = trade['timestamp'].hour
            if 0 <= hour < 10:  # Asian session (假設 UTC+8)
                asian_trades.append(trade)
            else:  # European/US session
                european_trades.append(trade)
        
        asian_count = len(asian_trades)
        european_count = len(european_trades)
        
        asian_pnl = sum(t['pnl'] for t in asian_trades) if asian_trades else 0
        european_pnl = sum(t['pnl'] for t in european_trades) if european_trades else 0
        
        asian_win_rate = sum(1 for t in asian_trades if t['pnl'] > 0) / asian_count if asian_count > 0 else 0
        european_win_rate = sum(1 for t in european_trades if t['pnl'] > 0) / european_count if european_count > 0 else 0
        
        daily_stats.append({
            'day': day_num,
            'date': str(date),
            'total_trades': total_trades,
            'win_rate': win_rate,
            'pnl': daily_pnl,
            'asian_trades': asian_count,
            'asian_win_rate': asian_win_rate,
            'asian_pnl': asian_pnl,
            'european_trades': european_count,
            'european_win_rate': european_win_rate,
            'european_pnl': european_pnl,
        })
    
    daily_df = pd.DataFrame(daily_stats)
    if not daily_df.empty:
        daily_df['cumulative_pnl'] = daily_df['pnl'].cumsum()
    
    return daily_df


def get_mock_data():
    """Fallback mock 數據（當 API 不可用時）"""
    
    # Day 1-7 每日數據
    daily_data = pd.DataFrame({
        'day': range(1, 8),
        'date': [(datetime.now() - timedelta(days=7-i)).strftime('%Y-%m-%d') for i in range(1, 8)],
        'total_trades': [5, 6, 5, 4, 5, 4, 4],
        'win_rate': [0.40, 0.33, 0.20, 0.50, 0.60, 0.75, 0.75],
        'pnl': [-120, -150, -90, 50, 80, 70, 60],
        'asian_trades': [3, 3, 2, 2, 2, 1, 1],
        'asian_win_rate': [0.33, 0.00, 0.00, 0.50, 0.50, 1.00, 1.00],
        'asian_pnl': [-90, -120, -60, -10, -5, 10, 5],
        'european_trades': [2, 3, 3, 2, 3, 3, 3],
        'european_win_rate': [0.50, 0.67, 0.33, 0.50, 0.67, 0.67, 0.67],
        'european_pnl': [-30, -30, -30, 60, 85, 60, 55],
    })
    
    # 累積損益
    daily_data['cumulative_pnl'] = daily_data['pnl'].cumsum()
    
    # Before/After 統計
    before_stats = {
        'period': 'Day 1-3 (Before)',
        'total_trades': daily_data[daily_data['day'] <= 3]['total_trades'].sum(),
        'win_rate': daily_data[daily_data['day'] <= 3]['win_rate'].mean(),
        'total_pnl': daily_data[daily_data['day'] <= 3]['pnl'].sum(),
        'asian_win_rate': 0.25,
        'european_win_rate': 0.67,
        'avg_asian_loss': -45,
        'lot_size_asian': 0.1,
        'lot_size_european': 0.1,
    }
    
    after_stats = {
        'period': 'Day 4-7 (After)',
        'total_trades': daily_data[daily_data['day'] > 3]['total_trades'].sum(),
        'win_rate': daily_data[daily_data['day'] > 3]['win_rate'].mean(),
        'total_pnl': daily_data[daily_data['day'] > 3]['pnl'].sum(),
        'asian_win_rate': 0.33,
        'european_win_rate': 0.70,
        'avg_asian_loss': -15,
        'lot_size_asian': 0.05,
        'lot_size_european': 0.1,
    }
    
    # Day 3 Reflection Insight
    reflection = {
        'day': 3,
        'trigger_time': '2026-02-23 23:59:00',
        'problem': 'Asian session shows 75% loss rate with -$360 total loss',
        'root_cause': 'Low liquidity causes frequent false breakouts',
        'action': 'Automatically reduced Asian session lot size from 0.1 to 0.05',
        'result': 'Day 4-7 Asian loss reduced by 67%, overall P&L turned positive',
        'pattern_id': 'asian_session_low_win_rate',
        'confidence': 0.85,
        'rule_activated': 'AR-001: Reduce Asian session lot size by 50%'
    }
    
    return daily_data, before_stats, after_stats, reflection


# ================== 主要內容 ==================

def main():
    # Sidebar
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        
        # API Status Check
        api_status = check_api_health()
        if api_status:
            st.success("✅ MCP Server Online")
        else:
            st.error("❌ MCP Server Offline")
            st.warning("Using mock data for demo")
        
        st.markdown("---")
        
        # Data Source Selection
        use_real_data = st.checkbox(
            "Use Real Data", 
            value=api_status,
            disabled=not api_status,
            help="Connect to MCP Server for real trade data"
        )
        
        days_to_show = st.slider("Days to Display", 3, 14, 7)
        
        st.markdown("---")
        st.markdown("## 📊 Quick Stats")
        
        # Quick refresh button
        if st.button("🔄 Refresh Data"):
            st.rerun()
    
    # 取得數據
    if use_real_data:
        with st.spinner("Loading real trade data..."):
            trades = fetch_trade_history(days=days_to_show)
            reflections = load_reflections(days=days_to_show)
            
            if trades:
                daily_data = process_trades_to_daily(trades)
                
                # 計算 Before/After（以中間天數分割）
                split_day = len(daily_data) // 2
                before_data = daily_data[daily_data['day'] <= split_day]
                after_data = daily_data[daily_data['day'] > split_day]
                
                before_stats = {
                    'period': f'Day 1-{split_day} (Before)',
                    'total_trades': before_data['total_trades'].sum(),
                    'win_rate': before_data['win_rate'].mean(),
                    'total_pnl': before_data['pnl'].sum(),
                    'asian_win_rate': before_data['asian_win_rate'].mean(),
                    'european_win_rate': before_data['european_win_rate'].mean(),
                    'avg_asian_loss': before_data['asian_pnl'].mean(),
                    'lot_size_asian': 0.1,  # TODO: Extract from actual trades
                    'lot_size_european': 0.1,
                }
                
                after_stats = {
                    'period': f'Day {split_day+1}-{len(daily_data)} (After)',
                    'total_trades': after_data['total_trades'].sum(),
                    'win_rate': after_data['win_rate'].mean(),
                    'total_pnl': after_data['pnl'].sum(),
                    'asian_win_rate': after_data['asian_win_rate'].mean(),
                    'european_win_rate': after_data['european_win_rate'].mean(),
                    'avg_asian_loss': after_data['asian_pnl'].mean(),
                    'lot_size_asian': 0.05,  # TODO: Extract from actual trades
                    'lot_size_european': 0.1,
                }
                
                # 解析 reflection insights
                if reflections:
                    # 取第一個有內容的 reflection
                    first_reflection = reflections[0]
                    insights = parse_reflection_insights(first_reflection['content'])
                    reflection = {
                        'day': split_day,
                        'trigger_time': first_reflection['date'] + ' 23:55:00',
                        'problem': insights.get('problem', 'N/A'),
                        'root_cause': insights.get('root_cause', 'N/A'),
                        'action': insights.get('action', 'N/A'),
                        'result': insights.get('result', 'N/A'),
                        'pattern_id': 'auto_detected',
                        'confidence': 0.75,
                        'rule_activated': 'Based on daily reflection analysis'
                    }
                else:
                    reflection = {
                        'day': split_day,
                        'trigger_time': 'N/A',
                        'problem': 'No reflection data available yet',
                        'root_cause': 'Waiting for daily reflection to run',
                        'action': 'Continue collecting trade data',
                        'result': 'Check back after 23:55 daily reflection',
                        'pattern_id': 'pending',
                        'confidence': 0.0,
                        'rule_activated': 'N/A'
                    }
            else:
                st.warning("⚠️ No trade data available. Using mock data for demo.")
                daily_data, before_stats, after_stats, reflection = get_mock_data()
    else:
        daily_data, before_stats, after_stats, reflection = get_mock_data()
    
    # Header
    st.markdown('<div class="main-header">🧠 Watch Your Agent Evolve</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">See how your trading agent learns from mistakes in just 7 days</div>', unsafe_allow_html=True)
    
    if not use_real_data:
        st.markdown("""
        <div class="warning-box">
            <strong>⚠️ Demo Mode</strong><br/>
            You're viewing mock data. Connect to MCP Server to see real trading data.
        </div>
        """, unsafe_allow_html=True)
    
    # ========== Section 1: Timeline View ==========
    st.markdown("---")
    st.markdown("## 📈 7-Day Evolution Timeline")
    
    if daily_data.empty:
        st.error("❌ No data available to display")
        return
    
    # 建立 Timeline 圖表
    fig_timeline = go.Figure()
    
    # 每日損益柱狀圖
    colors = ['red' if pnl < 0 else 'green' for pnl in daily_data['pnl']]
    fig_timeline.add_trace(go.Bar(
        x=daily_data['day'],
        y=daily_data['pnl'],
        name='Daily P&L',
        marker_color=colors,
        text=daily_data['pnl'].apply(lambda x: f'${x:+.0f}'),
        textposition='outside',
        hovertemplate='Day %{x}<br>P&L: $%{y:.0f}<extra></extra>'
    ))
    
    # 累積損益折線圖
    fig_timeline.add_trace(go.Scatter(
        x=daily_data['day'],
        y=daily_data['cumulative_pnl'],
        name='Cumulative P&L',
        mode='lines+markers',
        line=dict(color='blue', width=3),
        marker=dict(size=8),
        yaxis='y2',
        hovertemplate='Day %{x}<br>Cumulative: $%{y:.0f}<extra></extra>'
    ))
    
    # Reflection 標記（如果有）
    if reflection['day'] > 0:
        fig_timeline.add_vline(
            x=reflection['day'] + 0.5, 
            line_dash="dash", 
            line_color="purple", 
            annotation_text="💡 Reflection Triggered", 
            annotation_position="top"
        )
    
    fig_timeline.update_layout(
        title="Daily P&L and Cumulative Performance",
        xaxis_title="Day",
        yaxis_title="Daily P&L ($)",
        yaxis2=dict(title="Cumulative P&L ($)", overlaying='y', side='right'),
        hovermode='x unified',
        height=400,
        showlegend=True
    )
    
    st.plotly_chart(fig_timeline, use_container_width=True)
    
    # Timeline 說明
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**🔴 Learning Phase**")
        st.write("Agent trades normally, patterns emerge")
    with col2:
        st.markdown("**💡 Reflection**")
        st.write("ReflectionEngine detects patterns and suggests adaptations")
    with col3:
        st.markdown("**🟢 Adapted Strategy**")
        st.write("Performance improves based on learned insights")
    
    # ========== Section 2: Reflection Insight ==========
    st.markdown("---")
    st.markdown("## 💡 AI Reflection Insights")
    
    if reflection['confidence'] > 0:
        st.markdown(f"""
        <div class="insight-box">
            <div class="insight-title">🔍 What Did the Agent Learn?</div>
            <p><strong>Problem Detected:</strong><br/>"{reflection['problem']}"</p>
            <p><strong>Root Cause Analysis:</strong><br/>"{reflection['root_cause']}"</p>
            <p><strong>Action Taken:</strong><br/>"{reflection['action']}"</p>
            <p><strong>Result Achieved:</strong><br/>"{reflection['result']}"</p>
            <p style="margin-top: 1rem; opacity: 0.9;">
                <strong>Pattern ID:</strong> {reflection['pattern_id']}<br/>
                <strong>Confidence:</strong> {reflection['confidence']*100:.0f}%<br/>
                <strong>Trigger:</strong> {reflection['trigger_time']}
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("🔄 Waiting for reflection analysis. Check back after daily reflection runs at 23:55.")
    
    # ========== Section 3: Before vs After Comparison ==========
    st.markdown("---")
    st.markdown("## 📊 Before vs After: The Numbers Don't Lie")
    
    col_before, col_after = st.columns(2)
    
    with col_before:
        st.markdown(f"### 🔴 {before_stats['period']}")
        st.markdown('<div class="before-box">', unsafe_allow_html=True)
        st.metric("Total Trades", f"{before_stats['total_trades']}")
        st.metric("Win Rate", f"{before_stats['win_rate']*100:.0f}%")
        st.metric("Total P&L", f"${before_stats['total_pnl']:+.0f}", delta=None, delta_color="off")
        st.markdown("**Session Performance:**")
        st.write(f"- Asian Win Rate: {before_stats['asian_win_rate']*100:.0f}%")
        st.write(f"- European Win Rate: {before_stats['european_win_rate']*100:.0f}%")
        st.write(f"- Avg Asian P&L: ${before_stats['avg_asian_loss']:.0f}/trade")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col_after:
        st.markdown(f"### 🟢 {after_stats['period']}")
        st.markdown('<div class="after-box">', unsafe_allow_html=True)
        st.metric("Total Trades", f"{after_stats['total_trades']}")
        win_rate_delta = (after_stats['win_rate']-before_stats['win_rate'])*100
        st.metric("Win Rate", f"{after_stats['win_rate']*100:.0f}%", 
                 delta=f"{win_rate_delta:+.0f}%" if win_rate_delta != 0 else None)
        pnl_delta = after_stats['total_pnl']-before_stats['total_pnl']
        st.metric("Total P&L", f"${after_stats['total_pnl']:+.0f}",
                 delta=f"${pnl_delta:+.0f}" if pnl_delta != 0 else None)
        st.markdown("**Session Performance:**")
        st.write(f"- Asian Win Rate: {after_stats['asian_win_rate']*100:.0f}%")
        st.write(f"- European Win Rate: {after_stats['european_win_rate']*100:.0f}%")
        st.write(f"- Avg Asian P&L: ${after_stats['avg_asian_loss']:.0f}/trade")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # 改善總結
    if before_stats['win_rate'] > 0 and after_stats['win_rate'] > 0:
        st.markdown("### 🎯 Key Improvements")
        col1, col2, col3 = st.columns(3)
        
        win_rate_improvement = (after_stats['win_rate']-before_stats['win_rate'])*100
        col1.metric("Win Rate Change", f"{win_rate_improvement:+.0f}%")
        
        pnl_improvement = after_stats['total_pnl']-before_stats['total_pnl']
        col2.metric("P&L Change", f"${pnl_improvement:+.0f}")
        
        asian_improvement = ((after_stats['avg_asian_loss']-before_stats['avg_asian_loss'])/abs(before_stats['avg_asian_loss'])*100) if before_stats['avg_asian_loss'] != 0 else 0
        col3.metric("Asian Session Improvement", f"{asian_improvement:+.0f}%")
    
    # ========== Section 4: Session Heatmap ==========
    st.markdown("---")
    st.markdown("## 🔥 Session Performance Heatmap")
    
    # 建立 session heatmap 數據
    heatmap_data = []
    for _, row in daily_data.iterrows():
        heatmap_data.append({
            'Day': f"Day {row['day']}",
            'Session': 'Asian',
            'P&L': row['asian_pnl'],
            'Trades': row['asian_trades']
        })
        heatmap_data.append({
            'Day': f"Day {row['day']}",
            'Session': 'European',
            'P&L': row['european_pnl'],
            'Trades': row['european_trades']
        })
    
    heatmap_df = pd.DataFrame(heatmap_data)
    heatmap_pivot = heatmap_df.pivot(index='Session', columns='Day', values='P&L')
    
    # 使用 Plotly 建立熱力圖
    fig_heatmap = go.Figure(data=go.Heatmap(
        z=heatmap_pivot.values,
        x=heatmap_pivot.columns,
        y=heatmap_pivot.index,
        colorscale='RdYlGn',
        zmid=0,
        text=heatmap_pivot.values,
        texttemplate='$%{text:.0f}',
        textfont={"size": 12},
        colorbar=dict(title="P&L ($)")
    ))
    
    fig_heatmap.update_layout(
        title="P&L by Trading Session (Asian vs European)",
        xaxis_title="Day",
        yaxis_title="Session",
        height=300
    )
    
    st.plotly_chart(fig_heatmap, use_container_width=True)
    
    st.markdown("""
    **📝 Reading the heatmap:**
    - 🟢 Green = Profitable session
    - 🔴 Red = Losing session
    - The agent learns to adapt strategy based on session performance patterns
    """)
    
    # ========== Section 5: Raw Reflection Reports (if available) ==========
    if use_real_data:
        st.markdown("---")
        st.markdown("## 📄 Daily Reflection Reports")
        
        reflections = load_reflections(days=days_to_show)
        
        if reflections:
            for ref in reflections:
                with st.expander(f"📅 {ref['date']} Reflection Report"):
                    st.text(ref['content'])
        else:
            st.info("No reflection reports found. Reports are generated daily at 23:55.")
    
    # ========== Footer ==========
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #888; padding: 2rem 0;">
        <p>🧠 TradeMemory Protocol v0.1.0</p>
        <p>AI-Powered Trading Memory & Adaptive Decision Layer</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
