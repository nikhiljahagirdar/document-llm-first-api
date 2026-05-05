from app.security import get_password_hash, verify_password

password = "admin123"
hashed = get_password_hash(password)
print(f"Password: {password}")
print(f"Hashed: {hashed}")
print(f"Verified: {verify_password(password, hashed)}")

# Check against a known failing case if possible, but we don't have the hash from DB easily.
