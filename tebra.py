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
                
                # Prepare payload for Bootstrap API - convert timestamps to strings
                bootstrap_payload = [
                    {
                        "resource": "ApptWithMode",
                        "query": {
                            "minDate": str(start_timestamp),
                            "maxDate": str(end_timestamp),
                            "deleted": False,
                            "maxDaysPerPage": 5
                        }
                    }
                ]
                
                # Make the API call to Bootstrap using PUT method
                st.write("Making Bootstrap API call using PUT method...")
                bootstrap_resp = requests.put(
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
                    try:
                        # Try to parse the JSON response
                        bootstrap_data = bootstrap_resp.json()
                        
                        # Debug the response content first
                        st.write("Bootstrap API raw response content (first 500 chars):")
                        response_text = bootstrap_resp.text
                        st.write(response_text[:500] + "..." if len(response_text) > 500 else response_text)
                        
                        # Debug the structure of the response
                        st.write("Bootstrap API response structure:")
                        
                        # Check if bootstrap_data is a dictionary
                        if isinstance(bootstrap_data, dict):
                            st.write(f"Keys in response: {list(bootstrap_data.keys())}")
                            
                            if "body" in bootstrap_data:
                                # Check if body is a dictionary
                                if isinstance(bootstrap_data["body"], dict):
                                    st.write(f"Keys in body: {list(bootstrap_data['body'].keys())}")
                                    
                                    if "results" in bootstrap_data["body"]:
                                        bootstrap_appointments = bootstrap_data["body"]["results"]
                                        
                                        # Check if results is a list
                                        if isinstance(bootstrap_appointments, list):
                                            st.write(f"Number of appointments in Bootstrap response: {len(bootstrap_appointments)}")
                                            
                                            # Show the first appointment structure if available
                                            if bootstrap_appointments:
                                                st.write("Example appointment structure:")
                                                if isinstance(bootstrap_appointments[0], dict):
                                                    st.write(f"Keys in first appointment: {list(bootstrap_appointments[0].keys())}")
                                                    
                                                    # Check if patientSummary exists
                                                    if "patientSummary" in bootstrap_appointments[0]:
                                                        if isinstance(bootstrap_appointments[0]["patientSummary"], dict):
                                                            st.write(f"Keys in patientSummary: {list(bootstrap_appointments[0]['patientSummary'].keys())}")
                                                        else:
                                                            st.write("patientSummary is not a dictionary")
                                                else:
                                                    st.write("First appointment is not a dictionary")
                                            
                                            for bootstrap_appt in bootstrap_appointments:
                                                if not isinstance(bootstrap_appt, dict):
                                                    continue
                                                    
                                                appt_uuid = bootstrap_appt.get("appointmentUUID")
                                                appointment_mode = bootstrap_appt.get("appointmentMode", "N/A")
                                                if appt_uuid:
                                                    appointment_mode_map[appt_uuid] = appointment_mode
                                                
                                                # Extract patient info if available
                                                patient_summary = bootstrap_appt.get("patientSummary")
                                                if patient_summary and isinstance(patient_summary, dict):
                                                    patient_guid = patient_summary.get("guid")
                                                    patient_id = patient_summary.get("patientId", "N/A")
                                                    if patient_guid:
                                                        patient_id_map[patient_guid] = patient_id
                                                        # st.write(f"Mapped patient GUID {patient_guid} to ID {patient_id}")
                                        else:
                                            st.write("Results is not a list")
                                    else:
                                        st.write("No 'results' found in the body")
                                else:
                                    st.write("Body is not a dictionary")
                            else:
                                st.write("No 'body' found in the response")
                        elif isinstance(bootstrap_data, list):
                            st.write("Response is a list with length:", len(bootstrap_data))
                            if bootstrap_data:
                                st.write("First item type:", type(bootstrap_data[0]).__name__)
                                if isinstance(bootstrap_data[0], dict):
                                    st.write(f"Keys in first item: {list(bootstrap_data[0].keys())}")
                                    
                                    # Process list-type response
                                    for item in bootstrap_data:
                                        if isinstance(item, dict) and "status" in item and item["status"] == 200:
                                            if "body" in item and isinstance(item["body"], dict) and "results" in item["body"]:
                                                bootstrap_appointments = item["body"]["results"]
                                                
                                                if isinstance(bootstrap_appointments, list):
                                                    st.write(f"Found {len(bootstrap_appointments)} appointments in list response")
                                                    
                                                    # Process appointments
                                                    for bootstrap_appt in bootstrap_appointments:
                                                        if not isinstance(bootstrap_appt, dict):
                                                            continue
                                                            
                                                        appt_uuid = bootstrap_appt.get("appointmentUUID")
                                                        appointment_mode = bootstrap_appt.get("appointmentMode", "N/A")
                                                        if appt_uuid:
                                                            appointment_mode_map[appt_uuid] = appointment_mode
                                                        
                                                        # Extract patient info if available
                                                        patient_summary = bootstrap_appt.get("patientSummary")
                                                        if patient_summary and isinstance(patient_summary, dict):
                                                            patient_guid = patient_summary.get("guid")
                                                            patient_id = patient_summary.get("patientId", "N/A")
                                                            if patient_guid and patient_id != "N/A":
                                                                patient_id_map[patient_guid] = patient_id
                                                                # st.write(f"Mapped patient GUID {patient_guid} to ID {patient_id}")
                        else:
                            st.write(f"Response is not a dictionary or list, type: {type(bootstrap_data).__name__}")
                    except Exception as e:
                        st.error(f"Error parsing Bootstrap API response: {str(e)}")
                        st.write("Response content (first 500 chars):")
                        response_text = bootstrap_resp.text
                        st.write(response_text[:500] + "..." if len(response_text) > 500 else response_text)
                else:
                    st.error(f"Bootstrap API call failed with status {bootstrap_resp.status_code}")
                    st.write(f"Error response: {bootstrap_resp.text}")
                    
                    # Fallback: Try to extract patient IDs from the main API response if available
                    st.write("Attempting to extract patient IDs from main API response...")
                    
                    # Check if we can find patient IDs in the main response
                    for appt in appointment_list:
                        patient_guid = appt.get("patientGuid")
                        
                        # Some APIs include patient ID directly in the main response
                        if "patientId" in appt:
                            patient_id = appt.get("patientId")
                            patient_id_map[patient_guid] = patient_id
                            # st.write(f"Found patient ID in main response: {patient_guid} -> {patient_id}")
                        # Or it might be embedded in a different field
                        elif "patient" in appt and isinstance(appt.get("patient"), dict):
                            patient_data = appt.get("patient")
                            if "id" in patient_data:
                                patient_id = patient_data.get("id")
                                patient_id_map[patient_guid] = patient_id
                                # st.write(f"Found patient ID in patient object: {patient_guid} -> {patient_id}")
                        # Last resort: Try to extract from URLs or other fields
                        else:
                            # Try to find patient ID in any URL fields that might contain it
                            for key, value in appt.items():
                                if isinstance(value, str) and "patient" in key.lower() and value.isdigit():
                                    patient_id = value
                                    patient_id_map[patient_guid] = patient_id
                                    # st.write(f"Found potential patient ID in field {key}: {patient_guid} -> {patient_id}")
                            
                            # If we still don't have an ID, try to generate one from the GUID
                            if patient_guid and patient_guid not in patient_id_map:
                                # Extract last part of GUID as a fallback ID
                                if "-" in patient_guid:
                                    last_part = patient_guid.split("-")[-1]
                                    # Convert to a number if possible
                                    try:
                                        numeric_id = int(last_part, 16)  # Convert from hex
                                        patient_id_map[patient_guid] = numeric_id
                                        # st.write(f"Generated patient ID from GUID: {patient_guid} -> {numeric_id}")
                                    except ValueError:
                                        pass
                
                # Process appointments
                data = []
                
                # Debug patient GUID mapping
                st.write(f"Number of patient GUIDs mapped: {len(patient_id_map)}")
                # st.write(f"Patient GUID map keys: {list(patient_id_map.keys())[:5] if len(patient_id_map) > 5 else list(patient_id_map.keys())}")
                
                # Debug appointment UUID mapping
                st.write(f"Number of appointment UUIDs mapped: {len(appointment_mode_map)}")
                # st.write(f"Appointment UUID map keys: {list(appointment_mode_map.keys())[:5] if len(appointment_mode_map) > 5 else list(appointment_mode_map.keys())}")
                
                # Fetch insurance details for each patient
                st.write("Fetching insurance details for patients...")
                
                # Create a dictionary to store insurance details
                insurance_details_map = {}
                
                # Process only unique patient IDs to avoid duplicate API calls
                unique_patient_ids = set()
                for patient_guid, patient_id in patient_id_map.items():
                    if patient_id != "N/A" and isinstance(patient_id, (int, str)):
                        unique_patient_ids.add(str(patient_id))
                
                st.write(f"Found {len(unique_patient_ids)} unique patient IDs")
                
                # Fetch insurance details for each patient ID
                for patient_id in unique_patient_ids:
                    try:
                        # Make API call to get insurance details
                        insurance_resp = requests.get(
                            f"{BASE_URL}/billing-profiles-ui/api/BillingProfile/patient/{patient_id}",
                            headers=HEADERS
                        )
                        
                        if insurance_resp.status_code == 200:
                            # Parse the insurance data
                            insurance_data = insurance_resp.json()
                            
                            # Store the insurance details
                            insurance_details_map[patient_id] = insurance_data
                            
                            # Debug info
                        else:
                            st.write(f"⚠️ Failed to fetch insurance details for patient ID {patient_id}: {insurance_resp.status_code}")
                    except Exception as e:
                        st.write(f"❌ Error fetching insurance details for patient ID {patient_id}: {str(e)}")
                    
                    # Add a small delay to avoid rate limiting
                    time.sleep(0.1)
                
                st.write(f"Fetched insurance details for {len(insurance_details_map)} patients")
                
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
                    
                    # Extract basic insurance info from appointment data
                    basic_primary_insurance = appt.get("primaryInsurancePlanName", "N/A")
                    basic_primary_policy = appt.get("primaryInsurancePolicyNumber", "N/A")
                    basic_secondary_insurance = appt.get("secondaryInsurancePlanName", "N/A")
                    basic_secondary_policy = appt.get("secondaryInsurancePolicyNumber", "N/A")
                    
                    # Extract detailed insurance info if available
                    primary_insurance = basic_primary_insurance
                    primary_policy = basic_primary_policy
                   
                    
                    secondary_insurance = basic_secondary_insurance
                    secondary_policy = basic_secondary_policy
               
                    
                    # Get detailed insurance information from the billing profiles API
                    if patient_id != "N/A" and str(patient_id) in insurance_details_map:
                        insurance_details = insurance_details_map[str(patient_id)]
                        
                        # Extract patient case information (insurance details)
                        if "patientCases" in insurance_details and insurance_details["patientCases"]:
                            # Get the first patient case (usually the active one)
                            patient_case = insurance_details["patientCases"][0]
                            
                            # Check if policies exist
                            if "policies" in patient_case:
                                policies = patient_case["policies"]
                                
                                # Primary insurance (key "1")
                                if "1" in policies:
                                    primary_policy_info = policies["1"]
                                    primary_insurance = primary_policy_info.get("planName", basic_primary_insurance)
                                    
                                    
                                
                                # Secondary insurance (key "2")
                                if "2" in policies:
                                    secondary_policy_info = policies["2"]
                                    secondary_insurance = secondary_policy_info.get("planName", basic_secondary_insurance)
                                    
                                   
                   
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
