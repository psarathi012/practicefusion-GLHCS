import streamlit as st
import pandas as pd
import anthropic
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Anthropic client
@st.cache_resource
def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("⚠️ ANTHROPIC_API_KEY not found in environment variables")
        return None
    return anthropic.Anthropic(api_key=api_key)

def generate_ehr_note(client, row_data):
    """Generate EHR note using Anthropic API"""
    
    # Build the row data context
    row_context = ""
    for key, value in row_data.items():
        if pd.notna(value) and key != 'EHR Note' and key != 'Generated EHR Note':
            row_context += f"{key}: {value}\n"
    
    # Fixed format example
    format_example = """11/07/2025
Policy is active
Plan type: GEORGIA MEDICAID - ATLANTA/CENTRAL
Copay/Coinsurance: $0
Deductible: $0 / $0 remaining
OOP: $0 / $0 remaining
Visit limits: -2 remaining / 20 visits (22 visits in 2025)
Auth reqd.
Supahealth (Abbas)"""
    
    # Build the prompt
    prompt = f"""You are an EHR (Electronic Health Record) notes generator. Based on the patient insurance and visit data provided, create a concise EHR note following the exact format and style shown in the example below.

Here is the desired EHR note format:

{format_example}

Now, create an EHR note for the following patient data:

{row_context}

Important guidelines:
1. Follow the EXACT format shown in the example
2. Include today's date at the top (MM/DD/YYYY format)
3. Extract policy status, plan type, copay, deductible, OOP, visit limits, and authorization requirements
4. Be concise and structured
5. End with "Supahealth (Abbas)"
6. If any information is missing or not provided, use reasonable defaults or omit that line
7. For visit limits, calculate remaining visits based on available data

Generate ONLY the EHR note text, no additional commentary."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text.strip()
    except Exception as e:
        return f"Error generating note: {str(e)}"

# ---------- STREAMLIT UI ----------
st.title("🏥 EHR Notes Generator")
st.write("Upload an Excel file to generate EHR notes using Anthropic AI")

# Initialize client
client = get_anthropic_client()

if client is None:
    st.stop()

# File uploader
uploaded_file = st.file_uploader("Choose an Excel file", type=['xlsx', 'xls'])

if uploaded_file is not None:
    try:
        # Read the Excel file
        df = pd.read_excel(uploaded_file)
        
        st.success(f"✅ File loaded successfully! Found {len(df)} rows and {len(df.columns)} columns")
        
        # Show columns
        with st.expander("📋 View Columns"):
            st.write(df.columns.tolist())
        
        # Show sample data
        with st.expander("👀 Preview Data (First 3 rows)"):
            st.dataframe(df.head(3))
        
        # Processing options
        st.subheader("⚙️ Processing Options")
        
        process_all = st.checkbox("Process all rows", value=False)
        
        if not process_all:
            num_rows = st.number_input("Number of rows to process", min_value=1, max_value=len(df), value=min(5, len(df)))
        else:
            num_rows = len(df)
        
        # Generate button
        if st.button("🚀 Generate EHR Notes", type="primary"):
            
            # Create a copy of the dataframe
            df_result = df.copy()
            
            # Add new column for generated notes
            df_result['Generated EHR Note'] = None
            
            # Progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Process rows
            rows_to_process = df.iloc[:num_rows] if not process_all else df
            
            for idx, (index, row) in enumerate(rows_to_process.iterrows()):
                status_text.text(f"Processing row {idx + 1} of {num_rows}...")
                progress_bar.progress((idx + 1) / num_rows)
                
                # Convert row to dict
                row_data = row.to_dict()
                
                # Generate EHR note
                generated_note = generate_ehr_note(client, row_data)
                df_result.at[index, 'Generated EHR Note'] = generated_note
            
            status_text.text("✅ Processing complete!")
            
            # Show results
            st.subheader("📊 Results")
            
            # Show sample generated notes
            st.markdown("### Sample Generated Notes")
            
            for idx in range(min(3, num_rows)):
                row = df_result.iloc[idx]
                
                with st.expander(f"Patient: {row.get('Patient Name', 'N/A')} - {row.get('Appointment date', 'N/A')}"):
                    generated_note = row.get('Generated EHR Note', 'N/A')
                    if pd.notna(generated_note):
                        st.text(generated_note)
                    else:
                        st.text("(No generated note)")
            
            # Show full dataframe
            st.markdown("### Full Results Table")
            
            # Select key columns to display
            display_cols = ['Patient Name', 'DOB', 'Primary Insurance', 'Appointment date', 'Generated EHR Note']
            
            # Filter to show only available columns
            available_cols = [col for col in display_cols if col in df_result.columns]
            st.dataframe(df_result[available_cols].head(num_rows))
            
            # Download button
            st.subheader("💾 Download Results")
            
            # Convert to Excel
            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_result.to_excel(writer, index=False, sheet_name='Results')
            
            excel_data = output.getvalue()
            
            st.download_button(
                label="📥 Download Excel with Generated Notes",
                data=excel_data,
                file_name=f"ehr_notes_generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            # Statistics
            st.subheader("📈 Statistics")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Rows Processed", num_rows)
            
            with col2:
                successful = df_result['Generated EHR Note'].notna().sum()
                st.metric("Successfully Generated", successful)
            
            with col3:
                errors = df_result['Generated EHR Note'].isna().sum()
                st.metric("Errors", errors)
    
    except Exception as e:
        st.error(f"❌ Error processing file: {str(e)}")
        st.exception(e)

else:
    st.info("👆 Please upload an Excel file to get started")
    
    # Show instructions
    st.markdown("""
    ### 📖 Instructions
    
    1. **Upload** your Excel file containing patient insurance and visit data
    2. **Configure** processing options (all rows or specific number)
    3. Click **Generate EHR Notes** to create notes using AI
    4. **Review** sample generated notes
    5. **Download** the results as an Excel file with a new "Generated EHR Note" column
    
    ### 📋 Expected Columns
    
    Your Excel file should contain columns like:
    - Appointment date
    - Patient Name
    - DOB (Date of Birth)
    - Primary Insurance
    - Member ID#
    - Secondary Insurance Info
    - Copay/Copay Telehealth/Coinsurance
    - Remaining Deductibles & OOP Maximum
    - No of Visits
    - Notes
    - Remarks
    
    ### 📝 EHR Note Format
    
    All generated notes will follow this standardized format:
    ```
    MM/DD/YYYY
    Policy is active
    Plan type: [Plan Type]
    Copay/Coinsurance: $X
    Deductible: $X / $X remaining
    OOP: $X / $X remaining
    Visit limits: X remaining / X visits (X visits in YYYY)
    Auth reqd. [if applicable]
    Supahealth (Abbas)
    ```
    """)

