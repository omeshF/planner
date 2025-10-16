import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from icalendar import Calendar
import os

# Page configuration
st.set_page_config(
    page_title="Hours Tracker & Calendar",
    page_icon="⏰",
    layout="wide"
)

# Initialize Google Sheets connection
@st.cache_resource
def get_connection():
    return st.connection("gsheets", type="gsheets")

conn = get_connection()

def load_modules():
    try:
        df = conn.read(worksheet="modules", ttl=0)
        if df.empty:
            return [], 1
        df = df.astype({'id': 'int64', 'total_hours': 'float64'})
        modules = df.to_dict('records')
        next_id = df['id'].max() + 1 if not df.empty else 1
        return modules, next_id
    except Exception as e:
        st.warning(f"⚠️ Could not load modules: {e}")
        return [], 1

def load_entries():
    try:
        df = conn.read(worksheet="entries", ttl=0)
        if df.empty:
            return []
        df = df.astype({'week': 'int64', 'module_id': 'int64', 'hours': 'float64'})
        return df.to_dict('records')
    except Exception as e:
        st.warning(f"⚠️ Could not load entries: {e}")
        return []

def save_modules(modules):
    if modules:
        df = pd.DataFrame(modules)
        conn.update(worksheet="modules", data=df)
    else:
        # Clear sheet
        conn.update(worksheet="modules", data=pd.DataFrame())

def save_entries(entries):
    if entries:
        df = pd.DataFrame(entries)
        conn.update(worksheet="entries", data=df)
    else:
        conn.update(worksheet="entries", data=pd.DataFrame())

def get_source_color(source):
    color_map = {
        'gmail': '#EA4335',
        'google': '#EA4335',
        'samsung': '#1428A0',
        'outlook': '#0078D4',
        'apple': '#555555',
        'icloud': '#555555',
    }
    source_lower = source.lower()
    for key, color in color_map.items():
        if key in source_lower:
            return color
    import hashlib
    hash_obj = hashlib.md5(source.encode())
    return f"#{hash_obj.hexdigest()[:6]}"

def get_source_icon(source):
    source_lower = source.lower()
    if 'gmail' in source_lower or 'google' in source_lower:
        return '📧'
    elif 'samsung' in source_lower:
        return '📱'
    elif 'outlook' in source_lower:
        return '📨'
    elif 'apple' in source_lower or 'icloud' in source_lower:
        return '🍎'
    else:
        return '📅'

def get_week_monday(any_date):
    return any_date - timedelta(days=any_date.weekday())

# Initialize session state
if 'modules' not in st.session_state:
    modules, next_id = load_modules()
    entries = load_entries()
    st.session_state.modules = modules
    st.session_state.entries = entries
    st.session_state.next_id = next_id

if 'page' not in st.session_state:
    st.session_state.page = 'modules'

if 'calendar_week_start' not in st.session_state:
    st.session_state.calendar_week_start = get_week_monday(datetime.today().date())

def get_week_number():
    return datetime.now().isocalendar()[1]

