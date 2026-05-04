import psycopg
import json

def increase_limits():
    try:
        conn = psycopg.connect('postgresql://postgres:postgres123@localhost:5432/document_mgmt')
        cur = conn.cursor()
        
        # Update all plans with much higher limits
        new_limits = {
            "ai_limit": 1000000,
            "ocr_pages": 10000,
            "storage_limit_mb": 10240,
            "total_tokens": 1000000
        }
        
        cur.execute("SELECT plan_id, limits FROM subscription_plans")
        plans = cur.fetchall()
        
        for plan_id, limits in plans:
            if isinstance(limits, str):
                limits = json.loads(limits)
            
            limits.update(new_limits)
            cur.execute(
                "UPDATE subscription_plans SET limits = %s WHERE plan_id = %s",
                (json.dumps(limits), plan_id)
            )
            
        conn.commit()
        conn.close()
        print("Limits increased successfully")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    increase_limits()
