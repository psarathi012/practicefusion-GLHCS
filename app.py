import streamlit as st
import requests
import pandas as pd
import psycopg2
import os
from datetime import date, datetime, timedelta
# from dotenv import load_dotenv

# load_dotenv()  # Load environment variables from .env file

# Add this right after load_dotenv() to debug



# ---------- CONFIG ----------
BASE_URL = "https://static.practicefusion.com"

def get_db_connection():
    return psycopg2.connect(
       host = "aws-1-us-east-1.pooler.supabase.com",
    dbname = "postgres",
    user = "postgres.hownxddqrylfanrqytxa",
    password = "$7Q3WEzArEqoYkL$",
    port = "5432"
       
    )
# 🔹 Fetch latest session from DB
def get_latest_session():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT cookie, csrf_token 
        FROM sessions
        WHERE expires_at > NOW()
        AND source = 'practicefusion'
        ORDER BY expires_at DESC
        LIMIT 1;
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row if row else None


# ---------- STREAMLIT UI ----------
st.title("Patient Dashboard")
st.write("Fetch patients with insurance and visit details")

# Date range picker
start_date, end_date = st.date_input(
    "Select Date Range",
    [date(2025, 7, 31), date(2025, 8, 20)]  # default
)

if st.button("Fetch Patients"):
    st.write("Fetching data...",os.getenv("host"))
    with st.status("Fetching data...", expanded=True) as status:
        session = get_latest_session()
        if not session:
            st.error("⚠️ No valid session found in DB")
        else:
            cookie_string, csrf_token = session
            st.write("✅ Got session from DB")

            # Example API call
            HEADERS = {
                "accept": "application/json",
                "content-type": "application/json; charset=UTF-8",
                "cookie": cookie_string,
                "authorization": csrf_token,
                
            }
        # Step 1: Fetch patients
        # Convert dates to ET timezone format
        # Start date: beginning of day in ET (00:00:00 ET = 04:00:00 UTC)
        start_datetime = f"{start_date}T04:00:00.000Z"
        
        # End date: end of day in ET (23:59:59 ET = 03:59:59 UTC next day)
        end_date_obj = datetime.combine(end_date, datetime.min.time())
        next_day = end_date_obj + timedelta(days=1)
        end_datetime = f"{next_day.strftime('%Y-%m-%d')}T03:59:59.000Z"
        
        payload = {
            "startMinimumDateTimeUtc": start_datetime,
            "startMaximumDateTimeUtc": end_datetime
        }

       
        all_patients = []
        page = 0
        page_size = 50

        while True:
            resp = requests.post(
                f"{BASE_URL}/ScheduleEndpoint/api/v1/Schedule/Report/{page}/{page_size}",
                headers=HEADERS,
                json=payload
            )

            if resp.status_code != 200:
                st.error(f"Failed to fetch patients on page {page}: {resp.text}")
                break

            patients = resp.json().get("scheduledEventList", [])
            if not patients:  # no more data
                break

            all_patients.extend(patients)
            page += 1  # move to next page

        if resp.status_code != 200:
            st.error(f"Failed to fetch patients: {resp.text}")
        if not all_patients:
            st.error("No patients found.")
        else:

            st.write(f"✅ Fetched {len(all_patients)} patients")

            data = []
            for p in all_patients:
                patient_uid = p.get("patientPracticeGuid")
                name = p.get("patientName")
                provider=p.get("providerName")
                # Extract DOB as date only
                Dob = p.get("patientDateOfBirthDateTime")
                if Dob:
                    # Parse the datetime and extract just the date part
                    try:
                        dob_datetime = datetime.fromisoformat(Dob.replace('Z', '+00:00'))
                        Dob = dob_datetime.strftime('%Y-%m-%d')  # Format as YYYY-MM-DD
                    except:
                        Dob = "N/A"  # If parsing fails, keep as N/A
                else:
                    Dob = "N/A"
                Phone = p.get("patientMobilePhone")
                AppointmentType = p.get("appointmentTypeName")
                StartTime = p.get("startAtDateTimeFlt")
                Status = p.get("status")

                # Step 2: Insurance details
                ins_resp = requests.get(
                    f"https://static.practicefusion.com/PatientEndpoint/api/v1/patients/{patient_uid}/patientRibbonInfo",
                    headers=HEADERS,
                )
                insurance = ins_resp.json() if ins_resp.status_code == 200 else {}

                # Extract insurance information
                primary_insurance = "N/A"
                primary_insurance_id = "N/A"
                # secondary_insurance = "N/A"
                # secondary_insurance_id = "N/A"
                secondary_insurance_combined = "N/A"


                if insurance:
                    # Primary insurance
                    primary_plan = insurance.get("primaryInsurancePlan", {})
                    if primary_plan:
                        primary_insurance = primary_plan.get("payerName", "N/A")
                        primary_insurance_id = primary_plan.get("policyIdentifier", "N/A")
                    
                    # Secondary insurance (if available in the API response)
                    secondary_plan = insurance.get("secondaryInsurancePlan", {})
                    if secondary_plan:
                        sec_payer = secondary_plan.get("payerName", "N/A")
                        sec_id = secondary_plan.get("policyIdentifier", "N/A")
                        secondary_insurance_combined = f"{sec_payer} - {sec_id}" if sec_payer != "N/A" and sec_id != "N/A" else "N/A"

                # Step 3: Visit details
                transcript_resp = requests.get(
                    f"https://static.practicefusion.com/ChartingEndpoint/api/v4/patients/{patient_uid}/transcriptSummaries",
                    headers=HEADERS,
                )
                transcripts = transcript_resp.json().get("transcriptDisplaySummaries", []) if transcript_resp.status_code == 200 else []

                # Store all transcripts as JSON
                all_transcripts = []
                for t in transcripts:
                    transcript_date = t.get("dateOfServiceLocal", "N/A")
                    transcript_type = t.get("encounterTypeEncounterEventTypeName", "N/A")
                    all_transcripts.append(f"{transcript_date} - {transcript_type}")

                # Join them as one string (or keep as list if you prefer)
                transcripts_str = "; ".join(all_transcripts) if all_transcripts else "N/A"
                
                # Step 3.5: Fetch patient notes
                patient_details_resp = requests.get(
                    f"https://static.practicefusion.com/PatientEndpoint/api/v3/patients/{patient_uid}",
                    headers=HEADERS,
                )
                patient_notes = "N/A"
                if patient_details_resp.status_code == 200:
                    patient_data = patient_details_resp.json()
                    patient_notes = patient_data.get("patient", {}).get("notes", "N/A")

                # Create one row per patient with all transcripts
                data.append({
                    "Patient UID": patient_uid,
                    "Name": name,
                    "Provider": provider,
                    "DOB": Dob,
                    "Phone": Phone,
                    "Appointment Type": AppointmentType,
                    "Start Time": StartTime,
                    "Status": Status,
                    "Primary Insurance": primary_insurance,
                    "Primary Insurance ID": primary_insurance_id,
                    "Secondary Insurance + Member ID": secondary_insurance_combined,
                    "All Transcripts": transcripts_str,
                    "Patient Notes": patient_notes,
                    "Insurance": insurance
                })

            # Step 4: Show in table
            df = pd.DataFrame(data)
            st.dataframe(df)

            status.update(label="✅ All data fetched successfully!", state="complete")