def get_week_dates(year, week_num):
    jan_1 = datetime(year, 1, 1)
    week_start = jan_1 + timedelta(days=(week_num - 1) * 7)
    monday = week_start - timedelta(days=week_start.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday

def calculate_module_stats():
    stats = []
    for module in st.session_state.modules:
        claimed = sum(e['hours'] for e in st.session_state.entries if e['module_id'] == module['id'])
        stats.append({
            **module,
            'claimed': claimed,
            'remaining': module['total_hours'] - claimed
        })
    return stats

def calculate_week_total(week_num):
    return sum(e['hours'] for e in st.session_state.entries if e['week'] == week_num)

def add_module(name, hours):
    st.session_state.modules.append({
        'id': st.session_state.next_id,
        'name': name,
        'total_hours': hours
    })
    st.session_state.next_id += 1
    save_modules(st.session_state.modules)

def delete_module(module_id):
    st.session_state.modules = [m for m in st.session_state.modules if m['id'] != module_id]
    st.session_state.entries = [e for e in st.session_state.entries if e['module_id'] != module_id]
    save_modules(st.session_state.modules)
    save_entries(st.session_state.entries)

def update_module(module_id, name, hours):
    for module in st.session_state.modules:
        if module['id'] == module_id:
            module['name'] = name
            module['total_hours'] = hours
            break
    save_modules(st.session_state.modules)

def add_or_update_entry(week, module_id, hours):
    entry_idx = None
    for idx, e in enumerate(st.session_state.entries):
        if e['week'] == week and e['module_id'] == module_id:
            entry_idx = idx
            break
    
    if hours == 0:
        if entry_idx is not None:
            st.session_state.entries.pop(entry_idx)
    else:
        if entry_idx is not None:
            st.session_state.entries[entry_idx]['hours'] = hours
        else:
            st.session_state.entries.append({
                'week': week,
                'module_id': module_id,
                'hours': hours
            })
    save_entries(st.session_state.entries)

def get_entry_hours(week, module_id):
    for e in st.session_state.entries:
        if e['week'] == week and e['module_id'] == module_id:
            return e['hours']
    return 0.0

def get_module_name(module_id):
    for m in st.session_state.modules:
        if m['id'] == module_id:
            return m['name']
    return "Unknown Module"

def create_detailed_report_df():
    data = []
    for entry in st.session_state.entries:
        module_name = get_module_name(entry['module_id'])
        year = datetime.now().year
        monday, sunday = get_week_dates(year, entry['week'])
        data.append({
            'Week': entry['week'],
            'Week Start': monday.strftime('%Y-%m-%d'),
            'Week End': sunday.strftime('%Y-%m-%d'),
            'Module': module_name,
            'Hours': entry['hours']
        })
    return pd.DataFrame(data)

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Hours Report')
    return output.getvalue()

# Navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["📚 Modules", "⏰ Claim Hours", "📊 Reports", "📅 Calendar Viewer"])

if page == "📚 Modules":
    st.session_state.page = 'modules'
elif page == "⏰ Claim Hours":
    st.session_state.page = 'claim'
elif page == "📊 Reports":
    st.session_state.page = 'reports'
else:
    st.session_state.page = 'calendar'

# Persistent data warning
if st.session_state.page in ['modules', 'claim', 'reports']:
    st.info("✅ **Your data is now saved permanently in Google Sheets!** Changes persist across sessions.")

# Main App
if st.session_state.page == 'modules':
    st.title("📚 Module Management")
    st.write("Add and manage your university modules")
    
    st.markdown("---")
    
    st.subheader("➕ Add New Module")
    col1, col2, col3 = st.columns([3, 2, 1])
    
    with col1:
        new_module_name = st.text_input("Module Name", placeholder="e.g., CS101 - Introduction to Programming", key="new_name")
    with col2:
        new_module_hours = st.number_input("Total Hours Allocated", min_value=0.0, step=0.5, key="new_hours")
    with col3:
        st.write("")
        st.write("")
        if st.button("Add Module", type="primary", use_container_width=True):
            if new_module_name and new_module_hours > 0:
                add_module(new_module_name, new_module_hours)
                st.success(f"✅ Added: {new_module_name}")
                st.rerun()
            else:
                st.error("Please enter both module name and hours")
    
    st.markdown("---")
    
    st.subheader("📋 Your Modules")
    
    if not st.session_state.modules:
        st.info("No modules added yet. Add your first module above!")
    else:
        module_stats = calculate_module_stats()
        
        for module in module_stats:
            with st.container():
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    st.markdown(f"**{module['name']}**")
                    st.caption(f"Total Allocated: {module['total_hours']} hours")
                
                with col2:
                    progress_pct = min(module['claimed'] / module['total_hours'], 1.0) if module['total_hours'] > 0 else 0
                    st.progress(progress_pct)
                    st.caption(f"Claimed: {module['claimed']:.1f}h | Remaining: {module['remaining']:.1f}h")
                
                with col3:
                    col_edit, col_del = st.columns(2)
                    with col_edit:
                        if st.button("✏️", key=f"edit_{module['id']}", help="Edit"):
                            st.session_state[f'editing_{module["id"]}'] = True
                    with col_del:
                        if st.button("🗑️", key=f"del_{module['id']}", help="Delete"):
                            delete_module(module['id'])
                            st.rerun()
                
                if st.session_state.get(f'editing_{module["id"]}', False):
                    with st.form(key=f'form_{module["id"]}'):
                        edit_name = st.text_input("Module Name", value=module['name'])
                        edit_hours = st.number_input("Total Hours", value=float(module['total_hours']), min_value=0.0, step=0.5)
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.form_submit_button("💾 Save", type="primary"):
                                update_module(module['id'], edit_name, edit_hours)
                                st.session_state[f'editing_{module["id"]}'] = False
                                st.rerun()
                        with col_cancel:
                            if st.form_submit_button("❌ Cancel"):
                                st.session_state[f'editing_{module["id"]}'] = False
                                st.rerun()
                
                st.markdown("---")

elif st.session_state.page == 'claim':
    if 'selected_week' not in st.session_state:
        st.session_state.selected_week = get_week_number()
    
    st.title("⏰ Claim Hours")
    st.write("Log your weekly hours by module")
    
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns([1, 3, 1, 1])
    
    with col1:
        if st.button("◀ Previous"):
            st.session_state.selected_week = max(1, st.session_state.selected_week - 1)
            st.rerun()
    
    with col2:
        current_year = datetime.now().year
        monday, sunday = get_week_dates(current_year, st.session_state.selected_week)
        st.markdown(f"### 📅 Week {st.session_state.selected_week}")
        st.caption(f"{monday.strftime('%d %b')} - {sunday.strftime('%d %b %Y')}")
    
    with col3:
        if st.button("Next ▶"):
            st.session_state.selected_week += 1
            st.rerun()
    
    with col4:
        if st.button("Today"):
            st.session_state.selected_week = get_week_number()
            st.rerun()
    
    week_total = calculate_week_total(st.session_state.selected_week)
    is_over_limit = week_total > 37.5
    
    st.markdown("---")
    
    if is_over_limit:
        st.error(f"⚠️ **{week_total:.1f} / 37.5 hours** - Weekly limit exceeded!")
    else:
        st.success(f"✅ **{week_total:.1f} / 37.5 hours**")
    
    progress = min(week_total / 37.5, 1.0)
    st.progress(progress)
    
    st.markdown("---")
    
    st.subheader("📝 Enter Hours by Module")
    
    if not st.session_state.modules:
        st.warning("No modules available. Please add modules first.")
    else:
        module_stats = calculate_module_stats()
        
        for module in module_stats:
            with st.container():
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"**{module['name']}**")
                    st.caption(f"Remaining: {module['remaining']:.1f} hrs of {module['total_hours']} hrs")
                
                with col2:
                    current_saved = get_entry_hours(st.session_state.selected_week, module['id'])
                    
                    input_key = f"input_hours_{module['id']}"
                    if input_key not in st.session_state:
                        st.session_state[input_key] = float(current_saved)
                    
                    temp_hours = st.number_input(
                        "Hours",
                        min_value=0.0,
                        max_value=200.0,
                        value=st.session_state[input_key],
                        step=0.5,
                        key=f"ni_{module['id']}",
                        label_visibility="collapsed"
                    )
                    st.session_state[input_key] = temp_hours

                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("✅ Claim", key=f"claim_{module['id']}", use_container_width=True):
                            add_or_update_entry(st.session_state.selected_week, module['id'], temp_hours)
                            st.rerun()
                    with btn_col2:
                        if st.button("🔄 Reset", key=f"reset_{module['id']}", use_container_width=True):
                            st.session_state[input_key] = float(current_saved)
                            st.rerun()
                
                st.markdown("---")
        
        if is_over_limit:
            st.warning("⚠️ Remember: You cannot claim more than 37.5 hours per week!")

