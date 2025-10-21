import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from icalendar import Calendar
import json

# Optional: Google integrations
try:
    import gspread
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
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
# GOOGLE SHEETS: LOAD/SAVE DATA
# ==============================
def get_google_credentials(scopes):
    creds_info = st.secrets["google_sheets"]["credentials"]
    if isinstance(creds_info, str):
        creds_info = json.loads(creds_info)
    return Credentials.from_service_account_info(creds_info, scopes=scopes)

def load_sheet_data(worksheet_name):
    try:
        sheet_url = st.secrets["google_sheets"]["url"]
        creds = get_google_credentials(["https://www.googleapis.com/auth/spreadsheets"])
        gc = gspread.authorize(creds)
        sheet = gc.open_by_url(sheet_url)
        worksheet = sheet.worksheet(worksheet_name)
        return worksheet.get_all_records()
    except Exception as e:
        st.warning(f"⚠️ Could not load '{worksheet_name}': {e}")
        return []

def save_sheet_data(worksheet_name, data):
    try:
        sheet_url = st.secrets["google_sheets"]["url"]
        creds = get_google_credentials(["https://www.googleapis.com/auth/spreadsheets"])
        gc = gspread.authorize(creds)
        sheet = gc.open_by_url(sheet_url)
        try:
            worksheet = sheet.worksheet(worksheet_name)
        except Exception:
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
# GOOGLE DRIVE: LOAD CALENDARS
# ==============================
def load_calendars_from_drive():
    try:
        folder_id = st.secrets["google_drive"]["folder_id"]
        creds = get_google_credentials(["https://www.googleapis.com/auth/drive.readonly"])
        service = build("drive", "v3", credentials=creds)
        
        query = f"'{folder_id}' in parents and name contains '.ics' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])
        
        calendars = {}
        for file in files:
            file_id = file["id"]
            file_name = file["name"]
            request = service.files().get_media(fileId=file_id)
            content = request.execute().decode("utf-8")
            cal = Calendar.from_ical(content)
            source_name = file_name.replace(".ics", "")
            calendars[source_name] = cal
        return calendars
    except Exception as e:
        st.error(f"❌ Failed to load calendars from Google Drive: {e}")
        return {}

# ==============================
# DATA LOADING (TEXT IDs)
# ==============================
def load_modules():
    records = load_sheet_data("modules")
    modules = []
    for r in records:
        try:
            mod_id = str(r['id']).strip()
            if not mod_id: continue
            modules.append({
                'id': mod_id,
                'name': str(r['name']).strip(),
                'total_hours': float(r['total_hours'])
            })
        except Exception:
            st.warning(f"⚠️ Skipping invalid module: {r}")
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
        except Exception:
            st.warning(f"⚠️ Skipping invalid entry: {r}")
            continue
    return entries

def save_modules(modules):
    save_sheet_data("modules", modules)

def save_entries(entries):
    save_sheet_data("entries", entries)

# ==============================
# HELPER FUNCTIONS
# ==============================
def get_source_color(source):
    color_map = {'gmail': '#EA4335', 'samsung': '#1428A0', 'outlook': '#0078D4', 'apple': '#555555'}
    source_lower = source.lower()
    for key, color in color_map.items():
        if key in source_lower:
            return color
    import hashlib
    return f"#{hashlib.md5(source.encode()).hexdigest()[:6]}"

def get_source_icon(source):
    s = source.lower()
    return '📧' if 'gmail' in s or 'google' in s else '📱' if 'samsung' in s else '📨' if 'outlook' in s else '🍎' if 'apple' in s or 'icloud' in s else '📅'

def get_week_monday(d): return d - timedelta(days=d.weekday())
def get_week_number(): return datetime.now().isocalendar()[1]
def get_week_dates(year, week): 
    jan1 = datetime(year, 1, 1)
    return (jan1 + timedelta(days=(week - 1) * 7 - jan1.weekday()), 
            jan1 + timedelta(days=(week - 1) * 7 - jan1.weekday() + 6))

