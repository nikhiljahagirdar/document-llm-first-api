import asyncio
import uuid
import sys
import os
import selectors
from datetime import datetime
from faker import Faker

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper
from app.security import get_password_hash

fake = Faker()

NEW_HIERARCHY = {
  "industries": [
    {
      "name": "Universal",
      "categories": [
        {
          "name": "Legal",
          "subcategories": [
            {
              "name": "Contracts_Agreements",
              "documents": ["Non-Disclosure Agreement (NDA)", "Mutual NDA", "Service Level Agreement (SLA)", "Master Service Agreement (MSA)", "Statement of Work (SOW)", "Partnership Agreement", "Joint Venture Agreement", "Vendor Agreement", "Supplier Agreement", "Franchise Agreement", "Licensing Agreement", "Distribution Agreement", "Consulting Agreement", "Employment Contract", "Independent Contractor Agreement"]
            },
            {
              "name": "Corporate_Legal",
              "documents": ["Memorandum of Association (MOA)", "Articles of Association (AOA)", "Board Resolution", "Shareholder Agreement", "Cap Table", "Power of Attorney"]
            },
            {
              "name": "Compliance_Policies",
              "documents": ["Privacy Policy", "Terms and Conditions", "Cookie Policy", "Data Processing Agreement (DPA)", "Information Security Policy", "Code of Conduct", "Whistleblower Policy"]
            }
          ]
        },
        {
          "name": "Finance_Accounting",
          "subcategories": [
            {
              "name": "Billing",
              "documents": ["Invoice", "Tax Invoice", "Proforma Invoice", "Commercial Invoice", "Recurring Invoice", "Credit Note", "Debit Note", "Receipt"]
            },
            {
              "name": "Accounting",
              "documents": ["Balance Sheet", "Profit and Loss Statement", "Cash Flow Statement", "Trial Balance", "General Ledger", "Journal Entry", "Expense Report"]
            },
            {
              "name": "Taxation",
              "documents": ["VAT Return", "GST Return", "Corporate Tax Filing", "Withholding Tax Report", "Tax Invoice Register"]
            }
          ]
        },
        {
          "name": "HR",
          "subcategories": [
            {
              "name": "Recruitment",
              "documents": ["Job Description", "Offer Letter", "Interview Feedback Form", "Candidate Evaluation Sheet"]
            },
            {
              "name": "Employee_Lifecycle",
              "documents": ["Appointment Letter", "Employment Contract", "Payslip", "Promotion Letter", "Warning Letter", "Termination Letter", "Experience Letter", "Relieving Letter"]
            },
            {
              "name": "HR_Operations",
              "documents": ["Attendance Report", "Leave Application", "Leave Balance Report", "Timesheet", "HR Policy Handbook"]
            }
          ]
        },
        {
          "name": "Sales_Marketing",
          "subcategories": [
            {
              "name": "Sales",
              "documents": ["Quotation", "Estimate", "Sales Proposal", "Sales Contract", "Order Form", "Sales Report"]
            },
            {
              "name": "Marketing",
              "documents": ["Campaign Plan", "Campaign Report", "Market Research Report", "Customer Persona Document", "SEO Report"]
            }
          ]
        },
        {
          "name": "Operations",
          "subcategories": [
            {
              "name": "Reporting",
              "documents": ["Daily Report", "Weekly Report", "Monthly Report", "KPI Dashboard Report", "Audit Report", "Incident Report", "Risk Assessment Report"]
            }
          ]
        }
      ]
    },
    {
      "name": "Healthcare",
      "categories": [
        {
          "name": "Clinical",
          "subcategories": [
            {
              "name": "Patient_Records",
              "documents": ["Electronic Medical Record (EMR)", "Electronic Health Record (EHR)", "Prescription", "Diagnosis Report", "Treatment Plan", "Discharge Summary"]
            },
            {
              "name": "Diagnostics",
              "documents": ["Lab Test Report", "Blood Test Report", "Radiology Report", "MRI Report", "CT Scan Report"]
            }
          ]
        },
        {
          "name": "Administrative",
          "subcategories": [
            {
              "name": "Insurance",
              "documents": ["Insurance Claim Form", "Pre-Authorization Form", "Medical Insurance Report"]
            },
            {
              "name": "Compliance",
              "documents": ["Consent Form", "HIPAA Compliance Document", "Medical Audit Report"]
            }
          ]
        }
      ]
    },
    {
      "name": "Banking_Fintech",
      "categories": [
        {
          "name": "Customer_Onboarding",
          "subcategories": [
            {
              "name": "KYC",
              "documents": ["KYC Form", "Identity Verification", "Address Verification", "AML Report"]
            }
          ]
        },
        {
          "name": "Loans_Credit",
          "subcategories": [
            {
              "name": "Loan_Processing",
              "documents": ["Loan Application", "Loan Agreement", "Credit Assessment Report", "Amortization Schedule"]
            }
          ]
        },
        {
          "name": "Investment",
          "subcategories": [
            {
              "name": "Portfolio",
              "documents": ["Investment Portfolio Report", "Risk Profile", "Wealth Statement"]
            }
          ]
        }
      ]
    },
    {
      "name": "Construction_RealEstate",
      "categories": [
        {
          "name": "Project",
          "subcategories": [
            {
              "name": "Planning",
              "documents": ["Project Plan", "Blueprint", "BOQ", "Cost Estimation"]
            },
            {
              "name": "Execution",
              "documents": ["Work Order", "Site Inspection Report", "Progress Report", "Safety Report"]
            }
          ]
        },
        {
          "name": "Property",
          "subcategories": [
            {
              "name": "Transactions",
              "documents": ["Lease Agreement", "Sale Agreement", "Property Valuation Report", "Title Deed"]
            }
          ]
        }
      ]
    },
    {
      "name": "Manufacturing",
      "categories": [
        {
          "name": "Production",
          "subcategories": [
            {
              "name": "Operations",
              "documents": ["Production Plan", "Production Report", "Work Order", "Material Requisition"]
            }
          ]
        },
        {
          "name": "Quality",
          "subcategories": [
            {
              "name": "Control",
              "documents": ["Quality Inspection Report", "Defect Report", "CAPA Report", "Compliance Certificate"]
            }
          ]
        }
      ]
    },
    {
      "name": "Logistics_SupplyChain",
      "categories": [
        {
          "name": "Shipping",
          "subcategories": [
            {
              "name": "Freight",
              "documents": ["Bill of Lading", "Air Waybill", "Shipping Manifest", "Delivery Challan", "Proof of Delivery"]
            }
          ]
        },
        {
          "name": "Warehouse",
          "subcategories": [
            {
              "name": "Inventory",
              "documents": ["Inventory Report", "Stock Ledger", "Goods Receipt Note (GRN)"]
            }
          ]
        }
      ]
    },
    {
      "name": "IT_SaaS",
      "categories": [
        {
          "name": "Engineering",
          "subcategories": [
            {
              "name": "Documentation",
              "documents": ["Software Requirements Specification (SRS)", "High-Level Design (HLD)", "Low-Level Design (LLD)", "API Documentation", "Architecture Diagram"]
            }
          ]
        },
        {
          "name": "Operations",
          "subcategories": [
            {
              "name": "DevOps",
              "documents": ["Runbook", "Incident Report", "Postmortem Report", "Release Notes"]
            }
          ]
        }
      ]
    },
    {
      "name": "Education",
      "categories": [
        {
          "name": "Academic",
          "subcategories": [
            {
              "name": "Student",
              "documents": ["Report Card", "Transcript", "Degree Certificate", "Diploma Certificate"]
            }
          ]
        }
      ]
    },
    {
      "name": "Government",
      "categories": [
        {
          "name": "Regulatory",
          "subcategories": [
            {
              "name": "Licensing",
              "documents": ["Business License", "Permit", "Tax Filing", "Compliance Certificate", "Inspection Report"]
            }
          ]
        }
      ]
    }
  ]
}