elif st.session_state.page == 'reports':
    st.title("📊 Reports & Analytics")
    st.write("View detailed reports and export your data")
    
    if not st.session_state.entries:
        st.warning("No hours claimed yet. Start claiming hours to see reports!")
    else:
        df = create_detailed_report_df()
        
        st.markdown("---")
        st.subheader("📈 Summary Statistics")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Hours Claimed", f"{df['Hours'].sum():.1f}")
        with col2:
            st.metric("Weeks Tracked", df['Week'].nunique())
        with col3:
            st.metric("Active Modules", df['Module'].nunique())
        with col4:
            avg_weekly = df.groupby('Week')['Hours'].sum().mean()
            st.metric("Avg Weekly Hours", f"{avg_weekly:.1f}")
        
        st.markdown("---")
        
        st.subheader("🔍 Filter by Date Range")
        col1, col2 = st.columns(2)
        all_weeks = sorted(df['Week'].unique())
        with col1:
            start_week = st.selectbox("From Week", all_weeks, index=0)
        with col2:
            end_week = st.selectbox("To Week", all_weeks, index=len(all_weeks)-1)
        
        filtered_df = df[(df['Week'] >= start_week) & (df['Week'] <= end_week)]
        
        st.markdown("---")
        
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Weekly Hours", "🎯 Module Breakdown", "📉 Module Progress", "📅 Weekly by Module"])
        
        with tab1:
            weekly_data = filtered_df.groupby('Week')['Hours'].sum().reset_index()
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=weekly_data['Week'],
                y=weekly_data['Hours'],
                marker_color=['red' if h > 37.5 else 'green' for h in weekly_data['Hours']],
                text=weekly_data['Hours'].round(1),
                textposition='outside'
            ))
            fig.add_hline(y=37.5, line_dash="dash", line_color="red", annotation_text="37.5 hr limit")
            fig.update_layout(xaxis_title="Week Number", yaxis_title="Hours", showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)
            over_limit = weekly_data[weekly_data['Hours'] > 37.5]
            if not over_limit.empty:
                st.warning(f"⚠️ {len(over_limit)} week(s) exceeded the 37.5 hour limit!")
        
        with tab2:
            module_data = filtered_df.groupby('Module')['Hours'].sum().reset_index()
            fig = px.pie(module_data, values='Hours', names='Module', title='Total Hours Distribution by Module')
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(module_data.sort_values('Hours', ascending=False), use_container_width=True, hide_index=True)
        
        with tab3:
            module_stats = calculate_module_stats()
            progress_df = pd.DataFrame(module_stats)
            fig = go.Figure()
            fig.add_trace(go.Bar(name='Claimed', x=progress_df['name'], y=progress_df['claimed'], marker_color='lightblue'))
            fig.add_trace(go.Bar(name='Remaining', x=progress_df['name'], y=progress_df['remaining'], marker_color='lightgray'))
            fig.update_layout(barmode='stack', xaxis_title="Module", yaxis_title="Hours", height=400)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                progress_df[['name', 'claimed', 'total_hours', 'remaining']]
                .rename(columns={'name': 'Module', 'claimed': 'Claimed (hrs)', 'total_hours': 'Total (hrs)', 'remaining': 'Remaining (hrs)'}),
                use_container_width=True,
                hide_index=True
            )
        
        with tab4:
            pivot_data = filtered_df.pivot_table(values='Hours', index='Week', columns='Module', aggfunc='sum', fill_value=0)
            fig = go.Figure()
            for module in pivot_data.columns:
                fig.add_trace(go.Bar(name=module, x=pivot_data.index, y=pivot_data[module]))
            fig.update_layout(barmode='stack', xaxis_title="Week Number", yaxis_title="Hours", height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        
        st.subheader("📥 Export Data")
        col1, col2 = st.columns(2)
        with col1:
            csv = filtered_df.to_csv(index=False)
            st.download_button("📄 Download as CSV", csv, f"hours_report_{start_week}_to_{end_week}.csv", "text/csv", use_container_width=True)
        with col2:
            excel_data = to_excel(filtered_df)
            st.download_button("📊 Download as Excel", excel_data, f"hours_report_{start_week}_to_{end_week}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        
        st.markdown("---")
        st.subheader("📋 Detailed Hours Log")
        st.dataframe(filtered_df.sort_values(['Week', 'Module']), use_container_width=True, hide_index=True)

else:
    # CALENDAR VIEWER — reads from calendar_data/ folder in Git
    st.title("📅 Calendar Viewer")
    st.write("Displays all `.ics` files from the `calendar_data/` folder in your GitHub repo")

    st.markdown("---")

    CALENDAR_DIR = "calendar_data"
    if not os.path.exists(CALENDAR_DIR):
        st.error(f"❌ The folder `{CALENDAR_DIR}` does not exist. Please add it to your GitHub repository with your .ics files.")
        st.stop()

    ics_files = [f for f in os.listdir(CALENDAR_DIR) if f.endswith('.ics')]
    if not ics_files:
        st.warning(f"📁 No `.ics` files found in `{CALENDAR_DIR}`. Add calendar files (e.g., `work.ics`, `uni.ics`) to this folder in your GitHub repo.")
        st.stop()

    # Load calendars
    calendars = {}
    load_errors = []
    for filename in ics_files:
        filepath = os.path.join(CALENDAR_DIR, filename)
        source_name = filename.replace('.ics', '')
        try:
            with open(filepath, 'rb') as f:
                cal = Calendar.from_ical(f.read())
            calendars[source_name] = cal
        except Exception as e:
            load_errors.append(f"{filename}: {str(e)}")

    if load_errors:
        st.warning("⚠️ Some calendars failed to load:")
        for err in load_errors:
            st.caption(f"- {err}")

    if not calendars:
        st.error("❌ No valid calendars could be loaded.")
        st.stop()

    # Extract all events
    all_events = []
    for source_name, cal in calendars.items():
        for component in cal.walk():
            if component.name == "VEVENT":
                dtstart = component.get('dtstart')
                dtend = component.get('dtend')
                if not dtstart or not dtend:
                    continue
                summary = str(component.get('summary', 'No Title'))
                start = dtstart.dt
                end = dtend.dt
                is_allday = not isinstance(start, datetime)
                all_events.append({
                    'start': start,
                    'end': end,
                    'summary': summary,
                    'is_allday': is_allday,
                    'source': source_name
                })

    if not all_events:
        st.warning("📭 No events found in any calendar.")
        st.stop()

    # Week navigation with TODAY
    col1, col2, col3, col4 = st.columns([1, 2, 1, 1])
    with col1:
        if st.button("◀ Previous Week", key="cal_prev"):
            st.session_state.calendar_week_start -= timedelta(days=7)
            st.rerun()
    with col2:
        week_end = st.session_state.calendar_week_start + timedelta(days=6)
        st.markdown(f"### {st.session_state.calendar_week_start.strftime('%B %d')} – {week_end.strftime('%B %d, %Y')}")
    with col3:
        if st.button("Next Week ▶", key="cal_next"):
            st.session_state.calendar_week_start += timedelta(days=7)
            st.rerun()
    with col4:
        if st.button("Today", key="cal_today"):
            st.session_state.calendar_week_start = get_week_monday(datetime.today().date())
            st.rerun()

    # Legend
    unique_sources = sorted(set(e['source'] for e in all_events))
    st.markdown("---")
    st.markdown("**Calendar Sources:**")
    cols = st.columns(min(len(unique_sources), 4))
    for idx, source in enumerate(unique_sources):
        with cols[idx % 4]:
            icon = get_source_icon(source)
            color = get_source_color(source)
            st.markdown(f"<span style='color: {color};'>●</span> {icon} **{source}**", unsafe_allow_html=True)

    st.markdown("---")

    # Display week
    current_day = st.session_state.calendar_week_start
    local_tz = datetime.now().astimezone().tzinfo

    for i in range(7):
        target_date = current_day
        day_events = [
            e for e in all_events
            if (e['start'].date() if isinstance(e['start'], datetime) else e['start']) == target_date
        ]
        day_events.sort(key=lambda x: (
            not x['is_allday'],
            x['start'].time() if isinstance(x['start'], datetime) else datetime.min.time()
        ))

        day_name = current_day.strftime("%A, %B %d")
        is_weekend = i >= 5
        with st.expander(f"{'🌅 ' if is_weekend else '📅 '}{day_name}", expanded=(i < 2)):
            if not day_events:
                st.info("No events scheduled")
            else:
                for e in day_events:
                    source = e['source']
                    color = get_source_color(source)
                    icon = get_source_icon(source)
                    if e['is_allday']:
                        time_str = "🕗 All-day"
                    else:
                        start_disp = e['start']
                        end_disp = e['end']
                        if isinstance(start_disp, datetime) and start_disp.tzinfo is None:
                            start_disp = start_disp.replace(tzinfo=local_tz)
                        if isinstance(end_disp, datetime) and end_disp.tzinfo is None:
                            end_disp = end_disp.replace(tzinfo=local_tz)
                        start_time = start_disp.strftime("%H:%M")
                        end_time = end_disp.strftime("%H:%M") if isinstance(end_disp, datetime) else "??:??"
                        time_str = f"🕒 {start_time} - {end_time}"
                    st.markdown(
                        f"<div style='background-color: {color}22; padding: 10px; border-left: 4px solid {color}; margin-bottom: 8px; border-radius: 4px;'>"
                        f"<strong style='color: {color};'>{icon} {source}</strong> | {time_str}<br/>"
                        f"<span style='color: #333;'>{e['summary']}</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
        current_day += timedelta(days=1)

    # Stats
    st.markdown("---")
    st.subheader("📊 Calendar Statistics")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Events", len(all_events))
    with col2:
        st.metric("Calendars", len(calendars))
    with col3:
        allday_count = sum(1 for e in all_events if e['is_allday'])
        st.metric("All-day Events", allday_count)

    # Optional: Force reload (useful after Git update)
    st.markdown("---")
    if st.button("🔄 Reload Calendars from GitHub", help="Click after updating calendar_data in your repo"):
        st.cache_data.clear()
        st.rerun()