def calculate_module_stats():
    return [{**m, 'claimed': sum(e['hours'] for e in st.session_state.entries if e['module_id'] == m['id']),
             'remaining': m['total_hours'] - sum(e['hours'] for e in st.session_state.entries if e['module_id'] == m['id'])}
            for m in st.session_state.modules]

def calculate_week_total(w): return sum(e['hours'] for e in st.session_state.entries if e['week'] == w)
def get_entry_hours(w, mid): return next((e['hours'] for e in st.session_state.entries if e['week'] == w and e['module_id'] == mid), 0.0)
def get_module_name(mid): return next((m['name'] for m in st.session_state.modules if m['id'] == mid), "Unknown")

def add_module(code, name, hours):
    st.session_state.modules.append({'id': code, 'name': name, 'total_hours': hours})
    save_modules(st.session_state.modules)

def delete_module(mid):
    st.session_state.modules = [m for m in st.session_state.modules if m['id'] != mid]
    st.session_state.entries = [e for e in st.session_state.entries if e['module_id'] != mid]
    save_modules(st.session_state.modules); save_entries(st.session_state.entries)

def update_module(mid, name, hours):
    for m in st.session_state.modules:
        if m['id'] == mid:
            m.update({'name': name, 'total_hours': hours})
    save_modules(st.session_state.modules)

def add_or_update_entry(week, mid, hours):
    for e in st.session_state.entries:
        if e['week'] == week and e['module_id'] == mid:
            if hours == 0:
                st.session_state.entries.remove(e)
            else:
                e['hours'] = hours
            save_entries(st.session_state.entries)
            return
    if hours > 0:
        st.session_state.entries.append({'week': week, 'module_id': mid, 'hours': hours})
        save_entries(st.session_state.entries)

def create_detailed_report_df():
    data = []
    for e in st.session_state.entries:
        year = datetime.now().year
        monday, _ = get_week_dates(year, e['week'])
        data.append({
            'Week': e['week'],
            'Week Start': monday.strftime('%Y-%m-%d'),
            'Week End': (monday + timedelta(days=6)).strftime('%Y-%m-%d'),
            'Module': get_module_name(e['module_id']),
            'Hours': e['hours']
        })
    return pd.DataFrame(data)

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as w: df.to_excel(w, index=False)
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
st.session_state.page = {'📚 Modules': 'modules', '⏰ Claim Hours': 'claim', '📊 Reports': 'reports', '📅 Calendar Viewer': 'calendar'}[page]

if st.session_state.page in ['modules', 'claim', 'reports']:
    st.info("✅ Data saved securely in Google Sheets")

# ==============================
# MAIN APP
# ==============================
if st.session_state.page == 'modules':
    st.title("📚 Module Management")
    st.markdown("---")
    col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
    with col1: code = st.text_input("Module Code", placeholder="e.g., 6COM2008")
    with col2: name = st.text_input("Module Name", placeholder="e.g., IoT")
    with col3: hours = st.number_input("Total Hours", min_value=0.0, step=0.5)
    with col4: 
        st.write(""); 
        if st.button("Add Module", type="primary"):
            if code and name and hours > 0:
                add_module(code, name, hours)
                st.success(f"✅ Added: {code} - {name}")
                st.rerun()
    
    st.markdown("---")
    if not st.session_state.modules:
        st.info("No modules added yet.")
    else:
        for m in calculate_module_stats():
            with st.container():
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1: st.markdown(f"**{m['id']}**"); st.caption(m['name'])
                with col2: 
                    pct = min(m['claimed'] / m['total_hours'], 1) if m['total_hours'] > 0 else 0
                    st.progress(pct)
                    st.caption(f"Claimed: {m['claimed']:.1f}h | Remaining: {m['remaining']:.1f}h")
                with col3:
                    if st.button("✏️", key=f"edit_{m['id']}"): st.session_state[f'editing_{m["id"]}'] = True
                    if st.button("🗑️", key=f"del_{m['id']}"): delete_module(m['id']); st.rerun()
                
                if st.session_state.get(f'editing_{m["id"]}', False):
                    with st.form(f'form_{m["id"]}'):
                        e_code = st.text_input("Code", m['id'])
                        e_name = st.text_input("Name", m['name'])
                        e_hours = st.number_input("Hours", float(m['total_hours']), min_value=0.0, step=0.5)
                        if st.form_submit_button("💾 Save", type="primary"):
                            for mod in st.session_state.modules:
                                if mod['id'] == m['id']:
                                    mod.update({'id': e_code, 'name': e_name, 'total_hours': e_hours})
                            save_modules(st.session_state.modules)
                            st.session_state[f'editing_{m["id"]}'] = False
                            st.rerun()
                        if st.form_submit_button("❌ Cancel"):
                            st.session_state[f'editing_{m["id"]}'] = False
                            st.rerun()
                st.markdown("---")

