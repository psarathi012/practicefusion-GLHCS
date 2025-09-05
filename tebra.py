import streamlit as st
import requests
import pandas as pd
import psycopg2
import os
import time
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# ---------- CONFIG ----------
BASE_URL = "https://app.kareo.com"

def get_db_connection():
    return psycopg2.connect(
        host=st.secrets["database"]["host"],
        port=st.secrets["database"]["port"],
        dbname=st.secrets["database"]["dbname"],
        user=st.secrets["database"]["user"],
        password=st.secrets["database"]["password"]
    )

# Fetch latest session from DB
def get_latest_session():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT cookie, csrf_token 
        FROM sessions
        WHERE expires_at > NOW()
        AND source = 'tebra'
        ORDER BY expires_at DESC
        LIMIT 1;
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row if row else None

# Convert date to milliseconds timestamp
def date_to_ms_timestamp(input_date):
    epoch = datetime(1970, 1, 1)
    timestamp = int((input_date - epoch).total_seconds() * 1000)
    return timestamp

# ---------- STREAMLIT UI ----------
st.title("Tebra Patient Dashboard")
st.write("Fetch appointments and patient details from Kareo/Tebra")

# Date range picker
start_date, end_date = st.date_input(
    "Select Date Range",
    [date.today(), date.today() + timedelta(days=30)],  # Default to today through 30 days from now
    format="YYYY-MM-DD"
)

