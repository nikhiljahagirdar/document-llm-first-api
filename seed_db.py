import psycopg
import uuid
import json
from datetime import datetime
from faker import Faker
from app.security import get_password_hash

fake = Faker()

def seed_database():
    conn = psycopg.connect('postgresql://postgres:postgres123@localhost:5432/document_mgmt')
    cur = conn.cursor()
    
    print("Database is fresh, skipping truncate...")
    
    password_hash = get_password_hash("password123")
    now = datetime.now()
    
    # 1. Seed Industries (Skip verticals)
    industries = ["Legal", "Healthcare", "Finance", "Real Estate"]
    industry_ids = []
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
            industry_ids.append(res[0])
        
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

    # 6. Seed Categories and Subcategories for the first industry
    industry_id = industry_ids[0]
    categories = ["Contracts", "Invoices", "Reports"]
    for cat_name in categories:
        cat_id = uuid.uuid4()
        cur.execute(
            "INSERT INTO categories (category_id, industry_id, name, created_on, updated_on) VALUES (%s, %s, %s, %s, %s)",
            (cat_id, industry_id, cat_name, now, now)
        )
        # Subcategories
        for i in range(2):
            sub_id = uuid.uuid4()
            sub_name = f"{cat_name} Type {i+1}"
            cur.execute(
                "INSERT INTO subcategories (subcategory_id, category_id, name, created_on, updated_on) VALUES (%s, %s, %s, %s, %s)",
                (sub_id, cat_id, sub_name, now, now)
            )

    conn.commit()
    cur.close()
    conn.close()
    print("\nDatabase seeded successfully!")

if __name__ == "__main__":
    seed_database()