elif st.session_state.page == 'claim':
    st.title("⏰ Claim Hours")
    st.markdown("---")
    
    # Date input instead of week navigation
    st.subheader("📅 Select Date")
    col1, col2 = st.columns([3, 1])
    with col1:
        # Default to today
        default_date = datetime.today().date()
        selected_date = st.date_input(
            "Choose a date to log hours for",
            value=default_date,
            max_value=datetime.today().date(),  # Prevent future dates
            label_visibility="collapsed"
        )
    with col2:
        if st.button("📆 Today", use_container_width=True):
            st.session_state.claim_date = datetime.today().date()
            st.rerun()
    
    # Auto-calculate week from selected date
    selected_week = selected_date.isocalendar()[1]
    year = selected_date.isocalendar()[0]  # Use year from selected date (handles year boundaries)
    monday, sunday = get_week_dates(year, selected_week)
    st.caption(f"🗓️ **Week {selected_week}** ({monday.strftime('%d %b')} – {sunday.strftime('%d %b %Y')})")

    # Weekly total and limit check
    total = calculate_week_total(selected_week)
    over = total > 37.5
    st.markdown("---")
    if over:
        st.error(f"⚠️ **{total:.1f} / 37.5 hours** - Weekly limit exceeded!")
    else:
        st.success(f"✅ **{total:.1f} / 37.5 hours**")
    st.progress(min(total / 37.5, 1.0))
    
    st.markdown("---")
    st.subheader("📝 Enter Hours by Module")
    if not st.session_state.modules:
        st.warning("Add modules first.")
    else:
        for m in calculate_module_stats():
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{m['id']} - {m['name']}**")
                    st.caption(f"Remaining: {m['remaining']:.1f}h of {m['total_hours']}h")
                with col2:
                    saved = get_entry_hours(selected_week, m['id'])
                    key = f"input_{m['id']}"
                    if key not in st.session_state:
                        st.session_state[key] = float(saved)
                    temp = st.number_input(
                        "Hours",
                        min_value=0.0,
                        max_value=200.0,
                        value=st.session_state[key],
                        step=0.5,
                        key=f"ni_{m['id']}",
                        label_visibility="collapsed"
                    )
                    st.session_state[key] = temp
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅ Claim", key=f"claim_{m['id']}", use_container_width=True):
                            add_or_update_entry(selected_week, m['id'], temp)
                            st.rerun()
                    with b2:
                        if st.button("🔄 Reset", key=f"reset_{m['id']}", use_container_width=True):
                            st.session_state[key] = float(saved)
                            st.rerun()
                st.markdown("---")
        if over:
            st.warning("⚠️ Remember: You cannot claim more than 37.5 hours per week!")

