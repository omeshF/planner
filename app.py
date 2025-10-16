import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import json
import os
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from icalendar import Calendar
import pytz

# Page configuration
st.set_page_config(
    page_title="Hours Tracker & Calendar",
    page_icon="⏰",
    layout="wide"
)

# Data file paths
DATA_DIR = "hours_tracker_data"
MODULES_FILE = os.path.join(DATA_DIR, "modules.json")
ENTRIES_FILE = os.path.join(DATA_DIR, "entries.json")

# Calendar files
CALENDAR_DIR = "calendar_data"
OUTPUT_FILE = os.path.join(CALENDAR_DIR, "merged_output.ics")

# Create data directories if they don't exist
for directory in [DATA_DIR, CALENDAR_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

def load_data():
    """Load modules and entries from JSON files"""
    modules = []
    entries = []
    next_id = 1
    
    # Load modules
    if os.path.exists(MODULES_FILE):
        try:
            with open(MODULES_FILE, 'r') as f:
                modules = json.load(f)
                if modules:
                    next_id = max(m['id'] for m in modules) + 1
        except:
            modules = []
    
    # Load entries
    if os.path.exists(ENTRIES_FILE):
        try:
            with open(ENTRIES_FILE, 'r') as f:
                entries = json.load(f)
        except:
            entries = []
    
    return modules, entries, next_id

def save_modules():
    """Save modules to JSON file"""
    with open(MODULES_FILE, 'w') as f:
        json.dump(st.session_state.modules, f, indent=2)

def save_entries():
    """Save entries to JSON file"""
    with open(ENTRIES_FILE, 'w') as f:
        json.dump(st.session_state.entries, f, indent=2)

def get_source_color(source):
    """Get color for a calendar source"""
    # Predefined colors for common sources
    color_map = {
        'gmail': '#EA4335',      # Google red
        'google': '#EA4335',
        'samsung': '#1428A0',    # Samsung blue
        'outlook': '#0078D4',    # Outlook blue
        'apple': '#555555',      # Apple gray
        'icloud': '#555555',
    }
    
    # Check if source name contains any known keywords
    source_lower = source.lower()
    for key, color in color_map.items():
        if key in source_lower:
            return color
    
    # Generate a consistent color based on source name hash
    import hashlib
    hash_obj = hashlib.md5(source.encode())
    hash_hex = hash_obj.hexdigest()
    # Use first 6 characters as color
    color = f"#{hash_hex[:6]}"
    return color

def get_source_icon(source):
    """Get emoji icon for a calendar source"""
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
def get_all_ics_files():
    """Get all .ics files in the calendar directory"""
    if not os.path.exists(CALENDAR_DIR):
        return []
    return [f for f in os.listdir(CALENDAR_DIR) if f.endswith('.ics') and f != 'merged_output.ics']

def merge_all_ics_files():
    """Merge all .ics files in the calendar directory"""
    try:
        ics_files = get_all_ics_files()
        
        if len(ics_files) == 0:
            return None, False, "No .ics files found"
        
        # Create a new merged calendar
        merged_cal = Calendar()
        
        # Process each .ics file
        first_file = True
        for filename in ics_files:
            filepath = os.path.join(CALENDAR_DIR, filename)
            
            # Extract source name from filename (remove .ics extension)
            source_name = filename.replace('.ics', '')
            
            try:
                with open(filepath, 'rb') as f:
                    cal = Calendar.from_ical(f.read())
                
                # Copy properties from first calendar
                if first_file:
                    for key in cal.keys():
                        if key != 'VEVENT':
                            merged_cal.add(key, cal[key])
                    first_file = False
                
                # Add all events and tag with source
                for component in cal.walk():
                    if component.name == "VEVENT":
                        component.add('X-SOURCE', source_name)
                        merged_cal.add_component(component)
            
            except Exception as e:
                st.warning(f"⚠️ Could not read {filename}: {str(e)}")
                continue
        
        # Write merged calendar to output file
        with open(OUTPUT_FILE, 'wb') as f_out:
            f_out.write(merged_cal.to_ical())
        
        return merged_cal, True, f"Successfully merged {len(ics_files)} calendar file(s)"
    
    except Exception as e:
        return None, False, f"Error merging calendars: {str(e)}"

def extract_events(calendar):
    """Extract events with start time, end time, summary, and source"""
    events = []
    local_tz = datetime.now().astimezone().tzinfo

    try:
        from tzlocal import get_localzone
        local_tz_name = str(get_localzone())
        pytz_tz = pytz.timezone(local_tz_name)
    except Exception:
        pytz_tz = None

    for component in calendar.walk():
        if component.name == "VEVENT":
            dtstart = component.get('dtstart')
            dtend = component.get('dtend')
            summary = str(component.get('summary', 'No Title'))
            source = str(component.get('X-SOURCE', 'unknown'))

            if not dtstart or not dtend:
                continue

            start = dtstart.dt
            end = dtend.dt
            is_allday = False

            # Handle all-day events
            if not isinstance(start, datetime):
                is_allday = True
            else:
                if start.tzinfo is None:
                    if pytz_tz:
                        start = pytz_tz.localize(start, is_dst=None)
                    else:
                        start = start.replace(tzinfo=local_tz)
                if start.tzinfo != local_tz:
                    start = start.astimezone(local_tz)

            if isinstance(end, datetime):
                if end.tzinfo is None:
                    if pytz_tz:
                        end = pytz_tz.localize(end, is_dst=None)
                    else:
                        end = end.replace(tzinfo=local_tz)
                if end.tzinfo != local_tz:
                    end = end.astimezone(local_tz)

            events.append({
                'start': start,
                'end': end,
                'summary': summary,
                'is_allday': is_allday,
                'source': source
            })
    return events

def get_week_monday(any_date):
    """Return Monday of the week containing any_date"""
    return any_date - timedelta(days=any_date.weekday())

# Initialize session state
if 'modules' not in st.session_state:
    modules, entries, next_id = load_data()
    st.session_state.modules = modules
    st.session_state.entries = entries
    st.session_state.next_id = next_id

if 'page' not in st.session_state:
    st.session_state.page = 'modules'

if 'calendar_week_start' not in st.session_state:
    st.session_state.calendar_week_start = get_week_monday(datetime.today().date())

def get_week_number():
    """Get current week number"""
    return datetime.now().isocalendar()[1]

def get_week_dates(year, week_num):
    """Get start and end dates for a given week number"""
    jan_1 = datetime(year, 1, 1)
    week_start = jan_1 + timedelta(days=(week_num - 1) * 7)
    # Adjust to Monday
    monday = week_start - timedelta(days=week_start.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday

def calculate_module_stats():
    """Calculate claimed and remaining hours for each module"""
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
    """Calculate total hours for a specific week"""
    return sum(e['hours'] for e in st.session_state.entries if e['week'] == week_num)

def add_module(name, hours):
    """Add a new module"""
    st.session_state.modules.append({
        'id': st.session_state.next_id,
        'name': name,
        'total_hours': hours
    })
    st.session_state.next_id += 1
    save_modules()

def delete_module(module_id):
    """Delete a module and its entries"""
    st.session_state.modules = [m for m in st.session_state.modules if m['id'] != module_id]
    st.session_state.entries = [e for e in st.session_state.entries if e['module_id'] != module_id]
    save_modules()
    save_entries()

def update_module(module_id, name, hours):
    """Update module details"""
    for module in st.session_state.modules:
        if module['id'] == module_id:
            module['name'] = name
            module['total_hours'] = hours
            break
    save_modules()

def add_or_update_entry(week, module_id, hours):
    """Add or update hours entry for a specific week and module"""
    # Find existing entry
    entry_idx = None
    for idx, e in enumerate(st.session_state.entries):
        if e['week'] == week and e['module_id'] == module_id:
            entry_idx = idx
            break
    
    if hours == 0:
        # Remove entry if hours is 0
        if entry_idx is not None:
            st.session_state.entries.pop(entry_idx)
    else:
        if entry_idx is not None:
            # Update existing
            st.session_state.entries[entry_idx]['hours'] = hours
        else:
            # Add new
            st.session_state.entries.append({
                'week': week,
                'module_id': module_id,
                'hours': hours
            })
    save_entries()

def get_entry_hours(week, module_id):
    """Get hours for a specific week and module"""
    for e in st.session_state.entries:
        if e['week'] == week and e['module_id'] == module_id:
            return e['hours']
    return 0.0

def get_module_name(module_id):
    """Get module name by ID"""
    for m in st.session_state.modules:
        if m['id'] == module_id:
            return m['name']
    return "Unknown Module"

def create_detailed_report_df():
    """Create detailed DataFrame for reports"""
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
    """Convert DataFrame to Excel file"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Hours Report')
    return output.getvalue()

# Navigation menu in sidebar
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

# Main App
if st.session_state.page == 'modules':
    # MODULE MANAGEMENT PAGE
    st.title("📚 Module Management")
    st.write("Add and manage your university modules")
    
    # Show data location
    with st.expander("ℹ️ Data Storage Info"):
        st.info(f"Your data is saved in: `{os.path.abspath(DATA_DIR)}`")
        st.caption("All modules and claims are automatically saved and will be available when you restart the app.")
    
    st.markdown("---")
    
    # Add New Module Section
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
    
    # Display Modules
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
                
                # Edit mode
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
    # HOURS CLAIMING PAGE
    if 'selected_week' not in st.session_state:
        st.session_state.selected_week = get_week_number()
    
    st.title("⏰ Claim Hours")
    st.write("Log your weekly hours by module")
    
    st.markdown("---")
    
    # Week Navigation
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
    
    # Weekly Summary
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
    
    # Hours Entry
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
                    current_hours = get_entry_hours(st.session_state.selected_week, module['id'])
                    hours = st.number_input(
                        "Hours",
                        min_value=0.0,
                        max_value=200.0,
                        value=float(current_hours),
                        step=0.5,
                        key=f"hours_{module['id']}",
                        label_visibility="collapsed"
                    )
                    
                    if hours != current_hours:
                        add_or_update_entry(st.session_state.selected_week, module['id'], hours)
                        st.rerun()
                
                st.markdown("---")
        
        # Summary at bottom
        st.markdown("")
        if is_over_limit:
            st.warning("⚠️ Remember: You cannot claim more than 37.5 hours per week!")

elif st.session_state.page == 'reports':
    # REPORTS PAGE
    st.title("📊 Reports & Analytics")
    st.write("View detailed reports and export your data")
    
    if not st.session_state.entries:
        st.warning("No hours claimed yet. Start claiming hours to see reports!")
    else:
        # Create DataFrame
        df = create_detailed_report_df()
        
        # Summary Statistics
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
        
        # Date Range Filter
        st.subheader("🔍 Filter by Date Range")
        col1, col2 = st.columns(2)
        
        all_weeks = sorted(df['Week'].unique())
        with col1:
            start_week = st.selectbox("From Week", all_weeks, index=0)
        with col2:
            end_week = st.selectbox("To Week", all_weeks, index=len(all_weeks)-1)
        
        # Filter data
        filtered_df = df[(df['Week'] >= start_week) & (df['Week'] <= end_week)]
        
        st.markdown("---")
        
        # Charts
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Weekly Hours", "🎯 Module Breakdown", "📉 Module Progress", "📅 Weekly by Module"])
        
        with tab1:
            st.subheader("Weekly Hours Claimed")
            weekly_data = filtered_df.groupby('Week')['Hours'].sum().reset_index()
            
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=weekly_data['Week'],
                y=weekly_data['Hours'],
                marker_color=['red' if h > 37.5 else 'green' for h in weekly_data['Hours']],
                text=weekly_data['Hours'].round(1),
                textposition='outside'
            ))
            fig.add_hline(y=37.5, line_dash="dash", line_color="red", 
                         annotation_text="37.5 hr limit")
            fig.update_layout(
                xaxis_title="Week Number",
                yaxis_title="Hours",
                showlegend=False,
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Show weeks over limit
            over_limit = weekly_data[weekly_data['Hours'] > 37.5]
            if not over_limit.empty:
                st.warning(f"⚠️ {len(over_limit)} week(s) exceeded the 37.5 hour limit!")
        
        with tab2:
            st.subheader("Hours by Module")
            module_data = filtered_df.groupby('Module')['Hours'].sum().reset_index()
            
            fig = px.pie(module_data, values='Hours', names='Module', 
                        title='Total Hours Distribution by Module')
            st.plotly_chart(fig, use_container_width=True)
            
            # Module table
            st.dataframe(module_data.sort_values('Hours', ascending=False), 
                        use_container_width=True, hide_index=True)
        
        with tab3:
            st.subheader("Module Progress: Claimed vs Allocated")
            module_stats = calculate_module_stats()
            progress_df = pd.DataFrame(module_stats)
            
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name='Claimed',
                x=progress_df['name'],
                y=progress_df['claimed'],
                marker_color='lightblue'
            ))
            fig.add_trace(go.Bar(
                name='Remaining',
                x=progress_df['name'],
                y=progress_df['remaining'],
                marker_color='lightgray'
            ))
            fig.update_layout(
                barmode='stack',
                xaxis_title="Module",
                yaxis_title="Hours",
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Progress table
            st.dataframe(
                progress_df[['name', 'claimed', 'total_hours', 'remaining']]
                .rename(columns={
                    'name': 'Module',
                    'claimed': 'Claimed (hrs)',
                    'total_hours': 'Total (hrs)',
                    'remaining': 'Remaining (hrs)'
                }),
                use_container_width=True,
                hide_index=True
            )
        
        with tab4:
            st.subheader("Weekly Hours by Module (Stacked)")
            pivot_data = filtered_df.pivot_table(
                values='Hours',
                index='Week',
                columns='Module',
                aggfunc='sum',
                fill_value=0
            )
            
            fig = go.Figure()
            for module in pivot_data.columns:
                fig.add_trace(go.Bar(
                    name=module,
                    x=pivot_data.index,
                    y=pivot_data[module]
                ))
            
            fig.update_layout(
                barmode='stack',
                xaxis_title="Week Number",
                yaxis_title="Hours",
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        
        # Export Section
        st.subheader("📥 Export Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # CSV Export
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="📄 Download as CSV",
                data=csv,
                file_name=f"hours_report_{start_week}_to_{end_week}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # Excel Export
            excel_data = to_excel(filtered_df)
            st.download_button(
                label="📊 Download as Excel",
                data=excel_data,
                file_name=f"hours_report_{start_week}_to_{end_week}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        st.markdown("---")
        
        # Detailed Data Table
        st.subheader("📋 Detailed Hours Log")
        st.dataframe(
            filtered_df.sort_values(['Week', 'Module']),
            use_container_width=True,
            hide_index=True
        )

else:
    # CALENDAR VIEWER PAGE
    st.title("📅 Calendar Viewer")
    st.write("Upload and view all your calendar files with automatic color-coding")
    
    st.markdown("---")
    
    # File upload section
    st.subheader("📤 Upload Calendar Files")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_files = st.file_uploader(
            "Upload .ics calendar files (Gmail, Samsung, etc.)",
            type=['ics'],
            accept_multiple_files=True,
            help="You can upload multiple calendar files at once"
        )
        
        if uploaded_files:
            for uploaded_file in uploaded_files:
                file_path = os.path.join(CALENDAR_DIR, uploaded_file.name)
                with open(file_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())
            st.success(f"✅ Uploaded {len(uploaded_files)} calendar file(s)")
            # Auto-merge after upload
            with st.spinner("Merging calendars..."):
                merged_cal, success, message = merge_all_ics_files()
            st.rerun()
    
    with col2:
        st.info(f"**Files in folder:** {len(get_all_ics_files())}")
        if st.button("🔄 Refresh & Merge", help="Refresh and re-merge all calendars"):
            if get_all_ics_files():
                with st.spinner("Merging calendars..."):
                    merged_cal, success, message = merge_all_ics_files()
            st.rerun()
    
    # Show uploaded files
    ics_files = get_all_ics_files()
    
    if ics_files:
        # Auto-merge calendars if files exist
        if not os.path.exists(OUTPUT_FILE):
            with st.spinner("Auto-merging calendars..."):
                merged_cal, success, message = merge_all_ics_files()
        
        with st.expander(f"📋 Uploaded Calendars ({len(ics_files)} files)", expanded=False):
            for idx, filename in enumerate(ics_files, 1):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    source_name = filename.replace('.ics', '')
                    icon = get_source_icon(source_name)
                    color = get_source_color(source_name)
                    st.markdown(f"{icon} **{source_name}**")
                with col2:
                    file_path = os.path.join(CALENDAR_DIR, filename)
                    file_size = os.path.getsize(file_path) / 1024  # KB
                    st.caption(f"{file_size:.1f} KB")
                with col3:
                    if st.button("🗑️", key=f"del_cal_{idx}", help=f"Delete {filename}"):
                        os.remove(file_path)
                        if os.path.exists(OUTPUT_FILE):
                            os.remove(OUTPUT_FILE)
                        st.rerun()
    else:
        st.info("📋 No calendar files uploaded yet. Upload your Gmail, Samsung, or other .ics files above.")
    
    st.markdown("---")
    
    # Display merged calendar
    if os.path.exists(OUTPUT_FILE):
        st.subheader("📆 Weekly Calendar View")
        
        # Load events
        try:
            with open(OUTPUT_FILE, 'rb') as f:
                cal = Calendar.from_ical(f.read())
            events = extract_events(cal)
            
            if events:
                # Get all unique sources
                unique_sources = list(set(e['source'] for e in events))
                
                # Week navigation
                col1, col2, col3 = st.columns([1, 2, 1])
                
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
                
                # Legend with all sources
                st.markdown("---")
                st.markdown("**Calendar Sources:**")
                cols = st.columns(min(len(unique_sources), 4))
                for idx, source in enumerate(sorted(unique_sources)):
                    with cols[idx % 4]:
                        icon = get_source_icon(source)
                        color = get_source_color(source)
                        st.markdown(f"<span style='color: {color};'>●</span> {icon} **{source}**", unsafe_allow_html=True)
                
                st.markdown("---")
                
                # Display week
                current_day = st.session_state.calendar_week_start
                for i in range(7):
                    day_events = []
                    for e in events:
                        event_date = e['start'].date() if isinstance(e['start'], datetime) else e['start']
                        if event_date == current_day:
                            day_events.append(e)
                    
                    # Sort events
                    day_events.sort(key=lambda x: (
                        not x['is_allday'],
                        x['start'].time() if isinstance(x['start'], datetime) else datetime.min.time()
                    ))
                    
                    # Day header
                    day_name = current_day.strftime("%A, %B %d")
                    is_weekend = i >= 5
                    with st.expander(f"{'🌅 ' if is_weekend else '📅 '}{day_name}", expanded=(i < 2)):
                        if not day_events:
                            st.info("No events scheduled")
                        else:
                            for e in day_events:
                                # Get color and icon by source
                                source = e['source']
                                color = get_source_color(source)
                                icon = get_source_icon(source)
                                
                                if e['is_allday']:
                                    time_str = "🕗 All-day"
                                else:
                                    start_time = e['start'].strftime("%H:%M")
                                    end_time = e['end'].strftime("%H:%M") if isinstance(e['end'], datetime) else "??"
                                    time_str = f"🕒 {start_time} - {end_time}"
                                
                                st.markdown(f"<div style='background-color: {color}22; padding: 10px; border-left: 4px solid {color}; margin-bottom: 8px; border-radius: 4px;'>"
                                          f"<strong style='color: {color};'>{icon} {source}</strong> | {time_str}<br/>"
                                          f"<span style='color: #333;'>{e['summary']}</span>"
                                          f"</div>", unsafe_allow_html=True)
                    
                    current_day += timedelta(days=1)
                
                st.markdown("---")
                
                # Statistics
                st.subheader("📊 Calendar Statistics")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Events", len(events))
                with col2:
                    st.metric("Calendar Sources", len(unique_sources))
                with col3:
                    allday_count = sum(1 for e in events if e['is_allday'])
                    st.metric("All-day Events", allday_count)
                
                st.markdown("---")
                
                # Download merged calendar
                with open(OUTPUT_FILE, 'rb') as f:
                    st.download_button(
                        label="📥 Download Merged Calendar (.ics)",
                        data=f.read(),
                        file_name="merged_calendar.ics",
                        mime="text/calendar",
                        use_container_width=True
                    )
            
            else:
                st.warning("No events found in the merged calendar")
        
        except Exception as e:
            st.error(f"Error loading calendar: {str(e)}")
    
    else:
        # Instructions
        with st.expander("ℹ️ How to use", expanded=True):
            st.markdown("""
            **Steps to merge and view calendars:**
            
            1. **Upload Files**: Upload your Gmail, Samsung, or any other `.ics` calendar files
            2. **Multiple Files**: You can upload multiple files at once - they'll all be merged
            3. **Auto-Naming**: Each calendar will be color-coded based on its filename
            4. **Merge**: Click "Merge All Calendars" to combine them
            5. **View**: Navigate through weeks to see all your events
            6. **Download**: Export the merged calendar for use in other apps
            
            **Supported Calendars:**
            - 📧 Gmail/Google Calendar
            - 📱 Samsung Calendar
            - 📨 Outlook Calendar
            - 🍎 Apple/iCloud Calendar
            - 📅 Any other .ics calendar file
            
            **Tips:**
            - Name your files descriptively (e.g., `gmail.ics`, `samsung.ics`)
            - The filename determines the source label and color
            - All calendars in the folder are automatically detected
            
            **File Location:**
            Your calendars are saved in: `{os.path.abspath(CALENDAR_DIR)}`
            """)
