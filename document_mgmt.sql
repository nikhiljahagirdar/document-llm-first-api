--
-- PostgreSQL database dump
--

-- Dumped from database version 16.11
-- Updated manually to reflect latest schema (No Verticals, No Business Services)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', 'public', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Cleanup
--
DROP TABLE IF EXISTS public.user_credentials CASCADE;
DROP TABLE IF EXISTS public.audit_logs CASCADE;
DROP TABLE IF EXISTS public.categories CASCADE;
DROP TABLE IF EXISTS public.folders CASCADE;
DROP TABLE IF EXISTS public.document_chunks CASCADE;
DROP TABLE IF EXISTS public.document_history CASCADE;
DROP TABLE IF EXISTS public.document_images CASCADE;
DROP TABLE IF EXISTS public.document_statuses CASCADE;
DROP TABLE IF EXISTS public.document_versions CASCADE;
DROP TABLE IF EXISTS public.documents CASCADE;
DROP TABLE IF EXISTS public.generated_reports CASCADE;
DROP TABLE IF EXISTS public.industries CASCADE;
DROP TABLE IF EXISTS public.invoices CASCADE;
DROP TABLE IF EXISTS public.notifications CASCADE;
DROP TABLE IF EXISTS public.ocr_results CASCADE;
DROP TABLE IF EXISTS public.roles CASCADE;
DROP TABLE IF EXISTS public.subcategories CASCADE;
DROP TABLE IF EXISTS public.subscription_plans CASCADE;
DROP TABLE IF EXISTS public.subscriptions CASCADE;
DROP TABLE IF EXISTS public.templates CASCADE;
DROP TABLE IF EXISTS public.tenant_settings CASCADE;
DROP TABLE IF EXISTS public.tenants CASCADE;
DROP TABLE IF EXISTS public.usage_logs CASCADE;
DROP TABLE IF EXISTS public.users CASCADE;

--
-- Extensions
--
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

SET default_tablespace = '';
SET default_table_access_method = heap;

--
-- Tables
--