elif st.session_state.page == 'reports':
    st.title("📊 Reports & Analytics")
    if not st.session_state.entries:
        st.warning("No data yet.")
    else:
        df = create_detailed_report_df()
        st.markdown("---")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Total Hours", f"{df['Hours'].sum():.1f}")
        with c2: st.metric("Weeks", df['Week'].nunique())
        with c3: st.metric("Modules", df['Module'].nunique())
        with c4: st.metric("Avg Weekly", f"{df.groupby('Week')['Hours'].sum().mean():.1f}")
        
        st.markdown("---")
        weeks = sorted(df['Week'].unique())
        c1, c2 = st.columns(2)
        start = c1.selectbox("From Week", weeks, 0)
        end = c2.selectbox("To Week", weeks, len(weeks)-1)
        fdf = df[(df['Week'] >= start) & (df['Week'] <= end)]
        
        st.markdown("---")
        t1, t2, t3, t4 = st.tabs(["📊 Weekly", "🎯 By Module", "📉 Progress", "📅 Weekly x Module"])
        with t1:
            wd = fdf.groupby('Week')['Hours'].sum().reset_index()
            fig = go.Figure(go.Bar(x=wd['Week'], y=wd['Hours'], marker_color=['red' if h>37.5 else 'green' for h in wd['Hours']], text=wd['Hours'].round(1)))
            fig.add_hline(y=37.5, line_dash="dash", line_color="red")
            st.plotly_chart(fig, use_container_width=True)
        with t2:
            md = fdf.groupby('Module')['Hours'].sum().reset_index()
            st.plotly_chart(px.pie(md, values='Hours', names='Module'), use_container_width=True)
        with t3:
            stats = calculate_module_stats()
            if stats:
                dfp = pd.DataFrame(stats)
                fig = go.Figure()
                fig.add_bar(x=dfp['id'], y=dfp['claimed'], name='Claimed')
                fig.add_bar(x=dfp['id'], y=dfp['remaining'], name='Remaining')
                fig.update_layout(barmode='stack', height=400)
                st.plotly_chart(fig, use_container_width=True)
        with t4:
            if not fdf.empty:
                pivot = fdf.pivot_table(values='Hours', index='Week', columns='Module', fill_value=0)
                fig = go.Figure()
                for col in pivot.columns:
                    fig.add_bar(x=pivot.index, y=pivot[col], name=col)
                fig.update_layout(barmode='stack', height=400)
                st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1: st.download_button("📄 CSV", fdf.to_csv(index=False), f"report_{start}-{end}.csv", use_container_width=True)
        with c2: st.download_button("📊 Excel", to_excel(fdf), f"report_{start}-{end}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        st.dataframe(fdf.sort_values(['Week', 'Module']), use_container_width=True, hide_index=True)

else:
    # CALENDAR VIEWER — FROM GOOGLE DRIVE
    st.session_state.calendar_week_start = get_week_monday(datetime.today().date())
    st.title("📅 Calendar Viewer")
    calendars = load_calendars_from_drive()
    if not calendars:
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
    
    # Navigation
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
    
    # Legend
    sources = sorted(set(e['source'] for e in all_events))
    st.markdown("---")
    cols = st.columns(min(len(sources), 4))
    for i, s in enumerate(sources):
        with cols[i % 4]:
            st.markdown(f"<span style='color:{get_source_color(s)}'>●</span> {get_source_icon(s)} **{s}**", unsafe_allow_html=True)
    
    # Weekly view
    st.markdown("---")
    current = st.session_state.calendar_week_start
    local_tz = datetime.now().astimezone().tzinfo
    for i in range(7):
        target = current
        day_events = [e for e in all_events if (e['start'].date() if isinstance(e['start'], datetime) else e['start']) == target]
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
    
    # Stats
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Events", len(all_events))
    with c2: st.metric("Calendars", len(calendars))
    with c3: st.metric("All-day", sum(1 for e in all_events if e['is_allday']))
    
    if st.button("🔄 Reload Calendars"):
        st.cache_data.clear()
        st.rerun()