if st.button("Fetch Appointments"):
    st.write("Fetching data...")
    with st.status("Fetching data...", expanded=True) as status:
        session = get_latest_session()
        if not session:
            st.error("⚠️ No valid session found in DB")
        else:
            # Extract cookie string from session tuple
            cookie_string = session[0]  # First element of the tuple
            st.write("✅ Got session from DB")

            # Calculate start and end timestamps for the selected date range
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())
            
            start_timestamp = date_to_ms_timestamp(start_datetime)
            end_timestamp = date_to_ms_timestamp(end_datetime)

            # Headers for API request
            HEADERS = {
                "accept": "*/*",
                "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
                "cache-control": "no-cache",
                "content-type": "application/json",
                "origin": "https://app.kareo.com",
                "pragma": "no-cache",
                "priority": "u=1, i",
                "referer": "https://app.kareo.com/v2/",
                "sec-ch-ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
                "cookie": cookie_string
            }
        
        # Prepare payload for appointments API
        payload = {
            "orderByList": [],
            "pageSize": 50000,
            "currentPage": 0,
            "pmAppointmentId": None,
            "startDate": start_timestamp,
            "endDate": end_timestamp,
            "patientGuid": None,
            "providerGuids": None,
            "serviceLocationGuids": [],
            "appointmentReasonGuids": [],
            "ehrAppointmentStatuses": None,
            "groupAppointment": None,
            "matchedCharge": None,
            "linkedCharge": None,
            "primaryInsurancePlanGuids": [],
            "secondaryInsurancePlanGuids": [],
            "pmPayerScenarioIds": [],
            "patientHomePhone": None,
            "patientMobilePhone": None,
            "copayList": None,
            "practiceTimezone": "America/New_York"
        }

        # Fetch appointments
        resp = requests.post(
            f"{BASE_URL}/worklist-ui/api/appointments/base",
            headers=HEADERS,
            json=payload
        )

        if resp.status_code != 200:
            st.error(f"Failed to fetch appointments: {resp.text}")
        else:
            appointments = resp.json()
            
            # Check if we have a valid response with appointments
            if not appointments or "data" not in appointments:
                st.error("No appointments found or invalid response format.")
            else:
                appointment_list = appointments.get("data", [])
                st.write(f"✅ Fetched {len(appointment_list)} appointments")

                # Fetch additional appointment details from Bootstrap API
                st.write("Fetching additional appointment details...")
                
                # Prepare payload for Bootstrap API
                bootstrap_payload = [
                    {
                        "resource": "ApptWithMode",
                        "query": {
                            "minDate": start_timestamp,
                            "maxDate": end_timestamp,
                            "deleted": False,
                            "maxDaysPerPage": 5
                        }
                    }
                ]
                
                # Make the API call to Bootstrap
                bootstrap_resp = requests.post(
                    f"{BASE_URL}/dashboard-calendar-ui/api/BootStrap/",
                    headers=HEADERS,
                    json=bootstrap_payload
                )
                
                # Create a mapping of patient GUIDs to patient IDs
                patient_id_map = {}
                appointment_mode_map = {}
                
                # Debug information
                st.write(f"Bootstrap API response status: {bootstrap_resp.status_code}")
                
                if bootstrap_resp.status_code == 200:
                    bootstrap_data = bootstrap_resp.json()
                    
                    # Debug the structure of the response
                    st.write("Bootstrap API response structure:")
                    st.write(f"Keys in response: {list(bootstrap_data.keys())}")
                    
                    if "body" in bootstrap_data:
                        st.write(f"Keys in body: {list(bootstrap_data['body'].keys())}")
                        
                        if "results" in bootstrap_data["body"]:
                            bootstrap_appointments = bootstrap_data["body"]["results"]
                            st.write(f"Number of appointments in Bootstrap response: {len(bootstrap_appointments)}")
                            
                            # Show the first appointment structure if available
                            if bootstrap_appointments:
                                st.write("Example appointment structure:")
                                st.write(f"Keys in first appointment: {list(bootstrap_appointments[0].keys())}")
                                
                                # Check if patientSummary exists
                                if "patientSummary" in bootstrap_appointments[0]:
                                    st.write(f"Keys in patientSummary: {list(bootstrap_appointments[0]['patientSummary'].keys())}")
                            
                            for bootstrap_appt in bootstrap_appointments:
                                appt_uuid = bootstrap_appt.get("appointmentUUID")
                                appointment_mode = bootstrap_appt.get("appointmentMode", "N/A")
                                appointment_mode_map[appt_uuid] = appointment_mode
                                
                                # Extract patient info if available
                                patient_summary = bootstrap_appt.get("patientSummary")
                                if patient_summary:
                                    patient_guid = patient_summary.get("guid")
                                    patient_id = patient_summary.get("patientId", "N/A")
                                    if patient_guid:
                                        patient_id_map[patient_guid] = patient_id
                                        st.write(f"Mapped patient GUID {patient_guid} to ID {patient_id}")
                        else:
                            st.write("No 'results' found in the body")
                    else:
                        st.write("No 'body' found in the response")
                else:
                    st.error(f"Bootstrap API call failed with status {bootstrap_resp.status_code}")
                    st.write(f"Error response: {bootstrap_resp.text}")
                
                # Process appointments
                data = []
                
                # Debug patient GUID mapping
                st.write(f"Number of patient GUIDs mapped: {len(patient_id_map)}")
                st.write(f"Patient GUID map keys: {list(patient_id_map.keys())[:5] if len(patient_id_map) > 5 else list(patient_id_map.keys())}")
                
                # Debug appointment UUID mapping
                st.write(f"Number of appointment UUIDs mapped: {len(appointment_mode_map)}")
                st.write(f"Appointment UUID map keys: {list(appointment_mode_map.keys())[:5] if len(appointment_mode_map) > 5 else list(appointment_mode_map.keys())}")
                
                for appt in appointment_list:
                    # Extract basic appointment info
                    appt_id = appt.get("pmAppointmentId")
                    patient_guid = appt.get("patientGuid")
                    appt_uuid = appt.get("appointmentGuid")
                    
                    # Debug individual mapping
                    if patient_guid and patient_guid not in patient_id_map:
                        st.write(f"Patient GUID not found in map: {patient_guid}")
                    
                    # Get patient ID from mapping
                    patient_id = patient_id_map.get(patient_guid, "N/A")
                    
                    # Get appointment mode from mapping
                    appointment_mode = appointment_mode_map.get(appt_uuid, "N/A")
                    
                    # Patient name - combine first, middle, last
                    first_name = appt.get("patientFirstName", "")
                    middle_name = appt.get("patientMiddleName", "")
                    last_name = appt.get("patientLastName", "")
                    patient_name = f"{first_name} {middle_name} {last_name}".strip()
                    patient_name = patient_name if patient_name else appt.get("patientFullName", "N/A")
                    
                    # Provider name
                    provider_name = appt.get("providerFullName", "N/A")
                    
                    # Appointment details
                    appointment_start = appt.get("appointmentStart")
                    appointment_end = appt.get("appointmentEnd")
                    status = appt.get("appointmentStatus", "N/A")
                    appointment_type = appt.get("appointmentReasonName", "N/A")
                    
                    # Format timestamps to readable date/time
                    if appointment_start:
                        try:
                            start_time = datetime.fromisoformat(appointment_start.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            start_time = appointment_start
                    else:
                        start_time = "N/A"
                        
                    if appointment_end:
                        try:
                            end_time = datetime.fromisoformat(appointment_end.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            end_time = appointment_end
                    else:
                        end_time = "N/A"
                    
                    # Extract patient details if available
                    phone = appt.get("patientMobilePhone") or appt.get("patientHomePhone", "N/A")
                    
                    # Format DOB
                    dob = appt.get("patientDoB", "N/A")
                    if dob:
                        try:
                            dob = datetime.fromisoformat(dob.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                        except:
                            dob = "N/A"
                    
                    # Extract insurance info if available
                    primary_insurance = appt.get("primaryInsurancePlanName", "N/A")
                    primary_policy = appt.get("primaryInsurancePolicyNumber", "N/A")
                    secondary_insurance = appt.get("secondaryInsurancePlanName", "N/A")
                    secondary_policy = appt.get("secondaryInsurancePolicyNumber", "N/A")
                    
                   
                    # Add to data collection
                    data.append({
                        "Appointment ID": appt_id,
                        "Patient ID": patient_id,
                        "Patient GUID": patient_guid,
                        "Patient Name": patient_name,
                        "DOB": dob,
                        "Provider": provider_name,
                        "Start Time": start_time,
                        "Appointment Type": appointment_type,
                        "Appointment Mode": appointment_mode,
                        "Primary Insurance": primary_insurance,
                        "Primary Policy Number": primary_policy,
                        "Secondary Insurance": secondary_insurance,
                        "Secondary Policy Number": secondary_policy,
                        "Phone": phone
                    })
                
                # Create DataFrame and display
                if data:
                    df = pd.DataFrame(data)
                    st.dataframe(df)
                    
                    # Option to download as CSV
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download data as CSV",
                        data=csv,
                        file_name=f"tebra_appointments_{start_date}_to_{end_date}.csv",
                        mime="text/csv",
                    )
                else:
                    st.warning("No appointment data to display.")
                
                try:
                    status.update(label="✅ All data fetched successfully!", state="complete")
                except Exception as e:
                    st.success("✅ All data fetched successfully!")