CREATE TABLE public.industries (
    industry_id uuid NOT NULL PRIMARY KEY,
    name character varying(100) NOT NULL UNIQUE,
    description text,
    icon character varying(50),
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.categories (
    category_id uuid NOT NULL PRIMARY KEY,
    industry_id uuid NOT NULL REFERENCES public.industries(industry_id),
    name character varying(100) NOT NULL,
    description text,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.subcategories (
    subcategory_id uuid NOT NULL PRIMARY KEY,
    category_id uuid NOT NULL REFERENCES public.categories(category_id),
    name character varying(100) NOT NULL,
    description text,
    prompt text,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.tenants (
    tenant_id uuid NOT NULL PRIMARY KEY,
    name character varying(255) NOT NULL,
    org_name character varying(255),
    address text,
    type character varying(50),
    slug character varying(100) NOT NULL UNIQUE,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.roles (
    role_id uuid NOT NULL PRIMARY KEY,
    tenant_id uuid REFERENCES public.tenants(tenant_id),
    name character varying(50) NOT NULL,
    permissions jsonb,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now(),
    CONSTRAINT uq_role_name_tenant_id UNIQUE (name, tenant_id)
);

CREATE TABLE public.users (
    user_id uuid NOT NULL PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(tenant_id),
    email character varying(100) NOT NULL UNIQUE,
    password_hash character varying(255) NOT NULL,
    role_id uuid REFERENCES public.roles(role_id),
    first_name character varying(50),
    last_name character varying(50),
    google_id character varying(100) UNIQUE,
    profile_image character varying(255),
    provider character varying(20),
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.user_credentials (
    credential_id uuid NOT NULL PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    provider character varying(50) NOT NULL,
    access_token text,
    refresh_token text,
    expires_at timestamp without time zone,
    scopes text[],
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now(),
    CONSTRAINT uq_user_provider UNIQUE (user_id, provider)
);

CREATE TABLE public.folders (
    folder_id uuid NOT NULL PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(tenant_id),
    user_id uuid NOT NULL REFERENCES public.users(user_id),
    parent_folder_id uuid REFERENCES public.folders(folder_id),
    name character varying(255) NOT NULL,
    description text,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.documents (
    document_id uuid NOT NULL PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(tenant_id),
    user_id uuid NOT NULL REFERENCES public.users(user_id),
    industry_id uuid REFERENCES public.industries(industry_id),
    category_id uuid REFERENCES public.categories(category_id),
    subcategory_id uuid REFERENCES public.subcategories(subcategory_id),
    folder_id uuid REFERENCES public.folders(folder_id),
    filename character varying(255) NOT NULL,
    file_url character varying(512) NOT NULL,
    status character varying(50),
    file_size integer,
    file_type character varying(100),
    page_count integer,
    metadata jsonb,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now(),
    google_file_id character varying(255),
    google_last_modified timestamp without time zone,
    CONSTRAINT uq_doc_tenant_filename UNIQUE (tenant_id, filename)
);

CREATE TABLE public.document_versions (
    version_id uuid NOT NULL PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES public.documents(document_id),
    version_number integer,
    content text,
    created_by uuid REFERENCES public.users(user_id),
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now(),
    content_json jsonb,
    content_html jsonb,
    embedding vector(3072)
);

CREATE TABLE public.document_chunks (
    chunk_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES public.documents(document_id),
    version_id uuid REFERENCES public.document_versions(version_id),
    tenant_id uuid NOT NULL REFERENCES public.tenants(tenant_id),
    content text NOT NULL,
    embedding vector(3072),
    page_number integer,
    created_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.document_history (
    history_id uuid NOT NULL PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES public.documents(document_id),
    user_id uuid REFERENCES public.users(user_id),
    event_type character varying(50) NOT NULL,
    status character varying(50),
    message text NOT NULL,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.document_images (
    image_id uuid NOT NULL PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES public.documents(document_id),
    image_url character varying(512) NOT NULL,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.document_statuses (
    status_id uuid NOT NULL PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES public.documents(document_id),
    status character varying(50) NOT NULL,
    status_at timestamp without time zone DEFAULT now() NOT NULL,
    message character varying(255),
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.templates (
    template_id uuid NOT NULL PRIMARY KEY,
    tenant_id uuid REFERENCES public.tenants(tenant_id),
    user_id uuid REFERENCES public.users(user_id),
    industry_id uuid REFERENCES public.industries(industry_id),
    category_id uuid REFERENCES public.categories(category_id),
    subcategory_id uuid REFERENCES public.subcategories(subcategory_id),
    template_name character varying(255) NOT NULL,
    description text,
    template_schema jsonb,
    document_type character varying(50),
    html_content text,
    title character varying(255),
    subtitle character varying(255),
    footer text,
    header_image character varying(255),
    config jsonb,
    is_public boolean DEFAULT false,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.generated_reports (
    report_id uuid NOT NULL PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES public.users(user_id),
    template_id uuid NOT NULL REFERENCES public.templates(template_id),
    folder_id uuid REFERENCES public.folders(folder_id),
    parent_id uuid,
    version integer DEFAULT 1,
    title character varying(255) NOT NULL,
    content_markdown text,
    structured_data jsonb,
    chart_data jsonb,
    original_prompt text,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.subscription_plans (
    plan_id uuid NOT NULL PRIMARY KEY,
    name character varying(50) NOT NULL UNIQUE,
    price double precision,
    currency character varying(10),
    billing_cycle character varying(20),
    limits jsonb,
    features jsonb,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now(),
    description text,
    "interval" character varying(20) DEFAULT 'month'::character varying,
    stripe_monthly_price_id character varying(255),
    stripe_yearly_price_id character varying(255),
    paypal_plan_id character varying(255)
);

CREATE TABLE public.subscriptions (
    subscription_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(tenant_id),
    plan_id uuid NOT NULL REFERENCES public.subscription_plans(plan_id),
    status character varying(50) DEFAULT 'active'::character varying,
    current_period_start timestamp without time zone DEFAULT now(),
    current_period_end timestamp without time zone DEFAULT (now() + '1 mon'::interval),
    cancel_at_period_end boolean DEFAULT false,
    stripe_subscription_id character varying(255),
    paypal_subscription_id character varying(255),
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.invoices (
    invoice_id uuid NOT NULL PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(tenant_id),
    amount double precision NOT NULL,
    currency character varying(10),
    status character varying(50),
    due_date timestamp without time zone,
    paid_at timestamp without time zone,
    paypal_invoice_id character varying(100),
    stripe_invoice_id character varying(100),
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.audit_logs (
    log_id uuid NOT NULL PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(tenant_id),
    user_id uuid REFERENCES public.users(user_id),
    action character varying(100) NOT NULL,
    resource_type character varying(50),
    resource_id character varying(100),
    details jsonb,
    ip_address character varying(45),
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.notifications (
    notification_id uuid NOT NULL PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES public.users(user_id),
    title character varying(255) NOT NULL,
    message text NOT NULL,
    type character varying(50),
    is_read boolean DEFAULT false,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.ocr_results (
    ocr_id uuid NOT NULL PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES public.documents(document_id),
    extracted_text jsonb,
    status character varying(50),
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.tenant_settings (
    settings_id uuid NOT NULL PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(tenant_id),
    config jsonb,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

CREATE TABLE public.usage_logs (
    log_id uuid NOT NULL PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(tenant_id),
    user_id uuid REFERENCES public.users(user_id),
    metric_name character varying(100) NOT NULL,
    quantity integer,
    input_text text,
    output_text text,
    is_active boolean DEFAULT true,
    created_on timestamp without time zone DEFAULT now(),
    updated_on timestamp without time zone DEFAULT now()
);

--
-- Indexes
--
CREATE INDEX idx_chunks_content_trgm ON public.document_chunks USING gin (content public.gin_trgm_ops);
-- Note: IVFFlat/HNSW indexes are disabled for 3072-dim vectors on standard pgvector.

--
-- Seed Data (Universal Hierarchy)
--
DO $$
DECLARE
    ind_id uuid;
    cat_id uuid;
BEGIN
    -- 1. Universal
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Universal', 'Multi-purpose documents applicable across industries');
    
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Legal');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Contracts', 'Non-Disclosure Agreement (NDA), Service Level Agreement (SLA), Master Service Agreement (MSA), Partnership Agreement, Vendor Agreement, Employment Contract');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Compliance', 'Privacy Policy, Terms and Conditions, Data Processing Agreement, Consent Forms');
    
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Finance');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Billing', 'Invoice, Proforma Invoice, Credit Note, Debit Note, Receipt');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Accounting', 'Balance Sheet, Profit and Loss Statement, Cash Flow Statement, Expense Report');
    
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'HR');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Recruitment', 'Offer Letter, Job Description, Interview Evaluation Form');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Employee Management', 'Payslip, Experience Letter, Relieving Letter, Attendance Report, Leave Application');
    
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Operations');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Reporting', 'Daily Report, Weekly Report, Monthly Report, KPI Report, Audit Report');

    -- 2. Healthcare
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Healthcare', 'Medical and clinical institutions');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Clinical');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Patient Records', 'Electronic Medical Record (EMR), Prescription, Diagnosis Report, Discharge Summary');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Diagnostics', 'Lab Report, Radiology Report, Test Result Summary');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Administrative');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Insurance', 'Insurance Claim Form, Pre-Authorization Form');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Billing', 'Medical Invoice, Payment Receipt');

    -- 3. Banking_Finance
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Banking_Finance', 'Banking and Financial Services');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Customer_Onboarding');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'KYC', 'KYC Form, Identity Verification Document, Address Proof');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Loans');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Loan_Processing', 'Loan Application, Loan Agreement, Amortization Schedule');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Transactions');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Statements', 'Bank Statement, Transaction Report');

    -- 4. Construction_RealEstate
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Construction_RealEstate', 'Real Estate and Construction');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Project Management');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Planning', 'Project Plan, Blueprint, BOQ (Bill of Quantities)');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Execution', 'Work Order, Site Inspection Report, Progress Report');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Property');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Agreements', 'Lease Agreement, Sale Agreement, Property Valuation Report');

    -- 5. Ecommerce_Retail
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Ecommerce_Retail', 'Online and Offline Retail');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Sales');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Orders', 'Order Invoice, Order Confirmation, Receipt');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Logistics');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Shipping', 'Shipping Label, Packing Slip, Return Form');

    -- 6. Manufacturing
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Manufacturing', 'Industrial Production');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Production');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Operations', 'Production Report, Work Order, Material Requisition');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Quality');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Control', 'Quality Inspection Report, Defect Report, Compliance Report');

    -- 7. Education
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Education', 'Academic and Educational Institutions');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Academic');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Student Records', 'Report Card, Transcript, Certificate');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Administration');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Admissions', 'Admission Form, Enrollment Form');

    -- 8. Legal
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Legal_Industry', 'Legal Firms and Professionals');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Litigation');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Case Documents', 'Case File, Affidavit, Legal Notice, Court Filing');

    -- 9. Travel_Hospitality
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Travel_Hospitality', 'Travel Agencies and Hotels');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Booking');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Reservations', 'Booking Confirmation, Hotel Voucher, Travel Itinerary');

    -- 10. Logistics_SupplyChain
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Logistics_SupplyChain', 'Freight and Supply Chain');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Shipping');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Freight', 'Bill of Lading, Shipping Manifest, Delivery Challan');

    -- 11. IT_SaaS
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'IT_SaaS', 'Information Technology and Software');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Development');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Documentation', 'SRS, HLD, LLD, API Documentation');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Operations');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'DevOps', 'Runbook, Incident Report, Release Notes');

    -- 12. Government_Compliance
    ind_id := gen_random_uuid();
    INSERT INTO industries (industry_id, name, description) VALUES (ind_id, 'Government_Compliance', 'Regulatory and Public Sector');
    cat_id := gen_random_uuid();
    INSERT INTO categories (category_id, industry_id, name) VALUES (cat_id, ind_id, 'Regulatory');
    INSERT INTO subcategories (subcategory_id, category_id, name, description) VALUES (gen_random_uuid(), cat_id, 'Licensing', 'License, Permit, Tax Filing, Compliance Certificate');

END $$;
