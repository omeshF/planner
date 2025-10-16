import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from icalendar import Calendar
import os
import json

# Optional: gspread for Google Sheets
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSHEETS_AVAILABLE = True
except ImportError:
    GSHEETS_AVAILABLE = False

# Page configuration
st.set_page_config(
    page_title="Hours Tracker & Calendar",
    page_icon="⏰",
    layout="wide"
)

# ==============================
# GOOGLE SHEETS INTEGRATION
# ==============================
def get_gsheets_client():
    if not GSHEETS_AVAILABLE:
        st.error("❌ gspread not installed. Add it to requirements.txt")
        st.stop()
    
    try:
        creds_info = st.secrets["google_sheets"]["credentials"]
        if isinstance(creds_info, str):
            creds_info = json.loads(creds_info)
        creds = Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"❌ Google Sheets auth failed: {e}")
        st.stop()

def load_sheet_data(worksheet_name):
    try:
        sheet_url = st.secrets["google_sheets"]["url"]
        gc = get_gsheets_client()
        sheet = gc.open_by_url(sheet_url)
        worksheet = sheet.worksheet(worksheet_name)
        return worksheet.get_all_records()
    except Exception as e:
        st.warning(f"⚠️ Could not load '{worksheet_name}': {e}")
        return []

def save_sheet_data(worksheet_name, data):
    try:
        sheet_url = st.secrets["google_sheets"]["url"]
        gc = get_gsheets_client()
        sheet = gc.open_by_url(sheet_url)
        try:
            worksheet = sheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=worksheet_name, rows="1000", cols="10")
        
        if not data:
            worksheet.clear()
            return
        
        df = pd.DataFrame(data)
        if worksheet_name == "modules":
            df = df[['id', 'name', 'total_hours']]
        elif worksheet_name == "entries":
            df = df[['week', 'module_id', 'hours']]
        
        worksheet.update([df.columns.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"❌ Failed to save '{worksheet_name}': {e}")

# ==============================
# DATA LOADING / SAVING (TEXT-BASED IDs)
# ==============================
def load_modules():
    records = load_sheet_data("modules")
    modules = []
    for r in records:
        try:
            mod_id = str(r['id']).strip()
            if not mod_id:
                continue
            modules.append({
                'id': mod_id,
                'name': str(r['name']).strip(),
                'total_hours': float(r['total_hours'])
            })
        except (ValueError, KeyError, TypeError) as e:
            st.warning(f"⚠️ Skipping invalid module row: {r}")
            continue
    return modules

def load_entries():
    records = load_sheet_data("entries")
    entries = []
    for r in records:
        try:
            if not r.get('week') or not r.get('module_id') or not r.get('hours'):
                continue
            entries.append({
                'week': int(float(r['week'])),
                'module_id': str(r['module_id']).strip(),
                'hours': float(r['hours'])
            })
        except (ValueError, KeyError, TypeError) as e:
            st.warning(f"⚠️ Skipping invalid entry row: {r}")
            continue
    return entries

def save_modules(modules):
    save_sheet_data("modules", modules)

def save_entries(entries):
    save_sheet_data("entries", entries)

# ==============================
# HELPER FUNCTIONS (UNCHANGED)
# ==============================
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

def add_module(module_code, name, hours):
    st.session_state.modules.append({
        'id': module_code,
        'name': name,
        'total_hours': hours
    })
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

# ==============================
# SESSION STATE INIT
# ==============================
if 'modules' not in st.session_state:
    st.session_state.modules = load_modules()
    st.session_state.entries = load_entries()

if 'page' not in st.session_state:
    st.session_state.page = 'modules'

if 'calendar_week_start' not in st.session_state:
    st.session_state.calendar_week_start = get_week_monday(datetime.today().date())

if 'selected_week' not in st.session_state:
    st.session_state.selected_week = get_week_number()

# ==============================
# NAVIGATION
# ==============================
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

# Persistent data notice
if st.session_state.page in ['modules', 'claim', 'reports']:
    st.info("✅ **Your data is saved permanently in Google Sheets!**")

# ==============================
# MAIN APP PAGES
# ==============================
if st.session_state.page == 'modules':
    st.title("📚 Module Management")
    st.write("Add and manage your university modules")
    
    st.markdown("---")
    st.subheader("➕ Add New Module")
    col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
    
    with col1:
        new_module_code = st.text_input("Module Code", placeholder="e.g., 6COM2008", key="new_code")
    with col2:
        new_module_name = st.text_input("Module Name", placeholder="e.g., IoT", key="new_name")
    with col3:
        new_module_hours = st.number_input("Total Hours", min_value=0.0, step=0.5, key="new_hours")
    with col4:
        st.write("")
        if st.button("Add Module", type="primary", use_container_width=True):
            if new_module_code and new_module_name and new_module_hours > 0:
                add_module(new_module_code, new_module_name, new_module_hours)
                st.success(f"✅ Added: {new_module_code} - {new_module_name}")
                st.rerun()
            else:
                st.error("Please fill all fields")
    
    st.markdown("---")
    st.subheader("📋 Your Modules")
    
    if not st.session_state.modules:
        st.info("No modules added yet.")
    else:
        module_stats = calculate_module_stats()
        for module in module_stats:
            with st.container():
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.markdown(f"**{module['id']}**")
                    st.caption(module['name'])
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
                        edit_code = st.text_input("Module Code", value=module['id'])
                        edit_name = st.text_input("Module Name", value=module['name'])
                        edit_hours = st.number_input("Total Hours", value=float(module['total_hours']), min_value=0.0, step=0.5)
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.form_submit_button("💾 Save", type="primary"):
                                # Update in place
                                for m in st.session_state.modules:
                                    if m['id'] == module['id']:
                                        m['id'] = edit_code
                                        m['name'] = edit_name
                                        m['total_hours'] = edit_hours
                                        break
                                save_modules(st.session_state.modules)
                                st.session_state[f'editing_{module["id"]}'] = False
                                st.rerun()
                        with col_cancel:
                            if st.form_submit_button("❌ Cancel"):
                                st.session_state[f'editing_{module["id"]}'] = False
                                st.rerun()
                st.markdown("---")

elif st.session_state.page == 'claim':
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
    st.progress(min(week_total / 37.5, 1.0))
    
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
                    st.markdown(f"**{module['id']} - {module['name']}**")
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
    if not st.session_state.entries:
        st.warning("No hours claimed yet.")
    else:
        df = create_detailed_report_df()
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Total Hours", f"{df['Hours'].sum():.1f}")
        with col2: st.metric("Weeks", df['Week'].nunique())
        with col3: st.metric("Modules", df['Module'].nunique())
        with col4: st.metric("Avg Weekly", f"{df.groupby('Week')['Hours'].sum().mean():.1f}")
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        all_weeks = sorted(df['Week'].unique())
        with col1: start_week = st.selectbox("From Week", all_weeks, index=0)
        with col2: end_week = st.selectbox("To Week", all_weeks, index=len(all_weeks)-1)
        filtered_df = df[(df['Week'] >= start_week) & (df['Week'] <= end_week)]
        
        st.markdown("---")
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Weekly", "🎯 By Module", "📉 Progress", "📅 Weekly x Module"])
        with tab1:
            weekly = filtered_df.groupby('Week')['Hours'].sum().reset_index()
            fig = go.Figure(go.Bar(x=weekly['Week'], y=weekly['Hours'], 
                                   marker_color=['red' if h>37.5 else 'green' for h in weekly['Hours']],
                                   text=weekly['Hours'].round(1), textposition='outside'))
            fig.add_hline(y=37.5, line_dash="dash", line_color="red")
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        with tab2:
            mod_data = filtered_df.groupby('Module')['Hours'].sum().reset_index()
            fig = px.pie(mod_data, values='Hours', names='Module')
            st.plotly_chart(fig, use_container_width=True)
        with tab3:
            stats = calculate_module_stats()
            dfp = pd.DataFrame(stats)
            fig = go.Figure()
            fig.add_bar(x=dfp['id'], y=dfp['claimed'], name='Claimed')
            fig.add_bar(x=dfp['id'], y=dfp['remaining'], name='Remaining')
            fig.update_layout(barmode='stack', height=400)
            st.plotly_chart(fig, use_container_width=True)
        with tab4:
            pivot = filtered_df.pivot_table(values='Hours', index='Week', columns='Module', fill_value=0)
            fig = go.Figure()
            for col in pivot.columns:
                fig.add_bar(x=pivot.index, y=pivot[col], name=col)
            fig.update_layout(barmode='stack', height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            csv = filtered_df.to_csv(index=False)
            st.download_button("📄 CSV", csv, f"report_{start_week}-{end_week}.csv", use_container_width=True)
        with col2:
            excel_data = to_excel(filtered_df)
            st.download_button("📊 Excel", excel_data, f"report_{start_week}-{end_week}.xlsx", use_container_width=True)
        st.dataframe(filtered_df.sort_values(['Week', 'Module']), use_container_width=True, hide_index=True)

else:
    # CALENDAR VIEWER — reads from calendar_data/ in Git
    st.title("📅 Calendar Viewer")
    CALENDAR_DIR = "calendar_data"
    if not os.path.exists(CALENDAR_DIR):
        st.error(f"❌ Folder `{CALENDAR_DIR}` not found in repo.")
        st.stop()
    ics_files = [f for f in os.listdir(CALENDAR_DIR) if f.endswith('.ics')]
    if not ics_files:
        st.warning(f"📁 No .ics files in `{CALENDAR_DIR}`.")
        st.stop()
    
    calendars = {}
    for filename in ics_files:
        try:
            with open(os.path.join(CALENDAR_DIR, filename), 'rb') as f:
                calendars[filename.replace('.ics', '')] = Calendar.from_ical(f.read())
        except Exception as e:
            st.warning(f"⚠️ Failed to load {filename}: {e}")
    
    if not calendars:
        st.error("❌ No valid calendars.")
        st.stop()
    
    all_events = []
    for src, cal in calendars.items():
        for comp in cal.walk():
            if comp.name == "VEVENT":
                dtstart, dtend = comp.get('dtstart'), comp.get('dtend')
                if not dtstart or not dtend: continue
                all_events.append({
                    'start': dtstart.dt,
                    'end': dtend.dt,
                    'summary': str(comp.get('summary', 'No Title')),
                    'is_allday': not isinstance(dtstart.dt, datetime),
                    'source': src
                })
    
    if not all_events:
        st.warning("📭 No events found.")
        st.stop()
    
    col1, col2, col3, col4 = st.columns([1, 2, 1, 1])
    with col1: 
        if st.button("◀ Previous Week"): 
            st.session_state.calendar_week_start -= timedelta(days=7); st.rerun()
    with col2:
        end = st.session_state.calendar_week_start + timedelta(days=6)
        st.markdown(f"### {st.session_state.calendar_week_start.strftime('%B %d')} – {end.strftime('%B %d, %Y')}")
    with col3: 
        if st.button("Next Week ▶"): 
            st.session_state.calendar_week_start += timedelta(days=7); st.rerun()
    with col4: 
        if st.button("Today"): 
            st.session_state.calendar_week_start = get_week_monday(datetime.today().date()); st.rerun()
    
    sources = sorted(set(e['source'] for e in all_events))
    st.markdown("---")
    cols = st.columns(min(len(sources), 4))
    for i, s in enumerate(sources):
        with cols[i % 4]:
            st.markdown(f"<span style='color:{get_source_color(s)}'>●</span> {get_source_icon(s)} **{s}**", unsafe_allow_html=True)
    
    st.markdown("---")
    current = st.session_state.calendar_week_start
    local_tz = datetime.now().astimezone().tzinfo
    for i in range(7):
        day_events = [e for e in all_events if (e['start'].date() if isinstance(e['start'], datetime) else e['start']) == current]
        day_events.sort(key=lambda x: (not x['is_allday'], x['start'].time() if isinstance(x['start'], datetime) else datetime.min.time()))
        with st.expander(f"{'🌅' if i>=5 else '📅'} {current.strftime('%A, %B %d')}", expanded=i<2):
            if not day_events:
                st.info("No events")
            else:
                for e in day_events:
                    color = get_source_color(e['source'])
                    icon = get_source_icon(e['source'])
                    if e['is_allday']:
                        time_str = "🕗 All-day"
                    else:
                        start = e['start'].replace(tzinfo=local_tz) if e['start'].tzinfo is None else e['start'].astimezone(local_tz)
                        end = e['end'].replace(tzinfo=local_tz) if isinstance(e['end'], datetime) and e['end'].tzinfo is None else (e['end'].astimezone(local_tz) if isinstance(e['end'], datetime) else e['end'])
                        time_str = f"🕒 {start.strftime('%H:%M')} - {end.strftime('%H:%M') if isinstance(end, datetime) else '??:??'}"
                    st.markdown(f"<div style='background-color:{color}22;padding:10px;border-left:4px solid {color};border-radius:4px;margin-bottom:8px;'><strong style='color:{color}'>{icon} {e['source']}</strong> | {time_str}<br><span>{e['summary']}</span></div>", unsafe_allow_html=True)
        current += timedelta(days=1)
    
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Events", len(all_events))
    with col2: st.metric("Calendars", len(calendars))
    with col3: st.metric("All-day", sum(1 for e in all_events if e['is_allday']))
    
    if st.button("🔄 Reload Calendars from GitHub"):
        st.cache_data.clear()
        st.rerun()