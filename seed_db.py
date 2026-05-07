import psycopg
import uuid
import json
from datetime import datetime
import stripe
from faker import Faker
from app.security import get_password_hash
import os
from dotenv import load_dotenv

fake = Faker()
load_dotenv()

def clear_database(cur):
    print("Clearing all data from all tables...")
    cur.execute("""
        SELECT tablename 
        FROM pg_catalog.pg_tables 
        WHERE schemaname = 'public'
    """)
    tables = cur.fetchall()
    
    if not tables:
        print("No tables found to clear.")
        return

    # Filter out spatial_ref_sys if it exists (it's part of PostGIS/Vector)
    table_list = ", ".join([f'"{t[0]}"' for t in tables if t[0] != 'spatial_ref_sys'])
    print(f"Truncating tables: {table_list}")
    
    cur.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE;")
    print("Database cleared.")

def seed_database():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in .env")
        return

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        print("\nWARNING: STRIPE_SECRET_KEY not found in .env. Skipping Stripe plan synchronization.")

    
    conn = psycopg.connect(db_url)
    cur = conn.cursor()
    
    try:
        # 1. Clear everything
        clear_database(cur)
        
        now = datetime.now()

        # 2. Seed Global Roles
        print("\nSeeding Global Roles...")
        roles_to_seed = {
            "Admin": {"read": True, "write": True, "delete": True, "manage_users": True},
            "User": {"read": True, "write": True, "delete": False},
            "Viewer": {"read": True, "write": False, "delete": False}
        }
        for role_name, permissions in roles_to_seed.items():
            cur.execute(
                """INSERT INTO roles (role_id, name, permissions, tenant_id, created_on, updated_on)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (uuid.uuid4(), role_name, json.dumps(permissions), None, now, now)
            )
            print(f"  + Role: {role_name}")

        password_hash = get_password_hash("Admin@123")
        
        # 3. Seed Plans and Sync with Stripe
        print("\nSeeding Plans...")
        plans = [
            {
                "id": uuid.uuid4(),
                "name": "Free",
                "price": 0.0,
                "currency": "USD",
                "billing_cycle": "monthly",
                "description": "Basic plan for individuals",
                "limits": {"documents": 10, "storage_mb": 50, "reports": 3}
            },
            {
                "id": uuid.uuid4(),
                "name": "Pro",
                "price": 29.0,
                "currency": "USD",
                "billing_cycle": "monthly",
                "description": "Professional plan for small teams",
                "limits": {"documents": 1000, "storage_mb": 5000, "reports": 100}
            },
            {
                "id": uuid.uuid4(),
                "name": "Enterprise",
                "price": 299.0,
                "currency": "USD",
                "billing_cycle": "monthly",
                "description": "Enterprise plan for large organizations",
                "limits": {"documents": 100000, "storage_mb": 500000, "reports": 10000}
            }
        ]

        existing_stripe_products = {}
        if stripe.api_key:
            print("  -> Fetching existing products from Stripe to prevent duplicates...")
            try:
                all_products = stripe.Product.list(limit=100, active=True)
                for prod in all_products:
                    existing_stripe_products[prod.name] = prod
                print(f"     - Found {len(existing_stripe_products)} existing products in Stripe.")
            except stripe.error.StripeError as e:
                print(f"     - ERROR: Could not fetch Stripe products: {e}")
                print("     - Disabling Stripe integration for this run.")
                stripe.api_key = None

        for p in plans:
            stripe_monthly_id = None
            stripe_yearly_id = None

            if stripe.api_key and p['price'] > 0:
                print(f"  -> Syncing plan '{p['name']}' with Stripe...")
                product = None
                try:
                    if p['name'] in existing_stripe_products:
                        product = existing_stripe_products[p['name']]
                        print(f"     - Product '{p['name']}' already exists in Stripe (ID: {product.id}).")
                    else:
                        product = stripe.Product.create(
                            name=p['name'],
                            description=p['description'],
                            metadata={'plan_id': str(p['id'])}
                        )
                        print(f"     - Created new product in Stripe (ID: {product.id}).")
                    
                    existing_prices = stripe.Price.list(product=product.id, active=True)
                    monthly_amount = int(p['price'] * 100)
                    yearly_amount = int(round(p['price'] * 10, 2) * 100)

                    for price_obj in existing_prices:
                        if price_obj.recurring and price_obj.recurring['interval'] == 'month' and price_obj.unit_amount == monthly_amount:
                            stripe_monthly_id = price_obj.id
                        elif price_obj.recurring and price_obj.recurring['interval'] == 'year' and price_obj.unit_amount == yearly_amount:
                            stripe_yearly_id = price_obj.id
                            
                    if not stripe_monthly_id:
                        monthly_price_obj = stripe.Price.create(
                            product=product.id,
                            unit_amount=monthly_amount,
                            currency=p['currency'].lower(),
                            recurring={"interval": "month"},
                        )
                        stripe_monthly_id = monthly_price_obj.id
                        print(f"     - Created monthly price: {stripe_monthly_id}")

                    if not stripe_yearly_id:
                        yearly_price_obj = stripe.Price.create(
                            product=product.id,
                            unit_amount=yearly_amount,
                            currency=p['currency'].lower(),
                            recurring={"interval": "year"},
                        )
                        stripe_yearly_id = yearly_price_obj.id
                        print(f"     - Created yearly price: {stripe_yearly_id}")

                except stripe.error.StripeError as e:
                    print(f"     - Stripe Error for plan '{p['name']}': {e}")

            cur.execute(
                """INSERT INTO subscription_plans (plan_id, name, price, currency, billing_cycle, description, limits, stripe_monthly_price_id, stripe_yearly_price_id, created_on, updated_on) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (p["id"], p["name"], p["price"], p["currency"], p["billing_cycle"], p["description"], json.dumps(p["limits"]), stripe_monthly_id, stripe_yearly_id, now, now)
            )
            print(f"  + Plan '{p['name']}' seeded in DB.")

        # 4. Seed Industries, Categories, Subcategories
        print("\nSeeding Industries, Categories and Subcategories...")
        
        # Main industries list
        industries = ["Legal", "Healthcare", "Finance", "Real Estate","HR","Education","Marketing","Sales","Operations","IT","Ecommerce_Retail","Construction_RealEstate","Automotive","Manufacturing","Energy_Utilities","Telecom","Media_Entertainment","Government_PublicSector","Nonprofit","Other"]
        
        # Hierarchy for specific industries
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
                "Risk Management": ["Risk Register", "Insurance Policy", "Claim Record", "Incident Report", "Business Continuity", "Disaster Recovery", "Vendor Risk", "Model Validation", "Hedging Strategy", "Loss Run"]
            },
            "HR": {
                "Recruitment": ["Job Description", "Offer Letter", "Interview Feedback", "Candidate Evaluation"],
                "Employee Management": ["Payslip", "Experience Letter", "Relieving Letter", "Warning Letter", "Promotion Letter", "Employment Contract"],
                "HR Operations": ["Attendance Report", "Leave Application", "HR Policy Handbook", "Timesheet"],
            },
            "Education": {
                "Academic Records": ["Report Card", "Transcript", "Certificate", "Diploma"],
                "Administration": ["Admission Form", "Enrollment Form", "Fee Receipt", "Student ID Card"],
            },
            "IT": {
                "Software Development": ["SRS", "HLD", "LLD", "API Documentation", "Release Notes", "User Story"],
                "Operations & DevOps": ["Runbook", "Incident Report", "Postmortem", "Change Request", "Deployment Plan"],
                "Security": ["Security Policy", "Vulnerability Scan Report", "Penetration Test Report", "Access Control List"],
            },
            "Marketing": {
                "Campaign Management": ["Campaign Plan", "Campaign Report", "Ad Copy", "Email Marketing Template"],
                "Content & SEO": ["Blog Post", "Whitepaper", "SEO Report", "Keyword Analysis", "Social Media Calendar"],
                "Market Research": ["Survey Results", "Competitor Analysis", "Market Research Report", "Focus Group Notes"],
            },
            "Sales": {
                "Proposals & Contracts": ["Quotation", "Sales Proposal", "Sales Contract", "Order Form", "RFP Response"],
                "Reporting": ["Sales Report", "Forecast Report", "Commission Statement", "Pipeline Report"],
            },
            "Operations": {
                "Reporting": ["Daily Report", "Weekly Report", "Monthly Report", "KPI Report", "Business Review Deck"],
                "Logistics": ["Purchase Order", "Delivery Note", "Inventory Report", "Shipping Manifest"],
                "Quality Assurance": ["QA Test Plan", "Bug Report", "Audit Report", "User Acceptance Testing (UAT) Script"],
            },
            "Ecommerce_Retail": {
                "Sales & Orders": ["Order Invoice", "Order Confirmation", "Receipt", "Return Form", "Refund Confirmation"],
                "Logistics & Shipping": ["Shipping Label", "Packing Slip", "Bill of Lading", "Proof of Delivery"],
            },
            "Manufacturing": {
                "Production": ["Production Plan", "Work Order", "Bill of Materials (BOM)", "Production Schedule"],
                "Quality Control": ["Quality Inspection Report", "Defect Report", "Compliance Certificate", "Corrective Action Plan (CAPA)"],
                "Supply Chain": ["Material Requisition", "Supplier Agreement", "Inventory Ledger", "Goods Receipt Note (GRN)"],
            },
            "Government_PublicSector": {
                "Regulatory & Licensing": ["Business License", "Permit Application", "Tax Filing", "Compliance Report"],
                "Public Records": ["Grant Application", "Public Notice", "Meeting Minutes", "Freedom of Information Act (FOIA) Request"],
            },
            "Construction_RealEstate": {
                "Project Management": ["Project Plan", "Blueprint", "Bill of Quantities (BOQ)", "Site Inspection Report", "Request for Information (RFI)"],
                "Property Transactions": ["Lease Agreement", "Sale Agreement", "Title Deed", "Property Valuation Report", "Rental Application"],
            }
        }

        industry_map = {}
        for ind_name in industries:
            ind_id = uuid.uuid4()
            cur.execute(
                "INSERT INTO industries (industry_id, name, description, created_on, updated_on) VALUES (%s, %s, %s, %s, %s)",
                (ind_id, ind_name, f"{ind_name} industry documents", now, now)
            )
            industry_map[ind_name] = ind_id
            print(f"  + Industry: {ind_name}")

            if ind_name in seed_hierarchy:
                for cat_name, subcategories in seed_hierarchy[ind_name].items():
                    cat_id = uuid.uuid4()
                    cur.execute(
                        "INSERT INTO categories (category_id, industry_id, name, created_on, updated_on) VALUES (%s, %s, %s, %s, %s)",
                        (cat_id, ind_id, cat_name, now, now)
                    )
                    print(f"    - Category: {cat_name}")

                    for sub_name in subcategories:
                        sub_id = uuid.uuid4()
                        cur.execute(
                            "INSERT INTO subcategories (subcategory_id, category_id, name, created_on, updated_on) VALUES (%s, %s, %s, %s, %s)",
                            (sub_id, cat_id, sub_name, now, now)
                        )
                    print(f"      -> Seeded {len(subcategories)} subcategories.")

        # 5. Seed Superadmin
        print("\nSeeding Superadmin...")
        system_tenant_id = uuid.uuid4()
        cur.execute(
            "INSERT INTO tenants (tenant_id, name, slug, org_name, created_on, updated_on) VALUES (%s, %s, %s, %s, %s, %s)",
            (system_tenant_id, "SellingPoint System", "sellingpoint-system", "SellingPoint Inc.", now, now)
        )
        
        superadmin_role_id = uuid.uuid4()
        cur.execute(
            "INSERT INTO roles (role_id, tenant_id, name, permissions, created_on, updated_on) VALUES (%s, %s, %s, %s, %s, %s)",
            (superadmin_role_id, system_tenant_id, "Super Admin", json.dumps({"all": True}), now, now)
        )
        
        superadmin_user_id = uuid.uuid4()
        cur.execute(
            """INSERT INTO users (user_id, tenant_id, role_id, email, password_hash, first_name, last_name, created_on, updated_on) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (superadmin_user_id, system_tenant_id, superadmin_role_id, "admin@sellingpoint.ai", password_hash, "System", "Admin", now, now)
        )
        print(f"Created Superadmin: admin@sellingpoint.ai")

        conn.commit()
        print("\nDatabase seeded successfully!")
    except Exception as e:
        conn.rollback()
        print(f"Error seeding database: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    seed_database()
