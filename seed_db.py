import psycopg
import uuid
import json
from datetime import datetime
from faker import Faker
from app.security import get_password_hash

import os
from dotenv import load_dotenv

fake = Faker()
load_dotenv()

def seed_database():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in .env")
        return
    conn = psycopg.connect(db_url)
    cur = conn.cursor()
    
    print("Database is fresh, skipping truncate...")
    
    password_hash = get_password_hash("password123")
    now = datetime.now()
    
    # 1. Seed Industries (Skip verticals)
    industries = ["Legal", "Healthcare", "Finance", "Real Estate","HR","Education","Marketing","Sales","Operations","IT","Ecommerce_Retail","Construction_RealEstate","Automotive","Manufacturing","Energy_Utilities","Telecom","Media_Entertainment","Government_PublicSector","Nonprofit","Other"]
    industry_map = {}
    for ind_name in industries:
        ind_id = uuid.uuid4()
        cur.execute(
            "INSERT INTO industries (industry_id, name, description, created_on, updated_on) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING",
            (ind_id, ind_name, f"{ind_name} industry documents", now, now)
        )
        # Get the actual ID (whether newly inserted or existing)
        cur.execute("SELECT industry_id FROM industries WHERE name = %s", (ind_name,))
        res = cur.fetchone()
        if res:
            industry_map[ind_name] = res[0]
        
    # 3. Seed Tenants
    tenant_ids = []
    for _ in range(3):
        t_id = uuid.uuid4()
        t_name = fake.company()
        cur.execute(
            "INSERT INTO tenants (tenant_id, name, slug, org_name, created_on, updated_on) VALUES (%s, %s, %s, %s, %s, %s)",
            (t_id, t_name, t_name.lower().replace(' ', '-'), t_name, now, now)
        )
        tenant_ids.append(t_id)
        
    # 4. Seed Roles
    role_names = ["Super Admin", "Tenant Admin", "Contributor", "User", "Viewer"]
    role_map = {} # tenant_id -> {role_name -> role_id}
    
    for t_id in tenant_ids:
        role_map[t_id] = {}
        for r_name in role_names:
            r_id = uuid.uuid4()
            perms = {"all": True} if r_name == "Super Admin" else {"read": True, "write": r_name != "Viewer"}
            cur.execute(
                "INSERT INTO roles (role_id, tenant_id, name, permissions, created_on, updated_on) VALUES (%s, %s, %s, %s, %s, %s)",
                (r_id, t_id, r_name, json.dumps(perms), now, now)
            )
            role_map[t_id][r_name] = r_id
            
    # 5. Seed Users
    for t_id in tenant_ids:
        # One of each role per tenant
        for r_name in role_names:
            u_id = uuid.uuid4()
            first_name = fake.first_name()
            last_name = fake.last_name()
            email = f"{first_name.lower()}.{last_name.lower()}@{fake.domain_name()}"
            cur.execute(
                """INSERT INTO users (user_id, tenant_id, role_id, email, password_hash, first_name, last_name, created_on, updated_on) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (u_id, t_id, role_map[t_id][r_name], email, password_hash, first_name, last_name, now, now)
            )
            print(f"Created user: {email} ({r_name}) for tenant: {t_id}")

    # 6. Seed Categories and Subcategories for all industries
    print("\nSeeding Categories and Subcategories...")
    
    seed_hierarchy = {
        "Legal": {
            "Contracts": ["NDA", "SLA", "MSA", "SOW", "Partnership Agreement", "Joint Venture", "Vendor Agreement", "Licensing", "Consulting", "Employment"],
            "Compliance": ["Privacy Policy", "GDPR Compliance", "HIPAA Policy", "SOC2 Report", "ISO27001", "Audit Trail", "Internal Policy", "Code of Conduct", "Whistleblower", "Data Retention"],
            "Litigation": ["Case File", "Affidavit", "Legal Notice", "Court Order", "Summons", "Deposition", "Brief", "Exhibit", "Judgment", "Appeal"],
            "Corporate": ["Incorporation", "Bylaws", "Board Minutes", "Shareholder Agreement", "Stock Purchase", "Merger Doc", "Dissolution", "Annual Report", "Certificate of Good Standing", "Operating Agreement"],
            "Intellectual Property": ["Patent Application", "Trademark Registration", "Copyright Filing", "IP Assignment", "License Agreement", "Infringement Notice", "Search Report", "Design Right", "Trade Secret Policy", "Renewal Notice"],
            "Real Estate Legal": ["Title Deed", "Closing Disclosure", "Escrow Agreement", "Mortgage Deed", "Lease Contract", "Zoning Permit", "Property Tax Assessment", "Lien Waiver", "Purchase Offer", "Survey Report"],
            "Tax Legal": ["Tax Return", "IRS Correspondence", "Audit Notice", "Tax Opinion", "Exemption Certificate", "Vat Registration", "Transfer Pricing", "Payroll Tax", "Incentive Claim", "Tax Lien"],
            "Employment Legal": ["Offer Letter", "Termination Agreement", "Employee Handbook", "Non-Compete", "Severance Package", "Grievance Record", "Performance Review Legal", "Work Authorization", "Commission Plan", "Benefit Summary"],
            "Regulatory": ["SEC Filing", "Environmental Permit", "FDA Approval", "FCC License", "Occupational License", "Building Permit", "Import License", "Export Control", "Safety Certificate", "Compliance Audit"],
            "Insurance Legal": ["Policy Document", "Claim Form", "Settlement Agreement", "Renewal Notice", "Premium Invoice", "Underwriting Report", "Endorsement", "Certificate of Insurance", "Risk Assessment", "Loss Run"]
        },
        "Healthcare": {
            "Clinical Records": ["Patient History", "Diagnosis Report", "Discharge Summary", "Lab Results", "Radiology Report", "Prescription", "Immunization Record", "Surgery Note", "Vitals Log", "Referral Letter"],
            "Billing": ["Medical Invoice", "Insurance Claim", "EOB", "Payment Receipt", "Statement of Account", "Prior Authorization", "Superbill", "Collections Notice", "Refund Doc", "Fee Schedule"],
            "Diagnostics": ["MRI Report", "CT Scan", "Blood Test", "Biopsy Result", "ECG Trace", "Ultrasound", "Genetic Testing", "Allergy Test", "Pathology Report", "Stress Test"],
            "Administration": ["Admission Form", "Consent Form", "Insurance Card", "Patient ID", "Appointment Schedule", "Privacy Notice", "Feedback Form", "Registration Desk", "Medical Release", "Emergency Contact"],
            "Pharmacy": ["Drug Inventory", "Pharmacist Note", "Narcotic Log", "Refill Request", "Interaction Report", "Compound Formula", "Dispensing Record", "Shelf Label", "Supplier Invoice", "Recall Notice"],
            "Research": ["Clinical Trial Protocol", "Informed Consent Research", "Adverse Event", "Lab Notebook", "Statistical Plan", "Grant Proposal", "Ethics Approval", "Study Report", "Data Dictionary", "Publication Draft"],
            "Facilities": ["Maintenance Log", "Safety Inspection", "Equipment Calibration", "Waste Disposal", "Fire Drill", "Inventory List", "Vendor Contract Facility", "Cleaning Schedule", "Energy Usage", "Security Log"],
            "Staffing": ["Physician Credential", "Nurse License", "Shift Roster", "Training Record", "Payroll Healthcare", "Recruitment Doc", "Background Check", "Onboarding Checklist", "Appraisal", "Leave Record"],
            "Insurance Operations": ["Network Contract", "Credentialing Application", "Rate Table", "Provider Manual", "Policy Update", "Newsletter", "Meeting Minutes", "Strategic Plan", "Compliance Manual", "Grievance Log"],
            "Emergency Services": ["Triage Tag", "Ambulance Report", "ER Log", "Incident Command", "Resource Map", "Protocol Manual", "Dispatch Log", "Equipment Check", "Training Scenario", "After Action Report"]
        },
        "Finance": {
            "Accounting": ["Balance Sheet", "P&L Statement", "Cash Flow", "Trial Balance", "General Ledger", "Journal Entry", "Expense Report", "Accounts Payable", "Accounts Receivable", "Bank Statement"],
            "Billing": ["Standard Invoice", "Credit Note", "Debit Note", "Receipt", "Proforma", "Commercial Invoice", "Recurring Bill", "Statement", "Tax Invoice", "Payment Voucher"],
            "Loans": ["Loan Application", "Credit Report", "Appraisal", "Title Policy", "Closing Disclosure", "Promissory Note", "Mortgage", "Approval Letter", "Denial Notice", "Payoff Statement"],
            "Investments": ["Portfolio Summary", "Trade Confirmation", "Investment Policy", "Prospectus", "Annual Report", "K-1 Form", "Subscription Agreement", "Valuation", "Management Fee", "Market Commentary"],
            "Banking": ["Account Opening", "Signature Card", "Wire Transfer", "Stop Payment", "CD Certificate", "Safety Deposit", "OD Notice", "Direct Deposit", "ATM Receipt", "KYC Document"],
            "Audit": ["Audit Plan", "Engagement Letter", "Workpaper", "Management Letter", "Representation Letter", "Internal Audit", "Compliance Checklist", "Inventory Count", "Confirmations", "Final Report"],
            "Tax": ["Income Tax", "Sales Tax", "Property Tax", "Payroll Tax", "Excise Tax", "Tax Planning", "Authority Correspondence", "Credits & Incentives", "International Tax", "Local Filing"],
            "Treasury": ["Cash Forecast", "Investment Log", "FX Trade", "Debt Schedule", "Lease Admin", "Bank Portal Access", "Covenant Tracking", "Guarantee", "LC Application", "Authorized Signers"],
            "Risk Management": ["Risk Register", "Insurance Policy", "Claim Record", "Incident Report", "Business Continuity", "Disaster Recovery", "Vendor Risk", "Model Validation", "Hedging Strategy", "Loss Run"],
            "Real Estate Finance": ["Lease Abstract", "Rent Roll", "Estoppel", "SNDA", "Operating Expense", "Capital Expenditure", "Property Budget", "Acquisition Model", "Due Diligence", "Escrow Reconciliation"]
        }
    }

    for ind_name, categories in seed_hierarchy.items():
        if ind_name not in industry_map:
            # Create if not exists (for industries not in the simple list)
            ind_id = uuid.uuid4()
            cur.execute(
                "INSERT INTO industries (industry_id, name, description, created_on, updated_on) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING",
                (ind_id, ind_name, f"{ind_name} industry documents", now, now)
            )
            cur.execute("SELECT industry_id FROM industries WHERE name = %s", (ind_name,))
            res = cur.fetchone()
            if res:
                industry_id = res[0]
            else: continue
        else:
            industry_id = industry_map[ind_name]
            
        print(f"  + Seeding for Industry: {ind_name}")

        for cat_name, subcategories in categories.items():
            cat_id = uuid.uuid4()
            cur.execute(
                "INSERT INTO categories (category_id, industry_id, name, created_on, updated_on) VALUES (%s, %s, %s, %s, %s)",
                (cat_id, industry_id, cat_name, now, now)
            )
            print(f"    - Category: {cat_name}")

            for sub_name in subcategories:
                sub_id = uuid.uuid4()
                cur.execute(
                    "INSERT INTO subcategories (subcategory_id, category_id, name, created_on, updated_on) VALUES (%s, %s, %s, %s, %s)",
                    (sub_id, cat_id, sub_name, now, now)
                )
            print(f"      -> Seeded {len(subcategories)} subcategories.")

    conn.commit()
    cur.close()
    conn.close()
    print("\nDatabase seeded successfully!")

if __name__ == "__main__":
    seed_database()
