import psycopg
import uuid

def reset_usage():
    try:
        conn = psycopg.connect('postgresql://postgres:postgres123@localhost:5432/document_mgmt')
        cur = conn.cursor()
        tenant_id = '04c2ffd1-a2dc-4b89-a1ad-4c48849122aa'
        
        cur.execute("DELETE FROM usage_logs WHERE tenant_id = %s::uuid", (tenant_id,))
        
        # Also ensure we have a valid subscription with high limits
        cur.execute("""
            UPDATE subscriptions 
            SET status = 'active', 
                current_period_end = '2030-01-01'
            WHERE tenant_id = %s::uuid
        """, (tenant_id,))
        
        conn.commit()
        conn.close()
        print(f"Usage reset and subscription extended for {tenant_id}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    reset_usage()