async def seed_data():
    async with get_connection() as conn:
        print("Connected to DB. Starting enhanced seeding...")
        
        # 1. Seed Roles
        role_types = ["superadmin", "tenant_admin", "user", "viewer"]
        role_map = {}
        for r_name in role_types:
            existing = await DBWrapper.fetch_one(conn, "SELECT role_id FROM roles WHERE name = %s AND tenant_id IS NULL", (r_name,))
            if existing:
                role_id = existing["role_id"]
            else:
                role_id = uuid.uuid4()
                await DBWrapper.execute(conn, 
                    "INSERT INTO roles (role_id, name, permissions, created_on) VALUES (%s, %s, %s, %s)", 
                    (role_id, r_name, '{}', datetime.now()))
                print(f"Seeded Role: {r_name}")
            role_map[r_name] = role_id

        # 2. Seed Industries / Categories / Subcategories
        for ind_data in NEW_HIERARCHY["industries"]:
            ind_name = ind_data["name"]
            existing_ind = await DBWrapper.fetch_one(conn, "SELECT industry_id FROM industries WHERE name = %s", (ind_name,))
            if existing_ind:
                ind_id = existing_ind["industry_id"]
            else:
                ind_id = uuid.uuid4()
                await DBWrapper.execute(conn, "INSERT INTO industries (industry_id, name, description) VALUES (%s, %s, %s)", (ind_id, ind_name, f"{ind_name} Industry"))
                print(f"Seeded Industry: {ind_name}")
            
            for cat_data in ind_data["categories"]:
                cat_name = cat_data["name"]
                existing_cat = await DBWrapper.fetch_one(conn, "SELECT category_id FROM categories WHERE name = %s AND industry_id = %s", (cat_name, ind_id))
                if existing_cat:
                    cat_id = existing_cat["category_id"]
                else:
                    cat_id = uuid.uuid4()
                    await DBWrapper.execute(conn, "INSERT INTO categories (category_id, industry_id, name) VALUES (%s, %s, %s)", (cat_id, ind_id, cat_name))
                    print(f"  Seeded Category: {cat_name}")
                
                for sub_data in cat_data["subcategories"]:
                    sub_name = sub_data["name"]
                    existing_sub = await DBWrapper.fetch_one(conn, "SELECT subcategory_id FROM subcategories WHERE name = %s AND category_id = %s", (sub_name, cat_id))
                    if not existing_sub:
                        desc = f"Supported documents: {', '.join(sub_data['documents'])}"
                        await DBWrapper.execute(conn, "INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (%s, %s, %s, %s)", (uuid.uuid4(), cat_id, sub_name, desc))
                        print(f"    Seeded Subcategory: {sub_name}")

        # 3. Seed Tenants (Fixed + Faker)
        tenants = []
        # Main Demo Tenant
        existing_demo = await DBWrapper.fetch_one(conn, "SELECT tenant_id FROM tenants WHERE slug = %s", ("demo-tenant",))
        if existing_demo:
            demo_tenant_id = existing_demo["tenant_id"]
        else:
            demo_tenant_id = uuid.uuid4()
            await DBWrapper.execute(conn, "INSERT INTO tenants (tenant_id, name, org_name, slug, type) VALUES (%s, %s, %s, %s, %s)", (demo_tenant_id, "Demo Tenant", "Demo Corp", "demo-tenant", "enterprise"))
            print("Seeded Demo Tenant")
        tenants.append(demo_tenant_id)

        # 2 more random tenants using Faker
        for _ in range(2):
            t_name = fake.company()
            t_slug = t_name.lower().replace(" ", "-").replace(",", "")[:20] + "-" + str(uuid.uuid4().hex[:4])
            t_id = uuid.uuid4()
            await DBWrapper.execute(conn, "INSERT INTO tenants (tenant_id, name, org_name, slug, type) VALUES (%s, %s, %s, %s, %s)", (t_id, t_name, t_name, t_slug, "standard"))
            tenants.append(t_id)
            print(f"Seeded Fake Tenant: {t_name}")

        # 4. Seed Users (Fixed + Faker)
        fixed_users = [
            ("superadmin@example.com", "Super", "Admin", "admin123", role_map["superadmin"], demo_tenant_id),
            ("admin@demo.com", "Tenant", "Admin", "admin123", role_map["tenant_admin"], demo_tenant_id),
            ("user@demo.com", "Standard", "User", "user123", role_map["user"], demo_tenant_id),
        ]

        for email, f_name, l_name, pwd, r_id, t_id in fixed_users:
            existing = await DBWrapper.fetch_one(conn, "SELECT user_id FROM users WHERE email = %s", (email,))
            if not existing:
                await DBWrapper.execute(conn,
                    "INSERT INTO users (user_id, tenant_id, email, password_hash, role_id, first_name, last_name, provider) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (uuid.uuid4(), t_id, email, get_password_hash(pwd), r_id, f_name, l_name, "local"))
                print(f"Seeded Fixed User: {email}")

        # Add 10 fake users
        for _ in range(10):
            f_name = fake.first_name()
            l_name = fake.last_name()
            email = f"{f_name.lower()}.{l_name.lower()}@{fake.domain_name()}"
            t_id = fake.random_element(tenants)
            r_id = fake.random_element([role_map["user"], role_map["viewer"]])
            await DBWrapper.execute(conn,
                "INSERT INTO users (user_id, tenant_id, email, password_hash, role_id, first_name, last_name, provider) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (uuid.uuid4(), t_id, email, get_password_hash("password123"), r_id, f_name, l_name, "local"))
        print("Seeded 10 fake users across tenants.")

        # 5. Seed Subscription Plans
        plans = [
            ("Free", 0.0, "USD", "month", '{"doc_limit": 5, "ai_limit": 10}'),
            ("Pro", 29.0, "USD", "month", '{"doc_limit": 100, "ai_limit": 500}'),
            ("Enterprise", 199.0, "USD", "month", '{"doc_limit": -1, "ai_limit": -1}')
        ]
        for p_name, p_price, p_curr, p_cycle, p_limits in plans:
            existing = await DBWrapper.fetch_one(conn, "SELECT plan_id FROM subscription_plans WHERE name = %s", (p_name,))
            if not existing:
                await DBWrapper.execute(conn,
                    "INSERT INTO subscription_plans (plan_id, name, price, currency, billing_cycle, limits) VALUES (%s, %s, %s, %s, %s, %s)",
                    (uuid.uuid4(), p_name, p_price, p_curr, p_cycle, p_limits))
                print(f"Seeded Plan: {p_name}")

    print("Enhanced seeding complete.")

if __name__ == "__main__":
    loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()) if sys.platform == 'win32' else None
    if loop_factory:
        asyncio.run(seed_data(), loop_factory=loop_factory)
    else:
        asyncio.run(seed_data())
